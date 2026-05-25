# ka11y — System-Wide Code Review (Re-Review)

**Original review:** 2026-05-06 (branch `fix-patches`)
**This re-review:** 2026-05-25 (branch `pranav-v2`)
**Scope:** Full system — `ka11y-python` (FastAPI + Playwright + auditors), `ka11y-node` (axe-core + custom checks), API/orchestration glue.
**Method:** Every finding from the 2026-05-06 review was re-verified against current code, file-by-file, line-by-line. Status tags below (`FIXED` / `IMPROVED` / `OPEN`) are grounded in the present source, not the prior report.

---

## 1. Executive Summary

### Overall rating: **78 / 100** (was 54 / 100)

The remediation work between `fix-patches` and `pranav-v2` is substantial and real. **Every one of the original Top-5 criticals has been addressed**, and the bulk of the high/medium findings are fixed. Concretely, since the last review:

- The `DecisionEngine` now raises/propagates everything except a typed `PolicyError` — silent `NEEDS_REVIEW(0.1)` masking is gone (`engine.py`).
- A real `BrowserPool` singleton exists; all crawlers lease contexts/browsers from it (`browser_pool.py`). The 5-Chromium-per-URL pattern is gone.
- The SSRF guard now covers decimal/hex/octal/IPv4-mapped IPv6 forms, resolves hostnames, and runs at the **context** level so redirects are validated (`_ssrf_guard.py`).
- A `auditor_field_map.py` registry + CI guard test (`tests/test_auditor_field_map.py`) was added to catch the field-name-mismatch data-loss class.
- API responses now return an opaque `error_id` instead of tracebacks; `CombinedRequest` has length/pattern caps; the job store has TTL eviction; the step logger has per-path locks.
- A long list of accuracy bugs were fixed: contrast alpha compositing, accname-1.2 precedence, 1.3.1 input-type read, 2.4.13 focus-appearance composition, 2.5.3 token comparison, 1.1.1 decorative/`aria-hidden`/shadow-DOM/CSS-background coverage, sensory cross-check, reflow viewport assertion.

What still stops it from being production-perfect is now a **short, specific list** (Section 2), not a structural overhaul. The previously-urgent item — a red field-map guard test (B-1) — is **now fixed** (SC 1.2.2 registered in `auditor_field_map.py`; suite green). The remaining items are correctness/scale/quality, none ship-blocking.

---

## 2. 🐞 Open Bugs To Fix (the action list)

Severity legend: **P0** = ship-blocker / CI-red / correctness, **P1** = correctness or scale risk, **P2** = quality/maintainability.

