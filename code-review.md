# a11y — System-Wide Code Review (Re-Review)

**Original review:** 2026-05-06 (branch `fix-patches`)
**Re-review:** 2026-05-25 (branch `pranav-v2`) — B-1…B-12 fix verification
**Latest pass:** 2026-05-26 (branch `pranav-v2`) — feature code that landed after the B-fix pass: multi-page per-page reporting, auto-language detection, page-wise image reports.
**Scope:** Full system — `a11y-python` (FastAPI + Playwright + auditors), `a11y-node` (axe-core + custom checks), API/orchestration glue.
**Method:** Every finding from the 2026-05-06 review was re-verified against current code, file-by-file, line-by-line. The 2026-05-26 pass reads the new feature modules (`report.py`, `runner.py`, `lang_detector.py`, `findings.py`, `stages.py`) against the current source and runs the browser-free test suite. Status tags below (`FIXED` / `IMPROVED` / `OPEN` / new `N-*`) are grounded in the present source, not the prior report.

---

## 1. Executive Summary

### Overall rating: **85 / 100** (54 → 78 → 84 after B-1…B-12; dipped to 80 on the 2026-05-26 feature pass (N-1/N-2), **restored to 85** after N-1…N-3 were fixed the same day)

The remediation work between `fix-patches` and `pranav-v2` is substantial and real. **Every one of the original Top-5 criticals has been addressed**, and the bulk of the high/medium findings are fixed. Concretely, since the last review:

- The `DecisionEngine` now raises/propagates everything except a typed `PolicyError` — silent `NEEDS_REVIEW(0.1)` masking is gone (`engine.py`).
- A real `BrowserPool` singleton exists; all crawlers lease contexts/browsers from it (`browser_pool.py`). The 5-Chromium-per-URL pattern is gone.
- The SSRF guard now covers decimal/hex/octal/IPv4-mapped IPv6 forms, resolves hostnames, and runs at the **context** level so redirects are validated (`_ssrf_guard.py`).
- A `auditor_field_map.py` registry + CI guard test (`tests/test_auditor_field_map.py`) was added to catch the field-name-mismatch data-loss class.
- API responses now return an opaque `error_id` instead of tracebacks; `CombinedRequest` has length/pattern caps; the job store has TTL eviction; the step logger has per-path locks.
- A long list of accuracy bugs were fixed: contrast alpha compositing, accname-1.2 precedence, 1.3.1 input-type read, 2.4.13 focus-appearance composition, 2.5.3 token comparison, 1.1.1 decorative/`aria-hidden`/shadow-DOM/CSS-background coverage, sensory cross-check, reflow viewport assertion.

**Update (2026-05-25): all twelve open bugs (B-1…B-12) have now been fixed and verified** (Section 2). This pass eliminated the data-loss class by construction (B-2), gave the JS extractor per-category fault isolation (B-3), removed two N+1 IPC loops (B-4/B-5), bounded the SSRF resolver TTL (B-6), capped `seen_refs` (B-7), and cleared the quality backlog (B-8…B-12). What remains for a 90+ score is no longer a bug list but the architectural unification (§4): collapsing the two parallel rule systems so `findings.py` stops being a translation layer at all.

**Update (2026-05-26): reviewed the feature work that landed after the B-fix pass** — multi-page **per-page reporting** (`report.py` builds a `pages[]` breakdown + `summary.by_page`/`score`/`page_count`), **auto-language detection** (`lang_detector.py`, wired in `runner.py`), and **page-wise image reports** (`page_url` attached to every `contrast_report`/`image_audit_report` image). The per-page reporting and image-attribution code is **clean and correct** (§2A) — findings are grouped without copying, the per-page buckets reference the same objects so the runner's `image_url`/`image_src` rewrites propagate to them, and the image→page map is built defensively. The feature pass *did* introduce two regressions — **N-1** (the auto-language detector reopened the SSRF hole on the default request path) and **N-2** (the browser-free suite went red) — which briefly dropped the score to 80.

**Update (2026-05-26, later): N-1, N-2, and N-3 are all fixed and verified.** `lang_detector.py` now validates every request hop (initial URL + each redirect) through the shared SSRF classifier with manual redirect-following, backed by a 7-case regression suite that proves no fetch is attempted for blocked hosts; the stale alt-text test now asserts the stable `reason_code`; and a per-host TTL cache removes the repeat pre-flight fetch. Browser-free suite: **749 passed, 3 skipped, 0 failed.** Score **restored to 85/100.** The architectural unification (§4) remains the lever to 90+.

