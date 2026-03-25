# ka11y — Current Code Analysis Report

Updated: 2026-03-25

Scope:
- `ka11y-node`
- `ka11y-python`

This file supersedes the earlier stale review. Items previously tracked as unresolved but now fixed have been removed from the active findings list.

---

## 1. Validation Proof

| Area | Command / Source | Current result |
|---|---|---|
| Node unit/integration tests | `ka11y-node/npm test` | `165` tests passed, `0` failed |
| Python tests | `ka11y-python/python -m pytest` | `515` passed |
| Browser-backed rule proof | `ka11y-node/npm run evidence` | `0` bugs after 1 attempt |
| Evidence artifact | `ka11y-node/logs/evidence-report.md` | generated successfully |
| Live SC check test | All 20 custom checks against 3 real sites (W3C bad demo, BBC, Bootstrap) | `0` check execution errors; legitimate findings on real violations |
| Live website test | Python combined API against `httpbin.org/forms/post` | 64 findings emitted; form field `tag` and `element_id` populated correctly; violation text from auditor passed through (not generic fallback) |

What the evidence loop proved in a real browser:
- best-practice axe rules now reflect stable SC/criterion metadata
- `1.4.6` now resolves as `Contrast (Enhanced) / AAA`
- custom rules reflect both fail/pass or `needs_review` correctly
- pluggable custom checks load from new `*.check.js` files
- All 20 SC checks execute without errors on live production websites

---

## 2. Current Confirmed Findings

Ordered by severity.

| ID | Severity | Area | File | Current issue | Recommended fix |
|---|---|---|---|---|---|
| N-01 | High | Node security | `ka11y-node/src/services/accessibility.service.js:23-40`, `:183-209`, `:257-284` | `_assertPublicUrl()` validates only the original hostname. `page.goto()` can still follow a redirect chain to a private or link-local target because no request interception or post-redirect validation is applied. | Add a Playwright request/route guard that validates every request target, not just the first URL. |
| P-01 | High | Python security | `ka11y-python/ka11y/api/v1/combined/routes.py:89-121`, `:215-233` | `build_ssrf_route_handler()` exists, but it is not attached to crawler pages or contexts anywhere in the current tree. The helper also only catches literal IP hosts, not hostnames that resolve to private IPs mid-redirect. | Wire the guard into every Playwright page/context and resolve redirected hostnames before continuing requests. |
| P-03 | Medium | Python performance | `ka11y-python/ka11y/api/v1/combined/runner.py:57-86`, `ka11y-python/ka11y/api/v1/combined/stages.py:98-136`, `:155-176`, `:195-216`, `:235-256`, `:275-296`, `:315-336`, `:469-495` | The combined pipeline launches Node plus multiple Python stage crawlers in parallel. Each crawler revisits the same site independently, which increases wall-clock time, CPU, RAM, and target-site load. | Move toward a shared crawl artifact model so DOM/page discovery is reused across auditors instead of repeated. |
| N-02 | Medium | Node result fidelity | `ka11y-node/src/utils/axeResultMapper.js:382-427` | `mapCustomResultsFlat()` still emits `element: null` for custom findings. The SC/criterion metadata is now fixed, but many custom findings still lack stable HTML or selector evidence. | Extend custom check result shape to optionally include `html`, `target`, and `element_id`, and preserve it in the flat mapper. |

There are no currently confirmed mapper bugs in the `best-practice`, `1.4.6`, or `unknown SC -> null` paths; those were re-tested and are now working.

---

## 3. Verified Fixes In Current Tree

These issues were stale in the previous report and are now fixed.

### Node

- Pluggable custom-check loading is now filesystem-driven in `ka11y-node/src/custom-checks/index.js`.
- Missing best-practice criterion labels are fixed in `ka11y-node/src/utils/axeResultMapper.js`.
- Missing AAA metadata for `1.4.6` is fixed in `ka11y-node/src/utils/wcagMetadata.js`.
- Unknown SC handling now returns `null` rather than leaking `undefined`, and the tests covering that are in `ka11y-node/tests/utils/axeResultMapper.custom-flat.test.js`.
- Digit shortcuts are no longer falsely flagged for WCAG `2.1.4`; the fix and tests are in `ka11y-node/src/custom-checks/character-key-shortcuts.check.js` and `ka11y-node/tests/custom-checks/character-key-shortcuts.check.test.js`.
- Failing custom checks are no longer silently dropped; the safety behavior is covered in `ka11y-node/tests/custom-checks/index.test.js`.
- **NEW** `_runChecks()` filter changed from `.filter(Boolean)` to `.filter(r => r != null)` in `ka11y-node/src/custom-checks/index.js:199` — prevents silently dropping a check result that is a valid falsy value.
- **NEW** `keyboard-trap.check.js`: Critical runtime fix — `page.keyboard.press('Shift+Tab')` is not a valid Puppeteer key; replaced with `keyboard.down('Shift')` + `keyboard.press('Tab')` + `keyboard.up('Shift')` pattern. Check was silently failing on every page with an `"Unknown key"` error.
- **NEW** `keyboard-trap.check.js`: Element key stability improved — now uses `id`/`name`/`aria-label` attributes as primary identifier before falling back to DOM position index. Applied to all three key-capture points (Tab loop, Shift+Tab loop, post-Escape verification).
- **NEW** `status-messages.check.js`: Pass logic fixed — when `needsLiveRegions` is true AND live regions exist, now correctly returns `incomplete` (needs manual review) instead of `pass`. Added correct test: notification element properly inside a live region → `needsLiveRegions:false` → `pass`.
- **NEW** `meaningful-sequence.check.js`: The `MAX_CONTAINERS` counter was counting ALL elements scanned (including non-flex/grid), so on a page with 150+ elements the actual flex/grid containers checked were very few. Counter now increments only on flex/grid containers; limit raised from 150 → 500.
- **NEW** `dragging-movements.check.js`: Added `Set`-based dedup for library marker matching to prevent the same element being counted multiple times when it matches multiple library selectors.
- **NEW** `character-key-shortcuts.check.js`: Inline handler detection now matches symbol keys (e.g. `event.key === '!'`) consistent with `PRINTABLE_CHAR_RE`, not just letter keys.
- **NEW** `focus-visible.check.js`: Outline transparency check expanded from literal string equality to regex covering `rgba(0,0,0,0)`, `transparent`, `inherit`, and `initial`.
- **NEW** `pointer-cancellation.check.js`: Added `[onpointermove]` to the selector and handler extraction — covers implementations that define the action in `pointermove` and cancellation in `pointerup`.
- **NEW** `use-of-color.check.js`: `MAX_LINKS` increased from 80 → 150 to avoid missing violations in link-heavy pages.