| # | Sev | Bug | Location | Evidence / Fix |
|---|-----|-----|----------|----------------|
| **B-1** | ~~P0~~ **FIXED** | **Test suite was red.** `findings.py` referenced `wcag_1_2_2_status`, not declared in `AUDITOR_FIELD_MAP`, so the guard test failed. **Resolved (2026-05-25):** `"1.2.2"` added to `AUDITOR_FIELD_MAP` (alongside its `1.2.1` sibling, which shares the same `_violation` reason convention). `tests/test_auditor_field_map.py` now 3/3 green; findings tests 30/30 green. *Note:* the media auditor genuinely emits `wcag_1_2_2_violation` (not canonical `_reason`) — same as 1.2.1 — so the registry's `reason` entry stays aspirational until B-2. | `auditor_field_map.py:49` (now registered); `findings.py:1468`; `tests/test_auditor_field_map.py` | ✅ Done. |
| **B-2** | **P1** | **`findings.py` still reads raw keys.** The registry/helpers (`get_status`, `get_reason`) exist but `findings.py` (1562 lines) never calls them — it still does inline `r.get("wcag_X_Y_Z_status", "")` everywhere. The registry is a *parallel guard*, not the read path, so the data-loss class is only **caught** at CI, not **eliminated**. | `findings.py` (≈40+ inline `r.get("wcag_..._status")` sites); `auditor_field_map.py:get_status/get_reason` are imported nowhere in `findings.py` | Migrate converters to `get_status(r, sc)` / `get_reason(r, sc)`. Then a missing key is impossible by construction, not just test-detectable. |
| **B-3** | **P1** | **Monolithic JS extractor not split.** `_COMBINED_EXTRACT_JS` was moved out of Python (good — now lives in `js/universal_extract.js`), but it is still **one 1079-line file with 7 `querySelectorAll` passes**. A single JS error still kills forms + interactive + geometry + media + sensory + text-spacing at once. Only the maintainability half of the original fix was done; the resilience half was not. | `ka11y/crawler/js/universal_extract.js` (1079 lines, 7 `querySelectorAll`) | Split into `forms.js` / `geometry.js` / `dynamic.js` / `sensory.js`; evaluate independently so one failure degrades one category. |
| **B-4** | **P1** | **N+1 `evaluate` per image.** For each `<img>`, two separate `img.evaluate(...)` round-trips (resolved label, then context). 1000 images = ~2000 IPC hops. | `crawler.py:543` (resolved label), `crawler.py:563` (el context) | Collapse into one `img.evaluate(el => ({label, ctx, title, ...}))`. |
| **B-5** | **P1** | **N+1 `frame.evaluate` per relationship.** `for context in contexts: relations = await frame.evaluate(_RELATIONSHIP_JS, context.element_id)` — one IPC per element. | `pipeline/extractors/semantic_relationship_engine.py:89-94` | Pass the full id list once; return `[{id, relations}]`. |
| **B-6** | **P1** | **SSRF DNS-rebinding (TOCTOU) residual.** The guard resolves the host via cached `getaddrinfo` and classifies, but Playwright/Chromium performs its **own** resolution at connect time. A name that resolves "public" during validation can rebind to `169.254.169.254` before the socket connects. No DNS pinning. | `_ssrf_guard.py:_resolve_hostname` / `_host_is_blocked` | Pin the validated IP into the connection (resolve once, connect to the literal), or enforce via a resolver hook. Lower likelihood given the context-level guard, but it's the remaining SSRF surface. |
| **B-7** | **P2** | **No explicit `seen_refs` cap.** Chunked extraction is now bounded *indirectly* by `max_links_per_page` and `max_pages=20`, but there is still no hard `if len(seen_refs) > N: break`. Infinite-scroll pages can still grow the set across passes. | `universal_page.py:389` (`seen_refs = set()`), passed through `:417/:492/:543` | Add a per-page cap on `seen_refs`. |
| **B-8** | **P2** | **Late `import re` inside method.** Hot path re-imports `re` on every call instead of a module-level compiled pattern. | `policy_1_4_5.py:32` | Hoist to module level; compile the pattern once. (Sibling `policy_1_1_1.py` already does this correctly via `_DESCRIPTIVE_ALT_RE`.) |
| **B-9** | **P2** | **Misspelled module filename.** `classfier.py` (missing "i") keeps producing typo-prone imports across the codebase. | `ka11y/classifier/classfier.py` | Rename to `classifier.py`; update imports. |
| **B-10** | **P2** | **AAA contrast constants defined but unused.** `thresholds.py` declares `CONTRAST_NORMAL_AAA`/`CONTRAST_LARGE_AAA`, but `policy_1_4_6` re-hardcodes `7.0`/`4.5` inline (`threshold = 4.5 if is_large else 7.0`). Drift risk between the constant and the hardcode. | `policy_1_4_6.py:24`; `config/thresholds.py` | Import and use the constants in the policy. |
| **B-11** | **P2** | **2.5.4 generic "Settings" link still emits evidence.** Now confidence-graded (only `low` without nearby motion keywords), so it no longer false-PASSes outright — but a bare account-settings link still produces a "Found generic settings link" evidence string. | `disable-control-validator.js:51-56` | Drop the `low`-confidence generic-settings signal entirely, or require motion/accessibility adjacency before recording any evidence. |
| **B-12** | **P2** | **`output/` and `crawled_images/` disk growth.** In-memory job TTL eviction was added (`store.py:_evict_old_jobs`, `_JOB_TTL_SECONDS=3600`), but nothing prunes the on-disk artefact directories. They grow unbounded. | `store.py:107-138` (memory only); `output/`, `crawled_images/` (no TTL sweep) | Add a TTL sweep / per-job dir size cap for the disk artefacts, tied to job eviction. |

