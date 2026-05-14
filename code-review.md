# ka11y — System-Wide Code Review

**Date:** 2026-05-14
**Branch:** `fix-patches`
**Scope:** Full system — `ka11y-python` (FastAPI + Playwright + auditors), `ka11y-node` (axe-core + custom checks), API/orchestration glue.
**Reviewer mode:** FAANG production-readiness, brutally honest. Re-review of the 2026-05-06 audit after Sprints 1–5.

---

## 1. Executive Summary

### Overall rating: **82 / 100** (was 54)

The system has moved from "works on the happy path" to "defensible production candidate." The five critical issues from the prior review are **all addressed**, and the bulk of Sprints 1–5 landed:

- **Engine no longer swallows bugs.** `engine.py:10,37` catches *only* `PolicyError`; anything else propagates and is logged with an opaque `error_id` at the job boundary (`runner.py:449-501`). Silent `confidence=0.1` decay is gone.
- **One browser per audit.** Every crawler now leases from `crawler/browser_pool.py`; no crawler calls `async_playwright()` directly. `_MAX_BROWSERS=2`, `_MAX_CONCURRENT_JOBS=4` semaphores bound the host.
- **SSRF substantially hardened.** `_ssrf_guard.py` covers decimal/hex/octal-encoded IPs, IPv4-mapped IPv6, hostname resolution, and redirect targets (installed on the *context*, so it fires per-request). The Node side mirrors it (`accessibility.service.js:11-66`).
- **Data-loss class closed.** `auditor_field_map.py` is the single source of truth for `wcag_X_Y_Z_status` keys, paired with a CI test that fails on drift.
- **Resource economics fixed.** `asyncio.gather` callsites are wrapped in `asyncio.wait_for` budgets; jobs have a `_JOB_TIMEOUT_SECONDS` cap with task cancellation; TTL eviction reclaims `_jobs` and on-disk dirs; `step_logger` writes under per-path locks; auth + per-identity rate limiting + security headers are in place.

What keeps it from 90+: the **two-pipeline architecture** (`rules/*` auditors vs `pipeline/decisions/*` policies bridged by a 1543-line `findings.py`) is *mitigated* but not *resolved*; `universal_extract.js` is off-disk but still one 1079-line payload covering 7 categories; the job store is still in-process memory (no HA); and a layer of **dead/duplicated SSRF code** in `routes.py` actively contradicts the hardened guard.

### Top 5 remaining issues

| # | Issue | Impact |
|---|---|---|
| 1 | **Dead, weaker SSRF code shadows the hardened guard.** `routes.py:90-120` still defines `build_ssrf_route_handler` with the *exact* weak `_IP_HOST_RE` regex the last review flagged; `_BLOCKED_NETWORKS`/`_is_non_public_ip` are duplicated between `routes.py:36-87` and `_ssrf_guard.py:37-78`. Unused today, but a future caller wiring the wrong one re-opens the hole. | Latent SSRF regression; guaranteed drift |
| 2 | **`universal_page._extract_page_chunked` `seen_refs` is still unbounded** (`universal_page.py:389`), and `max_passes` is hardcoded to 4 despite a comment claiming it is config-driven. 4 passes × N elements × concurrent pages still accumulates without a cap. | Memory growth on infinite-scroll pages at scale |
| 3 | **Two parallel rule systems, 1543-line translation layer.** `rules/*` auditors and `pipeline/decisions/*` policies still don't share a data model; `combined/findings.py` remains a hand-maintained bridge. The field-map registry stops *silent* drift but the dual model is the root maintenance tax. | Every rule change touches 3 files; high change-amplification |
| 4 | **Job store is in-process memory.** `store.py:_jobs` is a module dict. TTL eviction and per-job locks are in place, but a process restart loses every running and recent job; no horizontal scaling. | No HA; restarts drop in-flight audits |
| 5 | **Monolithic `universal_extract.js` (1079 lines, 7 categories).** Now loaded from disk and internally split into per-category IIFEs (`extractForms`…`extractSensory`), but still one `page.evaluate` payload — a top-level JS syntax error still takes out all 7 categories at once. | Single point of failure for structural extraction |

---

## 2. Architecture Review

### 2.1 Current architecture