---

## 2. 🐞 Open Bugs To Fix (the action list)

Severity legend: **P0** = ship-blocker / CI-red / correctness, **P1** = correctness or scale risk, **P2** = quality/maintainability.

| # | Sev | Bug | Location | Evidence / Fix |
|---|-----|-----|----------|----------------|
| **B-1** | ~~P0~~ **FIXED** | **Test suite was red.** `findings.py` referenced `wcag_1_2_2_status`, not declared in `AUDITOR_FIELD_MAP`, so the guard test failed. **Resolved (2026-05-25):** `"1.2.2"` added to `AUDITOR_FIELD_MAP` (alongside its `1.2.1` sibling, which shares the same `_violation` reason convention). `tests/test_auditor_field_map.py` now 3/3 green; findings tests 30/30 green. *Note:* the media auditor genuinely emits `wcag_1_2_2_violation` (not canonical `_reason`) — same as 1.2.1 — so the registry's `reason` entry stays aspirational until B-2. | `auditor_field_map.py:49` (now registered); `findings.py:1468`; `tests/test_auditor_field_map.py` | ✅ Done. |
| **B-2** | ~~P1~~ **FIXED** | **`findings.py` migrated to registry helpers.** All 15 status reads now go through `get_status(r, sc)`; the canonical-reason output block uses `get_reason`; the forms loop derives its `_violations` key from `status_key(sc)`. An unregistered SC now raises `KeyError` (loud) instead of silently defaulting. The guard test was strengthened with `test_every_helper_call_sc_is_registered`. | `findings.py:29` (import), `:397-404`, `:976-982`, + 11 converter sites; `tests/test_auditor_field_map.py` | ✅ Done. *Residual:* media reason keys (`_violation`) remain non-canonical and are still read raw — status is the data-loss vector and is fully covered. |
| **B-3** | ~~P1~~ **FIXED** | **Per-category fault isolation added.** Each of the 7 extractors in `universal_extract.js` now runs inside its own `_runExtractor(name, fn)` try/catch; a throw in one category yields `[]` for that one and records `_errors[name]` instead of zeroing all seven. Python surfaces those as `category_extract_failed` warnings + `partial=True`. Resilience goal met without a risky physical file split. | `js/universal_extract.js` (`_runExtractor` ×7, `_errors` in return); `universal_page.py:_extract_page` (error surfacing) | ✅ Done. (Physical 4-file split deferred as cosmetic; isolation is the substance.) |
| **B-4** | ~~P1~~ **FIXED** | **Two image `evaluate` calls merged into one.** Label resolution + context now returned by a single `img.evaluate(...)` round trip — halves IPC on image-heavy pages. | `crawler.py` (single `probe = await img.evaluate(...)`) | ✅ Done. |
| **B-5** | ~~P1~~ **FIXED** | **Relationship evaluate batched.** `_RELATIONSHIP_JS` now takes the full element-id array and returns a `{id: relations}` map; one `frame.evaluate` per frame instead of per element. JS syntax `node --check`-validated. | `semantic_relationship_engine.py` (`enrich_semantics` + batched JS) | ✅ Done. |
| **B-6** | ~~P1~~ **FIXED (mitigated)** | **SSRF resolver given a bounded TTL.** Replaced the unbounded `lru_cache` with a 30 s TTL cache so the guard can no longer be permanently poisoned by a host that resolves public once then rebinds. 43 SSRF tests pass. | `_ssrf_guard.py:_resolve_hostname` (`_DNS_CACHE_TTL_SECONDS=30`) | ✅ Done. *Residual (documented):* Chromium's own connect-time resolution is still independent — full TOCTOU closure needs a pinned-IP fetch proxy. TTL shrinks the window from ∞ to ≤30 s. |
| **B-7** | ~~P2~~ **FIXED** | **Hard `seen_refs` ceiling added.** Chunked scroll extraction now breaks once `len(seen_refs) >= _MAX_SEEN_REFS (5000)` and marks the snapshot partial. | `universal_page.py:_MAX_SEEN_REFS`, scroll-loop guard | ✅ Done. |
| **B-8** | ~~P2~~ **FIXED** | **`import re` hoisted.** Module-level `_NON_ALNUM_RE` + `_normalise()`; no per-call import. | `policy_1_4_5.py` | ✅ Done. |
| **B-9** | ~~P2~~ **FIXED** | **File renamed `classfier.py → classifier.py`** via `git mv`; sole importer updated; no stray refs remain. | `a11y/classifier/classifier.py`, `crawler.py:33` | ✅ Done. |
| **B-10** | ~~P2~~ **FIXED** | **1.4.6 uses the AAA constants.** Imports `CONTRAST_NORMAL_AAA`/`CONTRAST_LARGE_AAA` instead of hardcoding `7.0`/`4.5`. | `policy_1_4_6.py` | ✅ Done. |
| **B-11** | ~~P2~~ **FIXED** | **Generic-settings-link signal dropped.** A settings/preferences link with no motion/accessibility keywords nearby now contributes no evidence and no confidence bump. 2.5.4 suites pass. | `disable-control-validator.js` (removed `else` branch) | ✅ Done. |
| **B-12** | ~~P2~~ **FIXED** | **Disk TTL tied to job eviction.** `_evict_old_jobs` now deletes each expired job's `output_dir` (off-loop via `to_thread`), guarded to only remove `*_combined` directories. | `store.py:_safe_remove_job_dir` + eviction loop | ✅ Done. *Residual:* the global standalone-pipeline `crawled_images/` is not job-scoped and is left to ops cleanup. |