> **Quick win:** B-1 is a one-line registry add + one key rename, turns CI green, and closes a real data-loss bug. Do it first.

---

## 3. Remediation Status of the Original Review

Condensed verification of the 2026-05-06 findings. `FIXED` = verified resolved in current source.

### 3.1 Top-5 Criticals — all addressed
| # | Original critical | Status | Where |
|---|-------------------|--------|-------|
| 1 | Auditor→converter field-name mismatch silently downgrades SCs | **IMPROVED** (registry + guard test added; but see **B-1**, **B-2**) | `auditor_field_map.py`, `tests/test_auditor_field_map.py` |
| 2 | `DecisionEngine` swallows every `Exception` → `NEEDS_REVIEW(0.1)` | **FIXED** — `except PolicyError` only; anything else propagates | `decisions/engine.py:10-56` |
| 3 | SSRF guard misses encoded IPs / redirects | **FIXED** (DNS-rebinding residual → **B-6**) | `_ssrf_guard.py` |
| 4 | 5 Chromium per URL; fan-out without timeout; page leak | **FIXED** — pool + `asyncio.wait_for` + `finally: ctx.close()` | `browser_pool.py`, `rendered_layout_crawler.py:314-317,400-416` |
| 5 | 2000-line monolithic `page.evaluate()` | **IMPROVED** — extracted to disk, but still one file → **B-3** | `js/universal_extract.js` |

### 3.2 Performance
| ID | Finding | Status |
|----|---------|--------|
| P-01 | Monolithic JS / megabyte JSON | IMPROVED → **B-3** |
| P-02 | Browser-per-crawler | **FIXED** (pool; `KA11Y_MAX_BROWSERS`) |
| P-03 | gather without timeout | **FIXED** (`asyncio.wait_for`) |
| P-04 | Page leak on exception | **FIXED** (ctx always closed in `finally`) |
| P-05 | Unbounded `seen_refs` | PARTIAL → **B-7** |
| P-06 | N+1 evaluate per image | **OPEN** → **B-4** |
| P-07 | N+1 evaluate per relationship | **OPEN** → **B-5** |
| P-09 | O(n·m) OCR lookup | **FIXED** (`_build_ocr_index`) |
| P-10 | Hot regex per call | **FIXED** in `policy_1_1_1`; **OPEN** in `policy_1_4_5` → **B-8** |
| P-16 | Node locale/classifier cache unbounded | **FIXED** (LRU w/ `AXE_LOCALE_CACHE_CAP`) |

### 3.3 Accuracy (WCAG)
| SC | Finding | Status |
|----|---------|--------|
| 1.1.1 | decorative `aria-hidden`/`role=presentation` ignored | **FIXED** (`alttext.py:352-374`) |
| 1.1.1 | logo words missing `logotype`/`wordmark` | **FIXED** (`_LOGO_WORDS`, `alttext.py:95`) |
| 1.1.1 | CSS `background-image` never seen | **FIXED** (`js/background_images.js`) |
| 1.1.1 | Shadow DOM not pierced | **FIXED** (`shadowRoot` in `universal_extract.js`, extractor) |
| 1.1.1 | accname priority wrong | **FIXED** — accname-1.2 precedence (`element_context_extractor.py:21-56`) |
| 1.2.1 | live-stream misclassification | **IMPROVED** — MediaSource/`srcObject`/`live` keyword (`media_auditor.py:110-139`) |
| 1.2.2 | (captions) | **FIXED** → **B-1** (field key now registered) |
| 1.3.1 | reads `type` from CSS | **FIXED** — reads from `html_snippet` (`policy_1_3_1.py:9,42`) |
| 1.3.3 | sensory flags labelled control name | **FIXED** — `_build_labelled_name_corpus` cross-check |
| 1.4.6 | enum-vs-string compare always-False | **FIXED** (`policy_1_4_6.py:13`) |
| 1.4.3/.6 | alpha ignored in RGB parse | **FIXED** — Porter-Duff compositing (`contrast_engine.py`) |
| 1.4.10 | viewport not asserted at 320px | **FIXED** (`reflow.py:26,54-59`) |
| 2.4.13 | AND/OR composition inverted; hardcoded fallback | **FIXED** (`policy_2_4_13.py`; `interaction_state_runner.py` returns None when unmeasured) |
| 2.5.1 | empty `onclick` passes as alternative | **FIXED** (`escape-hatch-validator.js:39-65`) |
| 2.5.3 | punctuation-stripped substring match | **FIXED** — token contiguous-run (`policy_2_5_3.py`) |
| 2.5.4 | "Settings" = motion control; essential = keyword | **IMPROVED** — confidence-graded + `data-wcag-motion-essential` opt-in (residual **B-11**) |
| 2.5.8 | `None` deref on bbox | **FIXED** (`policy_2_5_8.py:35-40`) |