```
            ┌────────────────────────────────────┐
            │  FastAPI app (main.py)             │
            │  _AuthMiddleware → _RateLimit →    │
            │  _SecurityHeaders → CORS           │
            │  lifespan: _evict_old_jobs +       │
            │            browser_pool shutdown   │
            └────────────────┬───────────────────┘
                             ▼
        ┌──────────────── api/v1 ────────────────────┐
        │  combined/  routes • runner • stages •      │
        │             findings • report • store •    │
        │             stage_events • auditor_field_map│
        │  pipeline.py • crawl.py • rules/            │
        └───────────────┬───────────────┬─────────────┘
                        │               │
                        ▼               ▼
   ┌────────────────────────┐   ┌──────────────────────────────┐
   │  Python crawlers       │   │  Node service (HTTP)         │
   │  all lease from        │   │  accessibility.service.js    │
   │  crawler/browser_pool  │   │   ├ axe-core run + locale    │
   │  ├ universal_page      │   │   ├ custom-checks/*.check.js │
   │  ├ crawler (images)    │   │   └ audits/wcag-2.5.x/       │
   │  ├ media / sensory     │   │  SSRF: _assertPublicUrl +    │
   │  ├ rendered_layout     │   │  request interception        │
   │  └ forms / target_size │   └──────────────────────────────┘
   └─────────┬──────────────┘
             ▼
   ┌──────────────────────────────────────────────────────────┐
   │ accessibility/                                           │
   │  rules/      (auditors: alttext, sensory, media, forms…) │
   │  rendered/   (reflow, text_spacing, focus evaluators)    │
   │  pipeline/   extractors • analyzers • runners •          │
   │              decisions/{engine + policy_X_Y_Z} •         │
   │              router • formatters                        │
   └──────────────────────────────────────────────────────────┘
```

### 2.2 What was fixed (vs. the 2026-05-06 review)