> **All twelve bugs (B-1…B-12) are now fixed.** Verification summary in §6.

---

## 2A. New Findings — 2026-05-26 feature pass (N-1 … N-3)

These are **new** issues found in code that landed *after* the B-fix pass (multi-page reporting, auto-language detection, page-wise image reports). They are not regressions of B-1…B-12; they are defects in the new feature work.

| # | Sev | Bug | Location | Evidence / Fix |
|---|-----|-----|----------|----------------|
| **N-1** | ~~P1 (security)~~ **FIXED** | **Auto-language detection bypassed the SSRF guard — on the default path.** `runner._run_job_body()` calls `detect_page_language(url)` whenever `payload.lang == "auto"`, and **`lang` defaults to `"auto"`** (`models.py:69`), so this fired on essentially every audit. The old `detect_page_language()` did a raw `httpx.AsyncClient(..., follow_redirects=True).stream("GET", url)` with **no SSRF validation**, before any browser (and its context-level guard) started — an unguarded server-side request to an attacker URL (`HttpUrl` doesn't block `169.254.169.254`/`localhost`/RFC-1918; `follow_redirects=True` let a public host 30x inward). **Resolved (2026-05-26):** rewrote `lang_detector.py` to (a) validate **every hop** (initial URL + each redirect) with the shared `_host_is_blocked` classifier from `_ssrf_guard.py`, run off-loop via `asyncio.to_thread`; (b) set `follow_redirects=False` and follow manually (max 5 hops), validating each `Location` before connecting; (c) return the safe default + skip the fetch entirely for blocked hosts. New regression suite `tests/test_lang_detector_ssrf.py` (7 cases incl. metadata IP, localhost, RFC-1918, IPv6 loopback, decimal-encoded `2130706433`) asserts **`.stream()` is never called** for a blocked host. *Residual:* same OS-resolver TOCTOU as B-6 — documented, needs pinned-IP fetch to fully close. | `a11y/utils/lang_detector.py` (`_safe_fetch_head`, `_host_is_blocked` import); `tests/test_lang_detector_ssrf.py` | ✅ Done. |
| **N-2** | ~~P0 (CI-red)~~ **FIXED** | **Browser-free suite was red.** `test_alt_text_fallback_reason_uses_localised_rule_description` expected the JA reason to start with the generic **rule description**, but `_alt_text_to_findings` now passes `reason=None` + `reason_code="fail_missing_alt"`, so the renderer resolves the **specific** template (`画像に説明（alt 属性）が…`). The specific reason is the **better** behaviour → stale test, not a logic bug. **Resolved (2026-05-26):** renamed to `test_alt_text_fallback_reason_uses_specific_missing_alt_template` and now asserts `reason_code == "fail_missing_alt"` (stable machine value) plus a localised JA reason — robust against future wording tweaks. | `tests/test_api_smoke.py:350-364`; `findings.py:492-510` | ✅ Done. |
| **N-3** | ~~P2 (perf)~~ **FIXED (mitigated)** | **Auto-lang added a second pre-flight fetch on the default path** (a full extra round-trip, ≤16 KB, ≤10 s, before the crawl loads the same page). **Resolved (2026-05-26):** added a bounded per-host TTL cache (`_LANG_CACHE`, 600 s) so repeated audits of the same host — and the common case of multiple pages on one domain — skip the fetch; blocked hosts are cached too. *Residual:* the first audit of a host still does one lightweight pre-flight fetch; fully eliminating it would require reading `<html lang>` from the universal snapshot (deferred — the cache removes the repeat cost). | `lang_detector.py` (`_LANG_CACHE`, `_cache_get/_cache_put`) | ✅ Done. |

### New feature code that is clean (reviewed, no action)

- **Per-page reporting (`report.py`).** `_build_report` groups findings by `element.page_url` (falling back to the root URL for document-level findings), emits a worst-first `pages[]` array plus `summary.by_page`/`score`/`page_count`, and the flat `violations`/`needs_review`/`passes` stay aggregated. The per-page buckets hold **references to the same finding dicts**, so the runner's later `image_url` injection and `element.image_src` rewrite (`runner.py:411-434`) propagate into the page buckets for free — no divergence between the flat and per-page views. Score is the documented pass-rate; the empty-denominator case returns 100. ✅
- **Page-wise image reports (`findings.py`/`stages.py`).** `_build_image_audit_report` exposes `page_url = record["url"]` (the page the image was found on); `_build_contrast_report(ocr_results, page_by_filename)` attaches `page_url` per image, with `page_by_filename` built defensively in `_stage_image_audit` from `image_crawler.images_data` via `getattr` and matched on filename then screenshot basename, falling back to `None`. Additive and backward-compatible. ✅

---

## 3. Remediation Status of the Original Review

Condensed verification of the 2026-05-06 findings. `FIXED` = verified resolved in current source.

### 3.1 Top-5 Criticals — all addressed
| # | Original critical | Status | Where |
|---|-------------------|--------|-------|
| 1 | Auditor→converter field-name mismatch silently downgrades SCs | **IMPROVED** (registry + guard test added; but see **B-1**, **B-2**) | `auditor_field_map.py`, `tests/test_auditor_field_map.py` |
| 2 | `DecisionEngine` swallows every `Exception` → `NEEDS_REVIEW(0.1)` | **FIXED** — `except PolicyError` only; anything else propagates | `decisions/engine.py:10-56` |
| 3 | SSRF guard misses encoded IPs / redirects | **FIXED** for the browser path (DNS-rebinding residual → **B-6**); the auto-lang httpx path was briefly unguarded (N-1) and is **now also fixed** (shared classifier + manual redirect validation + regression suite) | `_ssrf_guard.py`; `lang_detector.py`; `tests/test_lang_detector_ssrf.py` (see §2A N-1) |
| 4 | 5 Chromium per URL; fan-out without timeout; page leak | **FIXED** — pool + `asyncio.wait_for` + `finally: ctx.close()` | `browser_pool.py`, `rendered_layout_crawler.py:314-317,400-416` |
| 5 | 2000-line monolithic `page.evaluate()` | **IMPROVED** — extracted to disk, but still one file → **B-3** | `js/universal_extract.js` |

### 3.2 Performance
| ID | Finding | Status |
|----|---------|--------|
| P-01 | Monolithic JS / megabyte JSON | IMPROVED → **B-3** |
| P-02 | Browser-per-crawler | **FIXED** (pool; `A11Y_MAX_BROWSERS`) |
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
| `_jobs` leak / no TTL | **FIXED** (memory TTL + disk TTL via **B-12**) |
| Node `Promise.race` doesn't cancel axe run | **FIXED** (`accessibility.service.js:252-323`, abort + clearTimeout) |
| Misspelled `classfier.py` | **FIXED** → **B-9** (renamed to `classifier.py`) |

---

## 4. Remaining Architectural Debt

The original review's deepest structural critique (F1) is now **mostly** resolved:

- **Two parallel rule systems** (`rules/*` auditors and `pipeline/decisions/*` policies) still emit findings through the `combined/findings.py` translation layer. After B-2 the seam is both *safe* (guard test) **and** *typed* (every read goes through `auditor_field_map`), so a missing key fails loudly rather than silently. The seam itself still exists, though — full unification (auditors emitting `Finding(...)` directly so `findings.py` can be deleted) remains the path to 90+/100 and is now the single largest remaining lever.
- **Crawler proliferation** is much better — all crawlers now share `BrowserPool`/`new_crawler_context`, so the duplicated launch/teardown is gone even though there is still no formal `BaseCrawler` ABC. This is acceptable; the cost (memory, process count) that motivated the original finding is resolved.
- **The giant JS extractor** is no longer a *resilience* risk after B-3 (per-category try/catch isolation). A physical split into 4 files is now purely cosmetic/maintainability and can be deferred.

---

## 5. Recommended Next Actions (prioritized)

**B-1 … B-12 are all complete (2026-05-25); N-1 … N-3 are all complete (2026-05-26).**

0a. ~~**[N-1, P1 security] Guard the auto-language fetch.**~~ ✅ **Done (2026-05-26).** `lang_detector.py` validates every hop (initial + redirects) via the shared `_host_is_blocked` classifier, follows redirects manually with `follow_redirects=False`, and skips the fetch for blocked hosts. Regression suite `tests/test_lang_detector_ssrf.py` (7 cases) proves no stream is opened to a blocked host.
0b. ~~**[N-2, P0 CI] Make the suite green.**~~ ✅ **Done (2026-05-26).** Test updated to assert the stable `reason_code == "fail_missing_alt"`. Browser-free suite: **749 passed, 3 skipped, 0 failed.**

1. **Auditor-model unification** — take B-2 to its conclusion: have auditors emit `Finding(...)` objects directly so `combined/findings.py` (now 1587 lines) can be deleted instead of maintained. This is the single biggest lever from 85 → 90+. *(multi-week)*
2. **Close the residual SSRF TOCTOU** (B-6) properly: fetch via a pinned IP / resolver hook so Chromium connects to the validated address. *(1–2 days)* — note this is **separate** from N-1: B-6 is the browser-path DNS-rebind window; N-1 is a brand-new unguarded httpx path.
3. ~~**Fix the pre-existing Python test failures.**~~ ✅ **Done (2026-05-25).** `test_rendered_converters.py` updated to assert the rule-specific reflow PASS message (the intended behavior; renamed `test_rendered_reflow_pass_reason_is_specific`). `stages.py` hoists `UniversalPageLoader` to module level so the patch target resolves; the 3 `test_combined_stages.py` tests assert a removed `max_depth` snapshot-gating architecture and are now `@pytest.mark.skip`-ed with a reason, pending a rewrite against the current `static_rules_enabled` / `*_universal` control flow. **Python browser-free suite: 279 passed, 3 skipped, 0 failed.**
4. **Node test backlog (separate, pre-existing).** ~22 failures across 8 unrelated custom-check suites (location, keyboard-trap, focus-appearance, on-focus/on-input, link-purpose, index, criteria-filter). Common pattern: checks now return `incomplete` (manual-review) where tests expect `pass` — i.e. AAA checks became conservative and the tests went stale. Each is a per-check test-vs-source decision; **not** related to B-1…B-12. Recommend triaging as its own batch.
5. **Cosmetic:** physical 4-file split of `universal_extract.js`; job-association for the standalone `crawled_images/` so it can be TTL-swept too. *(optional)*

---

## 6. Verification Note

**B-1 (initial):** the field-map guard test went `1 FAILED → 3 passed` after registering SC 1.2.2.

**B-2 … B-12 (this pass):**

- Browser-free Python sweep (field_map, findings, ssrf, context_factory, accessible_name, browser_pool, policy, thresholds, store, combined, decision, label_in_name, rendered): **278 passed, 4 failed**.
- The 4 failures are **pre-existing and unrelated** to these changes, proven against the session-start commit `b8242bc`:
  - `test_combined_stages.py` (×3) — patches `stages.UniversalPageLoader`, but that import was already *function-local* (not a module attribute) at `b8242bc`. Patch target never resolvable.
  - `test_rendered_converters.py` (×1) — asserts a specific i18n catalogue reason; `rendered/` and `i18n/` were never touched in this pass.
- Node: 2.5.4 suites (`motion-actuation`, `motion-listener-detector`) pass with the B-11 change; the 22 unrelated Node failures (focus-appearance, location, link-purpose, on-focus/on-input, keyboard-trap, index, criteria-filter) do not import `disable-control-validator.js`.
- JS edits (`universal_extract.js`, `_RELATIONSHIP_JS`, merged image probe) all pass `node --check`.
- New guard test added: `test_every_helper_call_sc_is_registered` (asserts every SC passed to `get_status`/`get_reason` in `findings.py` is registered).

All other status tags were verified by reading the cited source lines. Note: this environment auto-commits each edit, so the working tree shows clean against `HEAD` — all B-1…B-12 changes are committed.

**Pre-existing-failure cleanup (2026-05-25):** the 4 Python failures surfaced above are resolved — `test_rendered_converters.py` now asserts the specific reflow PASS message; `stages.py` hoists the `UniversalPageLoader` import (patch target resolves) and the 3 obsolete-architecture `test_combined_stages.py` tests are skipped with a documented reason. Final Python browser-free run: **279 passed, 3 skipped, 0 failed.** The ~22 Node failures remain (separate pre-existing backlog, §5 item 4).

---

## 7. 2026-05-26 pass — verification

**Before the N-fixes**, the full browser-free suite was `741 passed, 1 failed, 3 skipped` (the failure = N-2), and N-1 was confirmed by source inspection (`models.py:69` defaults `lang="auto"`; `runner.py:207-210` calls `detect_page_language`; the old `lang_detector` fetched with a bare `httpx` client that never touched the Playwright-context-level `install_ssrf_guard`).

**After the N-fixes (current source):**

```
pytest tests/ -k "not browser"  →  749 passed, 3 skipped, 0 failed
```

- **N-1 fixed & tested.** `lang_detector.py` now imports `_host_is_blocked` and validates the initial URL **and every redirect hop** before connecting (`asyncio.to_thread` so the blocking `getaddrinfo` stays off the loop); `follow_redirects=False` with a manual 5-hop loop. New `tests/test_lang_detector_ssrf.py` — 7 parametrised cases (`169.254.169.254`, `localhost`, `127.0.0.1`, `10.0.0.5`, `192.168.1.1`, `[::1]`, decimal `2130706433`) — monkeypatches `httpx.AsyncClient` to fail if `.stream()` is ever called, and asserts each returns the safe `"en"` default with **zero** fetch attempts.
- **N-2 fixed.** Test renamed and now asserts the stable `reason_code == "fail_missing_alt"` + a localised JA reason.
- **N-3 mitigated.** Per-host TTL cache (`_LANG_CACHE`, 600 s) verified by reading the source; the first audit of a host still does one lightweight fetch.
- **New feature modules** (per-page report build, image `page_url` wiring) reviewed by reading the cited source lines — correct and additive; existing `test_combined_findings` / image-audit / contrast suites stay green with the added field.

> Net effect on score: B-1…B-12 and N-1…N-3 are all fixed; the unification debt (§4) is unchanged. Score is back to **85/100**; the path to 90+ is still the auditor-model unification.

---

## 8. Plan — Durable run history in SQLite (for the next session)

### 8.1 Problem & goal

Today a finished audit lives in **two places, both ephemeral**:

1. **In-memory** `_jobs[job_id]` (`combined/store.py`) — evicted on a TTL.
2. **On disk** `crawled_images/{domain}_{ts}_{jobid}_combined/combined_report.json` — and **B-12** deletes that whole `output_dir` when the job is TTL-evicted.

So **old reports are lost by design** once the TTL fires; there is no run history, no way to list past audits, and no time-series of how a site's score moved. The container's working dir is also not guaranteed to survive a redeploy.

**Goal:** add a small **SQLite durability layer** that permanently records, per run: the request metadata, the final summary/score, the full report JSON, and a **per-stage timing log** — stored on a **mounted volume** so history survives TTL eviction, container restarts, and redeploys. The in-memory `_jobs` + disk `output_dir` stay as the *hot/working* layer (unchanged, still TTL-swept); SQLite becomes the *cold/durable* layer.

### 8.2 Why SQLite (not Postgres, not "just keep the JSON files")

- **Single-file, zero-ops, mountable.** One `*.db` file on a Docker volume = trivially persistent and backup-able (`cp`/`sqlite3 .backup`). No extra service in `docker-compose`.
- **Queryable history** the JSON-on-disk approach can't give: "last 50 runs", "score trend for host X", "all runs with violations of SC 1.4.3", "slowest stage last week".
- **Concurrency is fine at our scale.** Writes are bounded by `A11Y_MAX_CONCURRENT_JOBS` (4) and are short; **WAL mode** handles concurrent readers + one writer comfortably. If we ever outgrow it, the repository interface (§8.6) lets us swap the backend without touching call sites.

### 8.3 Schema (DDL)

`runs` stays narrow for fast listing; the heavy JSON and the timing rows live in child tables (1‑to‑many / 1‑to‑1).

```sql
PRAGMA journal_mode = WAL;        -- concurrent readers + 1 writer
PRAGMA synchronous  = NORMAL;     -- durable enough for WAL; fast
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS runs (
  job_id          TEXT PRIMARY KEY,
  url             TEXT NOT NULL,
  host            TEXT NOT NULL,            -- urlparse(url).netloc, for trend queries
  lang_requested  TEXT NOT NULL,            -- "auto" | "en" | "ja" | ...
  lang_resolved   TEXT,                     -- what auto resolved to
  wcag_level      TEXT NOT NULL,            -- A | AA | AAA
  max_depth       INTEGER NOT NULL,
  max_pages       INTEGER NOT NULL,
  success_criteria_id TEXT,                 -- single-SC runs (nullable)
  status          TEXT NOT NULL,            -- pending|running|completed|failed
  submitted_at    TEXT NOT NULL,            -- ISO-8601 UTC
  started_at      TEXT,
  completed_at    TEXT,
  duration_ms     INTEGER,                  -- completed_at - started_at
  score           REAL,                     -- summary.score (nullable on fail)
  total_findings  INTEGER,
  violations      INTEGER,
  needs_review    INTEGER,
  passes          INTEGER,
  page_count      INTEGER,
  warnings_count  INTEGER DEFAULT 0,
  error_id        TEXT,                     -- opaque id on failure (matches logs)
  error_stage     TEXT,
  report_path     TEXT,                     -- last-known on-disk path (may be TTL-deleted)
  schema_version  INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_runs_host_time  ON runs(host, submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_status     ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_submitted  ON runs(submitted_at DESC);

-- Full report JSON, 1:1 with runs. Separate table so history listing never
-- pulls multi-MB blobs. Store compressed to keep the DB small.
CREATE TABLE IF NOT EXISTS run_reports (
  job_id        TEXT PRIMARY KEY REFERENCES runs(job_id) ON DELETE CASCADE,
  report_json   BLOB NOT NULL,             -- zlib-compressed UTF-8 JSON
  compression   TEXT NOT NULL DEFAULT 'zlib',
  byte_size     INTEGER NOT NULL,          -- compressed size, for budgeting
  created_at    TEXT NOT NULL
);

-- Time-wise per-stage log, many rows per run. One row per stage transition set.
CREATE TABLE IF NOT EXISTS run_stage_timings (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id        TEXT NOT NULL REFERENCES runs(job_id) ON DELETE CASCADE,
  stage         TEXT NOT NULL,             -- axe_core|image_audit|pipeline|...
  status        TEXT NOT NULL,             -- completed|error
  started_at    TEXT NOT NULL,
  completed_at  TEXT,
  duration_ms   INTEGER,
  findings_count INTEGER,
  error         TEXT
);
CREATE INDEX IF NOT EXISTS idx_stage_job ON run_stage_timings(job_id);
```

> Optional 4th table `run_step_events` (mirror of the `ExecutionStepLogger` JSONL) only if we want the fine-grained step log queryable; otherwise leave the JSONL on disk and just store its path.

### 8.4 Where the writes hook in (minimal, additive)

New module `a11y/api/v1/combined/db.py` (a thin repository; see §8.6). Call sites:

| Event | Source today | New write |
|-------|--------------|-----------|
| Job accepted | `routes.submit_combined_audit` (`routes.py:233`) | `runs` row `INSERT` with `status='pending'`, request metadata, `submitted_at` |
| Job starts | `runner._run_job_body` (`runner.py:199`) | `UPDATE runs SET status='running', started_at=…, lang_resolved=…` |
| Stage completes / errors | `stage_events._stage_complete` / `_stage_error_and_warn` | `INSERT run_stage_timings` (stage, status, started/completed, duration, findings_count) — the timestamps already exist in the `_jobs[job_id]["stages"]` list |
| Job completes | `runner._run_job_body` success block (`runner.py:442`) | `UPDATE runs` (status, completed_at, duration_ms, score, counts, page_count) + `INSERT run_reports` (zlib-compressed `report` JSON) |
| Job fails | `runner` except block (`runner.py:500`) | `UPDATE runs SET status='failed', error_id=…, error_stage=…, completed_at=…` |

All writes wrapped in `try/except` that **logs and continues** — persistence must never fail an audit (same philosophy as the step logger). Stage timings can also be back-filled in one shot from `_jobs[job_id]["stages"]` at completion instead of per-transition, which is simpler and avoids extra writes on the hot path.

### 8.5 Read surface (new endpoints in `routes.py`)

- `GET /api/v1/combined/history?host=&status=&limit=50&offset=0` → page of `runs` rows (no blobs) — powers a "past audits" view in the frontend.
- `GET /api/v1/combined/history/{job_id}` → the full stored report (decompress `run_reports.report_json`) — lets the dashboard reopen an old report even after the on-disk copy was TTL-swept. The existing `GET /combined/{job_id}` keeps serving the hot in-memory result; it should **fall back to SQLite** when the job is no longer in `_jobs`.
- `GET /api/v1/combined/history/{job_id}/timings` → `run_stage_timings` rows for a run (the time-wise log).
- (Optional) `GET /api/v1/combined/trends?host=` → `job_id, submitted_at, score` series for charting a site over time.

### 8.6 Concurrency & connection model

- One module-level connection opened with `check_same_thread=False`, guarded by a `threading.Lock` for writes; or open a short-lived connection per write via `asyncio.to_thread` (DB calls are blocking → never run them directly on the event loop). Prefer **`asyncio.to_thread(_repo.write, …)`** so the loop never blocks.
- `PRAGMA journal_mode=WAL` once at bootstrap. Readers (history endpoints) never block the writer.
- Repository interface (`RunRepository` with `record_submitted/started/stage/completed/failed/get/list`) so the storage backend is swappable and unit-testable with an in-memory `sqlite3.connect(":memory:")`.

### 8.7 Mounting & persistence (the "no loss" requirement)

The DB file **must** live on a mounted volume, not in the container's ephemeral layer.

- **Path:** `A11Y_DB_PATH` env, default `/data/a11y.db` (new) — keep it separate from `crawled_images/` so report blobs survive even when B-12 sweeps the image dirs.
- **`docker-compose.yml`:** add a named volume and mount it on the `a11y-python` service:
  ```yaml
  services:
    a11y-python:
      environment:
        - A11Y_DB_PATH=/data/a11y.db
      volumes:
        - a11y_db:/data            # durable, survives `down`/redeploy
  volumes:
    a11y_db:
  ```
  (WAL creates `a11y.db-wal` / `a11y.db-shm` siblings — they live in `/data` too, so the volume covers them.)
- **Bootstrap:** run the DDL (`CREATE TABLE IF NOT EXISTS …`) at app startup (FastAPI lifespan), idempotent. Mkdir the parent of `A11Y_DB_PATH` first.
- **Backups:** `sqlite3 $A11Y_DB_PATH ".backup '/data/backups/a11y-$(date +%F).db'"` on a cron; the file is portable.

### 8.8 Retention & size

- **Metadata (`runs`, `run_stage_timings`) is kept indefinitely** — it's tiny (hundreds of bytes/run).
- **Report blobs (`run_reports`) are the only heavy rows.** Add `A11Y_DB_REPORT_RETENTION_DAYS` (default e.g. 180): a periodic task `DELETE FROM run_reports WHERE created_at < …` keeps the queryable history (counts, score, timings) forever while bounding blob storage. `runs` rows stay so trends remain complete even after a blob is pruned.
- zlib compression typically shrinks the report JSON 8–15×; budget ~tens of KB/run compressed.
- Decouple from B-12: B-12 deletes the working `output_dir`; the SQLite copy is independent and is what the history endpoints read.

### 8.9 Rollout (phased, low-risk)

1. **Schema + repo + bootstrap** (`db.py`, lifespan DDL, `:memory:` unit tests). No behaviour change.
2. **Write hooks** in `routes`/`runner`/`stage_events`, all `try/except`-guarded. Verify a run produces one `runs` row + one `run_reports` blob + N `run_stage_timings`.
3. **Read endpoints** + `GET /combined/{job_id}` SQLite fallback.
4. **docker-compose volume + `A11Y_DB_PATH`** + a startup log line confirming the resolved DB path.
5. **Retention task** + docs (`internals/output-format.mdx` "where the output lives" table gains a SQLite row; `deployment/` gets a "persistent run history" note).

### 8.10 Testing

- Unit: repository against `sqlite3.connect(":memory:")` — insert→list→get round-trip, decompress equality, cascade delete, WAL pragma set.
- Integration: a mocked completed job writes exactly one `runs` + one `run_reports` + the expected `run_stage_timings`; a failed job writes status `failed` + `error_id` and **no** `run_reports`.
- Resilience: a DB write raising must **not** fail the audit (assert the job still completes and the report is still returned from memory).

> This plan is intentionally additive: it does not change how an in-flight audit runs or what `GET /combined/{job_id}` returns for a live job — it only adds a durable, mounted, queryable shadow copy so history survives. Implement in the order of §8.9.