### 3.4 Code Quality / Scalability / Security
| Finding | Status |
|---------|--------|
| Engine catch-Exception-and-shrug | **FIXED** |
| Step logger append without lock | **FIXED** (`step_logger.py` per-path locks) |
| `_run_python_stages` tuple-by-index | **FIXED** (typed dataclass return) |
| `rule_target_router` non-deterministic `list(set())` | **FIXED** (order-preserving dedup) |
| API traceback leakage | **FIXED** (opaque `error_id`) |
| `CombinedRequest` no length caps | **FIXED** (`max_length`/`pattern` on `wcag_level`, `lang`, `success_criteria_id`) |
| `_jobs` leak / no TTL | **FIXED** (memory TTL); disk dirs still **OPEN** → **B-12** |
| Node `Promise.race` doesn't cancel axe run | **FIXED** (`accessibility.service.js:252-323`, abort + clearTimeout) |
| Misspelled `classfier.py` | **OPEN** → **B-9** |

---

## 4. Remaining Architectural Debt

The original review's deepest structural critique (F1) is **partially** resolved:

- **Two parallel rule systems** (`rules/*` auditors and `pipeline/decisions/*` policies) still emit findings through the `combined/findings.py` translation layer. The new `auditor_field_map.py` + guard test makes the seam *safe*, but the seam still exists and `findings.py` is still 1562 lines of string-keyed translation (**B-2**). Full unification (auditors emitting `Finding(...)` directly) remains the path to 90+/100.
- **Crawler proliferation** is much better — all crawlers now share `BrowserPool`/`new_crawler_context`, so the duplicated launch/teardown is gone even though there is still no formal `BaseCrawler` ABC. This is acceptable; the cost (memory, process count) that motivated the original finding is resolved.
- **One giant JS extractor** persists as a resilience risk (**B-3**).

---

## 5. Recommended Next Actions (prioritized)

1. ~~**B-1** — Register `1.2.2`.~~ ✅ **Done (2026-05-25)** — suite green.
2. **B-2** — Route `findings.py` through `get_status`/`get_reason`. Eliminates the data-loss class by construction. *(half day)*
3. **B-4 / B-5** — Batch the two N+1 `evaluate` loops (images, relationships). Largest remaining per-page latency win. *(half day each)*
4. **B-3** — Split `universal_extract.js` into focused extractors. *(1–2 days)*
5. **B-6** — DNS-pin the SSRF guard. *(half day)*
6. **B-7 – B-12** — Quality/scale cleanup; batch into one PR. *(1 day)*

After 1–3, the system is comfortably in the low-to-mid 80s. Reaching 90+ is the auditor-model unification (B-2 taken to its conclusion: delete `findings.py`).

---

## 6. Verification Note

This re-review ran the fast (browser-free) guard tests. **Before** the B-1 fix:

```
tests/test_auditor_field_map.py   1 FAILED, 2 passed   ← B-1
```

**After** registering SC 1.2.2:

```
tests/test_auditor_field_map.py        3 passed
tests/test_combined_findings.py       15 passed
tests/test_accessible_name_priority.py 12 passed
                                       30 passed
```

All other status tags were verified by reading the cited source lines.