### Python

- Lazy imports now let the API boot without requiring every OCR/crawler dependency at import time.
- `_broadcast()` is now async and lock-protected in `ka11y-python/ka11y/api/v1/combined/store.py`.
- The combined Python stage runner now applies a per-stage timeout in `ka11y-python/ka11y/api/v1/combined/stages.py:464-495`.
- The `Label in Name` punctuation edge case is fixed in `ka11y-python/ka11y/accessibility/rules/input_modalities/label_in_name_auditor.py:70-97`.
- The orientation zero-interactive-elements edge case is fixed in `ka11y-python/ka11y/accessibility/rendered/evaluators/orientation.py:77-109`.
- The text-spacing non-relevant-item inflation issue is fixed in `ka11y-python/ka11y/accessibility/rules/input_modalities/text_spacing_auditor.py:31-49`.
- Unexpected `_run_python_stages()` return shapes are now handled defensively in `ka11y-python/ka11y/api/v1/combined/runner.py:100-109`.
- **NEW** Form findings field-name mismatch fixed in `ka11y-python/ka11y/api/v1/combined/findings.py:431-472`:
  - `_form_to_findings()` now resolves `violation_key` using `_violations` (plural) to match `form_auditor.py`'s `wcag_3_3_1_violations` / `wcag_3_3_2_violations` output — was using `_violation` (singular) which always fell back to the generic reason string.
  - `tag` now falls back to `field_tag` first, matching `form_auditor.py`'s record key.
  - `element_id` now falls back through `field_id` → `element_id` → `field_name` → `element_name` in order.
- **NEW** `max_depth` bounds (`ge=0, le=5`) added to legacy request models `CrawlRequest`, `FormsRequest`, `PipelineRequest` — previously only the combined endpoint model enforced this cap.

---

## 4. Performance Backdrops

These are not logic bugs, but they are the main reasons the full pipeline can feel heavy.

| Area | Current backdrop | Why it matters | Direction |
|---|---|---|---|
| Node | New Puppeteer browser per request | High startup cost for repeated audits | Add browser/context pooling |
| Python combined | Multiple crawlers revisit the same pages | Duplicated network and Playwright work | Share crawl results across stages |
| OCR path | OCR and rendered evaluators are expensive | Image-heavy sites will dominate runtime | Make expensive stages easier to disable or batch |
| Custom findings | Many custom checks are rule-level, not element-level | Harder to explain failures downstream | Return structured element evidence from custom checks |

---

## 5. Automation Status

Current automation already in place:
- `ka11y-node/npm test`
- `ka11y-python/python -m pytest`
- `ka11y-node/npm run evidence`

Recommended next automation step:

1. Put the evidence loop in CI alongside Node and Python tests.
2. Fail CI when `ka11y-node/logs/evidence-report.md` reports any non-zero bug count.
3. Add at least one redirect-SSRF regression test for Node and Python once request interception is implemented.
4. Add a contract test that custom checks may return structured element evidence and that the flat mapper preserves it.

---

## 6. Coverage Snapshot

Current WCAG coverage counts:

| Service | A | AA | AAA | Total |
|---|---:|---:|---:|---:|
| `ka11y-node` | 24 | 17 | 3 | 44 |
| `ka11y-python` | 6 | 10 | 1 | 17 |
| Combined | 25 | 22 | 4 | 51 |

Combined coverage percentage:
- `51 / 87` WCAG SCs = `59%`

The detailed per-SC breakdown is in `COVERAGE.md`.

---

## 7. Bottom Line

Current status after 2026-03-25 bug-fix pass:
- Node: 164 tests pass, 0 failures. Evidence loop 0 bugs.
- Python: 515 tests pass, 0 failures.
- Form audit findings now correctly propagate violation text and element metadata (`tag` + `element_id`) from the auditor through the findings converter — verified against `httpbin.org/forms/post` in live audit.
- Legacy `max_depth` input hardening now matches the combined endpoint.
- Custom check results no longer risk silent drops on falsy return values.

The remaining open work is concentrated in two areas:
- SSRF redirect hardening in both runtimes (security, not correctness)
- Performance: shared crawl artifact to avoid multi-crawler revisits of the same pages