- **F4 — engine swallowing.** Resolved. `engine.py` catches `PolicyError` only; everything else propagates to `runner.py`'s structured handler.
- **F2 — crawler proliferation.** Largely resolved. `browser_pool.py` + `context_factory.py` (which installs the SSRF guard on every context) + `navigation.py` (shared resilient navigation) replace the duplicated launch/cleanup blocks. All ten crawlers lease from the pool.
- **F3 — giant inline JS.** Partially resolved. Extractors are on disk (`crawler/js/*.js`, `_load_js`), restoring IDE tooling and syntax checks. Still one payload (see Top-5 #5).
- **F1 — two rule systems.** Mitigated, not resolved. `auditor_field_map.py` + its CI smoke test eliminates the *silent* field-mismatch bug class; the dual data model remains.
- **F7 — module-level singletons.** Improved. `config_loader.py` returns a `deepcopy` so callers can't mutate the cached config; job/subscriber locks are lazy and rebind per event loop (`store.py:_get_job_lock`). `combined/constants.py` still loads `_WCAG_NAMES` at import.

### 2.3 Remaining flaws

**F1′ — `combined/findings.py` is still 1543 lines.** It is a thinner bridge than before (registry-backed), but auditors still emit idiosyncratic record dicts and policies emit `RuleVerdict`s; the converter layer must know both shapes. The end state (auditors emit `Finding(...)` directly) is still a multi-week project.

**F5′ — Node custom-check / audit duplication.** `audits/wcag-2.5.1/` and `custom-checks/pointer-gestures.check.js` still coexist; selector banks (`multilingual-selectors.js` vs `axe-rule-pointer-gestures.js`) still duplicate definitions. Not regressed, not consolidated.

**F8 (new) — dead module files.** `api/v1/combined.py` is a **0-byte file** shadowed by the `combined/` package; `classifier/classfier.py` keeps its typo'd filename. Both are harmless today and both are landmines for the next reader.

**F9 (new) — duplicated security primitives.** `_BLOCKED_NETWORKS`, `_ip_is_blocked`, `_is_non_public_ip` exist in *both* `routes.py` and `_ssrf_guard.py`, with `routes.py` additionally carrying the obsolete regex-based `build_ssrf_route_handler`. One guard must be canonical; the rest deleted.

---

## 3. Performance & Computational Analysis

Most prior P-items are fixed. What remains:

### P-01 (HIGH) — `seen_refs` unbounded across scroll passes
**File:** `ka11y/crawler/universal_page.py:389-432`
**Problem:** `_extract_page_chunked` allocates `seen_refs = set()` and runs `max_passes = 4` (hardcoded — the adjacent comment "Read max scroll passes from config" is stale) with no cap on set size. On infinite-scroll pages the dedup set grows with every element seen across all passes.
**Fix:** Cap the set (`if len(seen_refs) > 5000: break`) and source `max_passes` from `CrawlPolicy`.

### P-02 (MEDIUM) — N+1 `img.evaluate` in the image crawler
**File:** `ka11y/crawler/crawler.py` (~543-573)
**Problem:** Each `<img>` triggers two separate `img.evaluate(...)` round-trips — one for `resolved_label` (aria-labelledby/aria-label), one for `el_context` (role/parent/clickable). 13 `.evaluate` callsites total in the file.
**Fix:** Collapse the two per-image evaluates into a single `el => ({label, ctx})` call.

### P-03 (MEDIUM) — Monolithic `universal_extract.js` payload
**File:** `ka11y/crawler/js/universal_extract.js` (1079 lines)
**Problem:** One `page.evaluate` returns forms + interactive + target_sizes + moving_content + media + text_spacing + sensory. Internally modular (per-category IIFEs) but a single top-level parse error or a thrown exception outside an IIFE's own guard takes out all 7 categories.
**Fix:** Split into 3–4 disk extractors run sequentially; cap each one's serialised output size.

### P-04 (LOW) — `networkidle` timeout logged at `debug`
**File:** `ka11y/crawler/universal_page.py:356`
**Problem:** A `networkidle` timeout is a real "page never settled" signal but is logged at `debug`, invisible in production.
**Fix:** `logger.warning`.

### P-05 (LOW) — Sensory mega-regex / OCR-index / batched evaluates already landed
`sensory_auditor.py` now uses single-pass mega-regexes; `alttext._build_ocr_index` is O(1); `semantic_relationship_engine` and `element_context_extractor` batch their `frame.evaluate` calls; `policy_1_1_1`/`policy_1_4_5` regexes are hoisted. No action.

---

## 4. Accuracy Issues (WCAG-Specific)

The prior review's concrete accuracy bugs are **fixed** — verified by reading the code:

- **1.1.1** — `alttext._is_aria_hidden_from_at` (`alttext.py:312`) now honours `aria-hidden="true"` / `role="presentation"|"none"`; 2-letter uppercase abbreviations ("UI", "OK") are matched.
- **1.3.1** — `policy_1_3_1.py:42` parses `type` from `html_snippet` via `_INPUT_TYPE_RE`, not from CSS `computed_styles`.
- **1.4.3 / 1.4.6** — `contrast_engine.py` has an alpha-aware parser (`_NUMBER_RE` no longer splits `0.5`), Porter-Duff `composite_over`, and hex `#rgba`/`#rrggbbaa` support. `policy_1_4_6.py` cleanly subclasses `Policy143` and overrides thresholds — the always-false enum/string compare is gone. `policy_1_4_3._is_large_text` reads real `font-weight`.
- **2.4.13** — `policy_2_4_13.py` fails on thin *or* low-contrast rings independently (the inverted AND/OR is fixed); `interaction_state_runner.py` extracts real ring thickness and leaves contrast `None` → `needs_review` instead of a fake passing value.
- **2.5.3** — `policy_2_5_3.py` tokenises and does a contiguous-subsequence match; "signin" no longer matches inside "signinbeta".
- **1.4.10** — `reflow.py:59` reads `snapshot_320.viewport_width` and validates it against `_REQUIRED_REFLOW_VIEWPORT_PX = 320`.
- **2.5.1 (Node)** — `escape-hatch-validator.js` rejects `KNOWN_EMPTY_PATTERNS` (`void 0`, `return false`, …) and requires a non-trivial handler body.
- **2.5.4 (Node)** — `disable-control-validator.js` only treats a "settings" link as evidence when motion keywords appear in the nearby subtree; bare settings links are "low" confidence and do not pass. `motion-listener-detector.js` clears `window.__motionRegistry` on read, so listeners no longer bleed across pages.

### Remaining accuracy gaps

**1.3.1 — data-table check is a rubber stamp.** `policy_1_3_1.py:28-35`: any element with `is_in_data_table` returns an unconditional `_pass("table_context")`. A `<td>` with no `<th>`/`scope`/`headers` association still passes. The check confirms membership, not relationships.

**1.1.1 — incidental OCR text can cause false fails.** `alttext._check_1_1_1_informative` (`alttext.py:384`) fails an informative image when OCR finds text the alt doesn't echo. A street photo containing an incidental shop sign would be marked failing even though the sign is not the image's purpose. Needs a "is this text *salient*" gate.

**2.5.1 — escape-hatch threshold is arbitrary.** `escape-hatch-validator.js` accepts a handler when `cleaned.length > 6`. A terse-but-real handler (`doZoom()`) is under the bar; a long junk handler is over it. The length proxy should be a "calls a function / dispatches an event" check.

**2.5.4 — still keyword-heuristic, no opt-in.** `disable-control-validator.js` / `essential-motion-classifier.js` remain keyword-driven. The prior review's recommendation of an explicit `data-wcag-motion-essential` opt-in was not adopted; residual false-positive surface remains (a design decision worth revisiting).

---

## 5. Code Quality Issues

### 5.1 Fixed
- `except Exception → NEEDS_REVIEW` removed from the engine.
- `policy_1_1_1` / `policy_1_4_5` regexes hoisted; the inline `import re` in `policy_1_4_5` is gone.
- `rule_target_router.py` uses an order-preserving dedup, not `list(set(...))`.
- `step_logger.py` appends under per-path `threading.Lock`s.
- `config_loader.py` returns a defensive deepcopy.
- Tuple-by-index stage returns replaced by `PythonStagesResult` dataclass (`runner.py:333`).

### 5.2 Remaining anti-patterns
- **Dead code.** `api/v1/combined.py` (0 bytes); `routes.py:90-120` `build_ssrf_route_handler` (unused, weaker than the real guard).
- **Filename typo.** `classifier/classfier.py` — still produces typo-prone imports.
- **Private-attribute access.** `runner.py:184` reads `sem._value` (`# noqa: SLF001`) to detect a full queue. Breaks silently if CPython renames the field.
- **Fire-and-forget broadcast + sleep hack.** `stage_events._fire_broadcast` schedules `_broadcast` via `loop.create_task` and never awaits it; `runner.py:511-512` does `await asyncio.sleep(0)` *twice* to "flush" those tasks before `_close_subscribers`. This is timing-dependent by the author's own admission in the comment — a lost-event race under load.
- **Crawler exception swallowing.** `universal_page.py` (13×), `rendered_layout_crawler.py` (12×), `crawler.py` (12×) still catch broad `Exception`. Many are legitimately defensive (cross-origin frames, detached contexts) but the volume makes real faults easy to miss; prefer named exceptions.
- **Duplicated security constants** across `routes.py` and `_ssrf_guard.py` (see F9).

### 5.3 Maintainability
- `findings.py` (1543 lines) and `universal_extract.js` (1079 lines) and `stages.py` (1305 lines) are the three files that will dominate future churn.
- Tests: 35 test files, 743 collected cases — real coverage, including `test_auditor_field_map.py` as a drift guard. Good. Node-side tests still mock the DOM in places (`audits/wcag-2.5.4/__tests__`), so production-vs-test divergence risk persists there.

---

## 6. Scalability Review

### 6.1 What's now bounded
- **Browsers:** `_MAX_BROWSERS=2` (pool semaphore), one warm Chromium reused across leases.
- **Jobs:** `_MAX_CONCURRENT_JOBS=4` semaphore; over-cap jobs sit in `queued` status (observable by pollers).
- **Time:** every `asyncio.gather` has an `asyncio.wait_for` budget; `_JOB_TIMEOUT_SECONDS=1200` outer cap cancels stuck branches; per-stage `_STAGE_TIMEOUT_SECONDS`.
- **Disk:** `_evict_old_jobs` runs every 5 min, reclaims `_jobs` entries and on-disk dirs older than `_JOB_TTL_SECONDS=3600`, plus orphan sibling crawler dirs — with a path-containment guard so a poisoned job dict can't trick it into deleting arbitrary trees.
- **Request size:** `CombinedRequest` caps URL length (2048), `wcag_level` pattern, `lang` `max_length=20` + pattern, `max_depth ∈ [0,5]`.
- **OCR:** module-level singleton readers (`text_detector/ocrbase.py`, `paddleocrbase.py`) — models load once per process.

### 6.2 Remaining scalability gaps
- **In-process job store (no HA).** `store.py:_jobs` is a dict. A restart drops every running and recently-completed job; you cannot run two API replicas. The prior review's Redis/sqlite recommendation stands — the semaphore + TTL changes are a single-process mitigation, not a distributed solution.
- **No real queue.** Work is `asyncio.create_task`-ed straight from the route handler, gated only by the in-process semaphore. Adequate for one box; a Celery/RQ worker tier is still the path to back-pressure across hosts.
- **`_extract_page_chunked` `seen_refs`** — see P-01.
- **SSE flush race** — see §5.2; under heavy concurrency a re-connecting client can still miss a stage event between the status snapshot and the queue subscription, or lose a terminal event to the `sleep(0)` hack.

---

## 7. Security & Stability

### 7.1 Fixed
- **SSRF (encoded IPs + redirects).** `_ssrf_guard.py` parses decimal/hex/octal/IPv4-mapped forms, resolves hostnames, classifies against `_BLOCKED_NETWORKS` + Python's address attributes, and is installed on the *context* so it fires for every request including redirect targets. Node mirrors it with `_assertPublicUrl` + `setRequestInterception` + `_installSsrfInterceptor`.
- **Traceback leakage.** `runner.py` logs the full traceback server-side with an `error_id` and returns only `"Audit failed due to an internal error."` + the opaque id to clients (`models.py:JobStatusResponse.error_id`).
- **Auth + rate limiting.** `_AuthMiddleware` (`X-API-Key`, soft-mode when unset) attributes identity; `_RateLimitMiddleware` throttles 30 POST/identity/60s by API key (not spoofable `X-Forwarded-For`). `_SecurityHeadersMiddleware` adds `nosniff`/`DENY`/referrer policy.
- **Image-serving path safety.** `routes.py:get_job_image` canonicalises the requested path, checks membership in the job's recorded image set, enforces parent-directory containment, and `is_file()`.
- **Step-log corruption.** Per-path locks in `step_logger.py`.

### 7.2 Remaining
- **G1 — DNS rebinding (TOCTOU).** `assert_public_url` resolves at submit time; `_ssrf_guard` resolves again per-request — but neither *pins* the resolved IP to the connection Playwright/Chromium actually opens. An attacker controlling DNS TTL can answer "public" to the guard and "169.254.169.254" to the browser. True closure needs IP pinning (resolve once, force the connection to that IP).
- **G2 — dead weak guard in `routes.py`.** `build_ssrf_route_handler` (`routes.py:90-120`) uses the regex-only `_IP_HOST_RE` the last review explicitly called a bypass surface. It is currently unused; delete it before someone wires it.
- **CORS `allow_origins=["*"]`.** `main.py:192-198` — flagged in-code as "development." Must be an allow-list before production.
- **`submit_combined_audit` returns the live `_jobs[job_id]` dict** (`routes.py:238`) — a shared mutable returned straight to the serializer. Harmless with current FastAPI behaviour but fragile; return a snapshot.

### 7.3 Stability
- The `_fire_broadcast` / `sleep(0)` flush pattern (§5.2) is the most likely source of "audit looks stuck in the UI" reports.
- `runner.py`'s `sem._value` read will break on a CPython internals change — low probability, silent failure mode.

---

## 8. Refactoring Plan (status)

Ordered by correctness/safety win per unit of effort. Much shorter than last time — Sprints 1–5 did the heavy lifting.

### Sprint A — Cleanup & latent-risk removal — ✅ DONE (2026-05-14)
1. ✅ **Deleted `routes.py:build_ssrf_route_handler`** and the duplicated `_BLOCKED_NETWORKS`/`_ip_is_blocked`/`_is_non_public_ip`. `assert_public_url` now routes through the single canonical guard in `_ssrf_guard.py` (`_host_is_blocked`/`_parse_literal_ip`/`_resolve_hostname`), keeping the friendly "could not resolve" 400.
2. ✅ **Deleted the 0-byte `api/v1/combined.py`**; renamed `classifier/classfier.py` → `classifier/classifier.py` and fixed the import in `crawler.py`.
3. ✅ **Capped `seen_refs`** and sourced `max_passes` from `CrawlPolicy` (`max_scroll_passes`, `max_seen_refs`) in `universal_page._extract_page_chunked`.
4. ✅ **Promoted the `networkidle` timeout log** to `warning`.
5. ✅ **Removed the `sem._value` private access** in `runner.py` — `asyncio.Semaphore.locked()` is the public-API equivalent.

### Sprint B — Robustness — ✅ DONE (2026-05-14)
6. ✅ **Stage broadcasts are now drained deterministically.** `_fire_broadcast` registers each scheduled task in `_pending_broadcasts`; `runner._run_job`'s `finally` awaits `drain_broadcasts(job_id)` before `_close_subscribers` — the double `sleep(0)` hack is gone, and the registry also keeps a strong task reference so the loop can't GC a broadcast before it runs.
7. ✅ **Collapsed the per-image N+1** in `crawler.py` — one `img.evaluate` now returns the resolved accessible name, alt/title, and DOM context together (was 3 round-trips per `<img>`).
8. ✅ **Split `universal_extract.js`** into a shared helper preamble (`extract/common.js`) plus four focused extractors (`structural`, `geometry`, `dynamic`, `sensory`). `universal_page.py` composes them into separate `page.evaluate` payloads and runs them with per-extractor error isolation + an 8000-record-per-category cap, so one failing extractor no longer takes out all 7 categories.
9. ✅ **Tightened `policy_1_3_1`** — a new `SemanticContext.has_table_header_association` (computed in the relationship engine: cell is `<th>`, has `headers=`, or its row/column carries a `<th>`) drives a real verdict; an unassociated `<td>` is now `needs_review`, not an unconditional pass.

All 748 Python tests pass after Sprints A + B.

### Sprint C — Scale-out — DEFERRED
10. **Move `_jobs` to Redis or sqlite** — needs an infra decision; the in-process store with TTL eviction + per-job locks remains safe within a single process.
11. **Introduce a worker tier** (Celery/RQ) — adds an external dependency and changes deployment topology; the `_MAX_CONCURRENT_JOBS` semaphore bounds concurrency on a single box in the meantime.

### Sprint D — Architecture — DEFERRED
12. **Unify the rule model** (auditors emit `Finding(...)` directly; `findings.py` shrinks to a grouper) — a multi-week rewrite touching every auditor and converter; deferred to protect the passing test suite.
13. **Consolidate Node custom-checks vs audits** and the duplicated selector banks.

---

## 9. Improved Code Snippets

### 9.1 One canonical SSRF guard (kills F9 + G2)

```python
# routes.py — delete _BLOCKED_NETWORKS, _ip_is_blocked, _is_non_public_ip,
# build_ssrf_route_handler. Import the hardened guard instead.
from ka11y.crawler._ssrf_guard import _host_is_blocked

async def assert_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(400, f"scheme '{parsed.scheme}' not supported")
    host = parsed.hostname or ""
    if not host:
        raise HTTPException(400, "URL hostname is missing.")
    # _host_is_blocked already covers literals (decimal/hex/octal/IPv6),
    # localhost aliases, and full hostname resolution.
    if _host_is_blocked(host):
        raise HTTPException(400, f"hostname '{host}' is not allowed (private/reserved).")
```

### 9.2 Bound `seen_refs` and config-drive scroll passes (P-01)

```python
# universal_page.py
async def _extract_page_chunked(cls, page, *, page_url, output, policy=None):
    seen_refs: set[str] = set()
    max_passes = (policy.max_scroll_passes if policy else 4)
    SEEN_REFS_CAP = 5000
    ...
    for i in range(max_passes):
        await cls._extract_page(page, page_url=page_url, output=output, seen_refs=seen_refs)
        if len(seen_refs) > SEEN_REFS_CAP:
            logger.warning("[universal] seen_refs cap hit (%d); stopping scroll", len(seen_refs))
            break
        ...
```

### 9.3 Awaitable stage broadcast (fixes the `sleep(0)` race)

```python
# stage_events.py — make the broadcast awaitable so callers can drain it.
async def stage_complete(job_id: str, name: str, findings_count: int = 0) -> None:
    _record_stage(job_id, name, "completed", findings_count)
    await _broadcast(job_id, "stage_complete", _payload(job_id, name, findings_count))

# runner.py finally: — replace the two sleep(0) calls with an explicit drain.
async def _drain_pending_broadcasts() -> None:
    pending = [t for t in asyncio.all_tasks() if t.get_name().startswith("broadcast:")]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
```

### 9.4 Single per-image evaluate (P-02)

```python
# crawler.py — one round-trip instead of two.
meta = await img.evaluate("""el => {
    const labelledby = el.getAttribute('aria-labelledby');
    let resolved = null;
    if (labelledby) {
        resolved = labelledby.trim().split(/\\s+/)
            .map(id => document.getElementById(id)?.textContent.trim() || '')
            .filter(Boolean).join(' ') || null;
    }
    if (!resolved) {
        const al = el.getAttribute('aria-label');
        if (al && al.trim()) resolved = al.trim();
    }
    const parent = el.closest('a,button,header,footer,nav,main,section,article') || el.parentElement;
    return {
        resolved_label: resolved,
        role: el.getAttribute('role') || '',
        aria_hidden: el.getAttribute('aria-hidden') || '',
        parent_tag: parent ? parent.tagName.toLowerCase() : '',
        clickable: !!el.closest("a,button,[role='button'],[onclick]"),
    };
}""")
```

### 9.5 Real 1.3.1 data-table relationship check

```python
# policy_1_3_1.py — confirm relationships, not just membership.
if element.semantics.is_in_data_table:
    has_assoc = (
        element.semantics.described_by_text          # headers="" resolved
        or "rowheader" in element.semantics.ancestor_roles
        or "columnheader" in element.semantics.ancestor_roles
        or element.semantics.has_scope_or_headers     # extractor must surface this
    )
    if not has_assoc:
        return self._needs_review(
            element, "table_cell_unassociated",
            "Data-table cell has no header association (scope/headers/th). "
            "Verify the relationship is programmatically determinable.",
        )
    return self._pass(element, "table_context", "Cell is associated with table headers.")
```

---

## 10. Final Verdict

### How far it's come

The 2026-05-06 review described a system "undermined by data-loss bugs, engine-level exception swallowing, broken resource economics, and security gaps." Every one of those is now addressed at the structural level: the engine surfaces faults, the field-map registry plus its CI test closes the data-loss class, a bounded browser pool and job semaphore replace the per-crawler Chromium explosion, and the SSRF guard handles encoded IPs and redirects. The accuracy bugs that were *concrete* — the 1.4.6 always-false compare, the 1.3.1 CSS-vs-attribute confusion, the 2.4.13 inverted logic, the contrast alpha-splitting parser — are fixed and verified by reading the code. This is a real engineering response, not a patch job.

### What still separates it from "perfect"

1. **The dual rule pipeline.** `rules/*` auditors and `pipeline/decisions/*` policies still speak different dialects, bridged by a 1543-line `findings.py`. The registry stopped the silent failures; it did not remove the change-amplification. Until auditors emit `Finding(...)` directly, every rule edit is a three-file edit.
2. **Single-process state.** The job store is a module dict. TTL eviction and per-job locks make it *safe within one process*; they do not make it *survivable across a restart* or *scalable across replicas*.
3. **Residual heuristic accuracy.** 2.5.4's motion classification, 2.5.1's handler-length proxy, and 1.3.1's table rubber-stamp are still pattern-matching where the SC demands intent verification.
4. **Self-inflicted latent risk.** Dead code (`combined.py`, `build_ssrf_route_handler`), a typo'd filename, and duplicated security constants are cheap to delete and expensive to trip over later.
5. **One genuine open security item.** DNS rebinding is not closed — the guard and the browser resolve independently, with no IP pinning between them.

### What "perfect" still looks like

A 95+/100 ka11y has: **one typed `Finding` model** emitted by auditors directly (no translation layer); **a distributed job store + worker tier** so the API is replica-safe and restart-safe; **intent-verifying WCAG checks** instead of keyword heuristics; **IP-pinned SSRF**; **one focused extractor per concern**; and **zero dead/duplicated code paths**.

The single highest-leverage day of work now is **Sprint A** — deleting the dead weak SSRF handler and the duplicated guards, capping `seen_refs`, and removing the `sem._value` hack. None of it is hard; all of it removes a latent regression or a silent failure mode. After Sprint A the rating is ~86; after Sprint D (the rule-model unification) it clears 95.
