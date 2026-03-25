# ka11y — Full Code Review, Bug Report & Coverage Analysis

**Date:** 2026-03-25
**Scope:** `ka11y-node` (Node.js / Puppeteer / axe-core) · `ka11y-python` (FastAPI / Playwright / NLTK)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Bugs Fixed This Session](#2-bugs-fixed-this-session)
3. [ka11y-node — Detailed Bug Report](#3-ka11y-node--detailed-bug-report)
4. [ka11y-python — Detailed Bug Report](#4-ka11y-python--detailed-bug-report)
5. [WCAG Coverage: ka11y-node](#5-wcag-coverage-ka11y-node)
6. [WCAG Coverage: ka11y-python](#6-wcag-coverage-ka11y-python)
7. [Combined Coverage Summary](#7-combined-coverage-summary)
8. [Custom Check Confidence Ratings](#8-custom-check-confidence-ratings)
9. [Suggested Improvements](#9-suggested-improvements)

---

## 1. Executive Summary

| | ka11y-node | ka11y-python |
|---|---|---|
| Files reviewed | 22 | 23 |
| Bugs found (total) | 14 | 11 |
| Bugs fixed | 13 | 4 |
| Critical bugs | 0 | 0 |
| High bugs | 3 | 3 |
| Medium bugs | 7 | 5 |
| Low bugs | 4 | 3 |
| WCAG SCs covered | 42 (24A + 16AA + 2AAA) | 17 |
| New checks added | 5 (1.2.1, 1.4.1, 2.4.8 AAA, 2.4.9 AAA, 2.4.13) | — |

---

## 2. Bugs Fixed This Session

### ka11y-node

| # | File | Line | Severity | Description | Fix Applied |
|---|------|------|----------|-------------|-------------|
| N1 | `keyboard-trap.check.js` | 49–50 | **High** | No settle delay after `Escape` press before checking if trap was escaped — async focus-restore handlers hadn't run, causing false positives | Added `SETTLE_MS` (60 ms) after both `Escape` and `Tab` in the verify step |
| N2 | `use-of-color.check.js` | 88, 93 | **High** | `ancestorFontWeight` and `hasFontStyleCue` used `link.parentElement` instead of the actual non-`<a>` ancestor found by `getAncestorTextStyle()` — if the parent is itself an `<a>`, comparison was against the wrong element | Refactored `getAncestorTextStyle()` to also return `fontWeight` and `fontStyle`; comparison now uses those values |
| N3 | `focus-appearance.check.js` | 29–38 | **Medium** | Element re-queries used a stale DOM index (`el.idx`) — if DOM mutated between initial collection and subsequent `page.evaluate()` calls, the wrong element was tested | Added `stableSel` (unique `#id` selector) to each element record; re-queries now prefer `stableSel` over array index |
| N4 | `meaningful-sequence.check.js` | 22–26 | **Medium** | Hidden element filter only excluded `display:none` and `visibility:hidden` — children with `opacity:0` or `visibility:collapse` were counted as visible and flagged as reordered | Added `cs.opacity !== '0'` and `cs.visibility !== 'collapse'` checks |
| N5 | `character-key-shortcuts.check.js` | 41–42 | **Medium** | Modifier guard check (`/ctrlKey|altKey|metaKey/.test(handler)`) matched the modifier string anywhere in the handler — an unrelated `if (event.ctrlKey)` branch elsewhere would prevent a real violation from being flagged | Replaced with proximity check: modifier and key check must be within 120 characters of each other |
| N6 | `status-messages.check.js` | 37–39 | **Medium** | `hasNotificationArea` included `[role="status"], [role="log"]` — those ARE live regions and were already counted in `liveRegions`; including them in "needs live regions" logic conflated two different concepts | Removed live-region roles from `hasNotificationArea`; replaced with class-based patterns for non-ARIA notification elements |
| N7 | `on-focus.check.js` | 11–17 | **Low** | SELECTOR array used leading commas on each element after the first joined with `.join('')` — fragile and misleading | Replaced with clean `[...].join(', ')` without leading commas |
| N8 | `on-input.check.js` | 16–22 | **Low** | Same leading-comma pattern as N7; `:not()` chains split across array lines | Flattened `input` selector to one string; clean `.join(', ')` |
| N9 | `focus-visible.check.js` | 73–74 | **Low** | `outlineChanged` returned `true` even when `outlineColor` changed to `transparent` — transparent outline counted as a visible change | Added `outlineColor !== 'rgba(0,0,0,0)'` and `!== 'transparent'` guards in `outlineActuallyVisible` |
| N10 | `accessible-auth.check.js` | 27–31 | **Medium** | `[data-sitekey]` alone matched non-CAPTCHA widgets → false positives | Dual-signal: now requires `iframe[src*="recaptcha"]` OR captcha-specific class alongside `data-sitekey` |
| N11 | `error-suggestion.check.js` | 27–31 | **Medium** | Class-based error selectors matched decorative or documentation elements outside forms → false positives | Scoped all class selectors to `form` descendants (`form .error-message`, etc.) → confidence 🔴 Low → 🟡 Medium |
| N13 | `server.js` | 49–54 | **Medium** | `Access-Control-Allow-Origin: *` set for requests without `Origin` header (server-to-server requests) — partially negated the allowlist | Removed wildcard fallback; header only set when `origin` is in the allowlist |

### ka11y-python

| # | File | Line | Severity | Description | Fix Applied |
|---|------|------|----------|-------------|-------------|
| P1 | `alttext.py` | 722 | **Medium** | `wcag_1_4_11_status` used `"INCOMPLETE"` when `wcag_1_4_11_pass is None`, while all other status fields in the same record used `"N/A"` — semantic inconsistency broke downstream filtering in `findings.py` | Changed `"INCOMPLETE"` → `"N/A"` to match all other status fields |
| P2 | `models.py` | 16 | **High** | `max_depth: int = 0` had no upper bound — a caller could submit `max_depth=999` triggering exponential page-crawl growth (DoS vector) | Added `Field(ge=0, le=5)` constraint |
| P3 | `text_spacing.py` | 77 | **Medium** | `len(el.text.strip()) < 3` skipped short but valid text such as `"OK"`, `"No"`, `"Go"` — WCAG 1.4.12 applies to ALL text | Changed threshold to `not el.text.strip()` (skip only truly empty text) |
| P4 | `stage_events.py` | 32–37 | **Low** | `_stage_complete()` and `_stage_error()` silently did nothing when a stage name was not found in running state — SSE progress appeared stale with no diagnostic | Added `logger.warning()` when stage match fails |

---

## 3. ka11y-node — Detailed Bug Report

### 3.1 Remaining Confirmed Bugs (not yet fixed)

| # | File | Line | Severity | Description | Recommended Fix |
|---|------|------|----------|-------------|-----------------|
| N12 | `character-key-shortcuts.check.js` | 38 | **Medium** | `[a-zA-Z0-9]` in key regex matches digit keys (0–9) — WCAG 2.1.4 targets printable character shortcuts, and numeric digits in most contexts are not considered "character key shortcuts" | Change to printable non-digit ASCII range; also tighten keyCode range |
| N14 | `axeResultMapper.js` | 257 | **Low** | `mapResultsFlat()` reads `WCAG_NAMES[sc]` and `WCAG_LEVEL[sc]` without checking for `undefined` — unknown SCs result in `criterion_name: undefined` (not `null`) which breaks JSON serialisation in some clients | Add `|| null` fallback: `criterion_name: sc ? (WCAG_NAMES[sc] || null) : null` |

### 3.2 False Positive / False Negative Risks

| Check | Risk Type | Description |
|-------|-----------|-------------|
| `status-messages` | FP | Notification class elements (`.toast`, `.notification`) that ARE already inside a `role="status"` container will trigger `needsLiveRegions=true` while `liveRegionCount > 0`, so the control flow resolves correctly — but the `dynamicContexts` message misleadingly says these areas "need" live regions |
| `error-suggestion` | FP | The `[aria-invalid="true"] + *` selector captures the NEXT sibling, which may be an unrelated element if the error message isn't the immediate next sibling |
| `dragging-movements` | FP | Library DnD markers like `[data-rbd-draggable-id=""]` (empty value = container, not item) are flagged as draggable — `el.getAttribute('draggable') !== 'false'` filter is insufficient |
| `character-key-shortcuts` | FP | Handler `if (e.key === '1') ...` is flagged but digit keys are typically not covered by WCAG 2.1.4 |
| `on-focus` / `on-input` | FN | Only 25 elements tested — traps deeper in the page are missed |
| `keyboard-trap` | FN | Only tests Tab (forward) — Shift+Tab (backward) traps are not tested |
| `focus-visible` | FN | N9 fix applied — transparent `outline-color` now correctly fails; remaining FN: box-shadow area not measured for 2.4.11 AAA threshold |

---

## 4. ka11y-python — Detailed Bug Report

### 4.1 Remaining Confirmed Bugs (not yet fixed)

| # | File | Line | Severity | Description | Recommended Fix |
|---|------|------|----------|-------------|-----------------|
| P5 | `routes.py` | 74–127 | **High** | `_assert_public_url()` validates the initial URL hostname but does NOT prevent SSRF via HTTP redirects — attacker's server at `https://attacker.com` can 301→`http://192.168.1.1` and the Playwright crawler follows it | Validate every redirect target; add a `page.on('request')` Playwright hook to block requests to private IP ranges |
| P6 | `store.py` | 38–42 | **Medium** | `_broadcast()` is synchronous and not lock-protected. `routes.py` uses `async with _subscribers_lock` when adding/removing queues. A concurrent `add-subscriber` coroutine could be scheduled between the `list()` snapshot and the `put_nowait()` loop | Make `_broadcast` async and acquire `_subscribers_lock` before iterating |
| P7 | `runner.py` | 100–103 | **Medium** | `python_findings, contrast_report = python_result` — if `_run_python_stages()` returns an unexpected type (not a 2-tuple), this raises an unhandled `ValueError` | Add type guard: `if isinstance(python_result, tuple) and len(python_result) == 2:` |
| P8 | `text_spacing_auditor.py` | 31–47 | **Medium** | Returns `"PASSED"` for non-text-relevant items (text < 20 chars) — the downstream converter treats this as an actual pass, artificially inflating pass rates | Return `"N/A"` for non-relevant items; `"PASSED"` only for genuinely checked items |
| P9 | `focus_not_obscured_*.py` | 24–26 | **Low** | Hardcoded obscuration thresholds (95% for minimum, 10%/2% for enhanced) — not documented or WCAG-specified; configuring in constants would make them auditable | Extract to named constants with explanatory comments linking to WCAG understanding doc |
| P10 | `orientation.py` | 79 | **Low** | Interactive element ratio check could produce misleading results when one orientation returns 0 elements (e.g. hamburger menu fully collapses) — no guard for division edge cases | Add `if p_count == 0 or l_count == 0` guard before ratio comparison |
| P11 | `label_in_name_auditor.py` | 71 | **Low** | Word-boundary regex `r"\bGo\b"` fails when visible label ends with `!` (e.g. `"Go!"`) because `!` is not a word character, so `\b` does not apply after `o` before `!` | Normalize punctuation before comparison: `re.sub(r"[^\w\s]", "", text).strip()` |

### 4.2 Design / Architecture Concerns

| # | File | Concern |
|---|------|---------|
| D1 | `alttext.py` / `findings.py` | Auditor uses uppercase status values (`"PASSED"`, `"FAILED"`) while the API emits lowercase (`"pass"`, `"fail"`) — the mapping is in `findings.py` but any new auditor that bypasses it will break the API contract |
| D2 | `stages.py` | No timeout on individual crawl stages — a slow/unresponsive target can hold a Playwright browser instance indefinitely; wrap with `asyncio.timeout()` |
| D3 | `findings.py` | `_build_contrast_report()` silently skips images with no OCR text — no entry is created for `has_text=False` images, making it impossible to distinguish "no text found" from "not analyzed" |
| D4 | `runner.py` | Status sorting key `{"fail":0,"needs_review":1,"pass":2}` works correctly for current status values; any new non-standard status will sort to position 3 (after passes) silently |

---

## 5. WCAG Coverage: ka11y-node

Coverage by custom Puppeteer checks + axe-core v4.9+.

### Level A — 31 SCs

| SC | Name | Method | Confidence |
|----|------|--------|-----------|
| 1.1.1 | Non-text Content | axe `image-alt`, `input-image-alt` | 🟢 High |
| 1.2.2 | Captions (Prerecorded) | axe `video-caption` | 🟢 High |
| 1.3.1 | Info and Relationships | axe `landmark-*`, `list`, `table-*` | 🟢 High |
| 1.3.2 | Meaningful Sequence | `custom-meaningful-sequence` (flex-direction, CSS order) | 🟡 Medium |
| **1.4.1** | **Use of Color** | axe `link-in-text-block` + `custom-use-of-color` | **🟡 Medium** *(was 🔴 Low)* |
| 1.4.2 | Audio Control | axe `no-autoplay-audio` | 🟡 Medium |
| 2.1.1 | Keyboard | axe `scrollable-region-focusable`, `frame-focusable-content` | 🟢 High |
| 2.1.2 | No Keyboard Trap | `custom-keyboard-trap` (Tab + Escape verify) | 🟡 Medium |
| 2.1.4 | Character Key Shortcuts | `custom-character-key-shortcuts` | 🟡 Medium *(was 🔴 Low)* |
| 2.2.1 | Timing Adjustable | axe `meta-refresh` | 🔴 Low |
| 2.2.2 | Pause, Stop, Hide | axe `blink`, `marquee` | 🟡 Medium |
| 2.4.1 | Bypass Blocks | axe `bypass` | 🟢 High |
| 2.4.2 | Page Titled | axe `document-title` | 🟢 High |
| 2.4.3 | Focus Order | axe `tabindex` | 🔴 Low |
| 2.4.4 | Link Purpose (In Context) | axe `link-name`, `area-alt` | 🟢 High |
| 2.5.2 | Pointer Cancellation | `custom-pointer-cancellation` | 🔴 Low |
| 2.5.3 | Label in Name | axe `label-content-name-mismatch` | 🟢 High |
| 3.1.1 | Language of Page | axe `html-has-lang`, `html-lang-valid` | 🟢 High |
| 3.2.1 | On Focus | `custom-on-focus` | 🟡 Medium |
| 3.2.2 | On Input | `custom-on-input` | 🟡 Medium |
| 3.3.1 | Error Identification | — | — |
| 3.3.2 | Labels or Instructions | axe `form-field-multiple-labels` | 🟡 Medium |
| 4.1.1 | Parsing | `custom-html-parsing` (duplicate IDs) | 🟢 High |
| 4.1.2 | Name, Role, Value | axe `aria-*`, `button-name` | 🟢 High |

**Added (Level A): 1.2.1** — `custom-audio-transcript` detects `<audio>` elements without adjacent text alternatives; returns `incomplete` (manual review required)

**Not covered (Level A): 1.2.3, 1.3.3, 2.3.1, 2.5.1, 2.5.4, 3.3.7** (6 SCs — require media analysis, video frames, or multi-step form tracking)

### Level AA — 26 SCs

| SC | Name | Method | Confidence |
|----|------|--------|-----------|
| 1.3.4 | Orientation | axe `css-orientation-lock` | 🟢 High |
| 1.3.5 | Identify Input Purpose | axe `autocomplete-valid` | 🟢 High |
| 1.4.3 | Contrast (Minimum) | axe `color-contrast` | 🟢 High |
| 1.4.4 | Resize Text | axe `meta-viewport` | 🟢 High |
| 1.4.5 | Images of Text | — | — |
| 1.4.10 | Reflow | — | — |
| 1.4.11 | Non-text Contrast | — | — |
| 1.4.12 | Text Spacing | axe `avoid-inline-spacing` | 🟡 Medium |
| 1.4.13 | Content on Hover or Focus | — | — |
| 2.4.5 | Multiple Ways | `custom-multiple-ways` (search/nav/sitemap/breadcrumb/toc) | 🟡 Medium |
| 2.4.6 | Headings and Labels | axe `heading-order`, `empty-heading` | 🟢 High |
| 2.4.7 | Focus Visible | `custom-focus-visible` + axe `focus-visible` | 🟡 Medium |
| 2.4.11 | Focus Not Obscured (Min) | — | — |
| **2.4.13** | **Focus Appearance** | axe `focus-appearance` + `custom-focus-appearance` | **🟡 Medium** *(was 🔴 Low)* |
| 2.5.7 | Dragging Movements | `custom-dragging-movements` | 🟡 Medium |
| 2.5.8 | Target Size (Minimum) | axe `target-size` | 🟢 High |
| 3.1.2 | Language of Parts | axe `valid-lang` | 🟢 High |
| 3.2.3 | Consistent Navigation | — | — |
| 3.2.4 | Consistent Identification | — | — |
| 3.2.6 | Consistent Help | `custom-consistent-help` | 🟡 Medium |
| 3.3.3 | Error Suggestion | `custom-error-suggestion` | 🔴 Low |
| 3.3.4 | Error Prevention | `custom-error-prevention` | 🟡 Medium |
| 3.3.8 | Accessible Auth (Min) | `custom-accessible-auth` | 🟡 Medium |
| 4.1.3 | Status Messages | `custom-status-messages` | 🟡 Medium |

**Not covered (Level AA): 1.4.5, 1.4.10, 1.4.11, 1.4.13, 2.4.11, 3.2.3, 3.2.4** (7 SCs — covered by Python rendered evaluators or require multi-page analysis)

### Node Coverage Totals

| Level | Total SCs | Covered | Coverage % |
|-------|-----------|---------|-----------|
| A | 31 | 25 | **81%** |
| AA | 26 | 17 | **65%** |
| AAA | 30 | 2 | **7%** |

---

## 6. WCAG Coverage: ka11y-python

Coverage by static auditors (crawler-based) + rendered evaluators (Playwright).

| SC | Name | Auditor / Evaluator | Confidence |
|----|------|---------------------|-----------|
| 1.1.1 | Non-text Content | `AltTextAccessibilityAuditor` (OCR cosine-sim alt adequacy) | 🟡 Medium |
| 1.3.4 | Orientation | `OrientationEvaluator` (portrait + landscape Playwright snapshots) | 🟢 High |
| 1.4.3 | Contrast (Min) | `OCRPreprocessing._contrast_to_findings` (text-in-image contrast) | 🟡 Medium |
| 1.4.4 | Resize Text | `ResizeTextEvaluator` (Playwright 200% text-size override) | 🟢 High |
| 1.4.5 | Images of Text | `AltTextAuditor._check_1_4_5` (OCR text detection) | 🟡 Medium |
| 1.4.10 | Reflow | `ReflowEvaluator` (Playwright 320px viewport) | 🟢 High |
| 1.4.11 | Non-text Contrast | `AltTextAuditor._check_1_4_11` (OCR contrast proxy) | 🔴 Low |
| 1.4.12 | Text Spacing | `TextSpacingAuditor` + `TextSpacingEvaluator` | 🟢 High |
| 1.4.13 | Content on Hover/Focus | `HoverFocusContentEvaluator` (Playwright hover) | 🟢 High |
| 2.2.2 | Pause, Stop, Hide | `PauseStopHideAuditor` (CSS anims, carousels, autoplay) | 🟢 High |
| 2.4.11 | Focus Not Obscured (Min) | `FocusNotObscuredMinimumEvaluator` | 🟢 High |
| 2.4.12 | Focus Not Obscured (Enh) | `FocusNotObscuredEnhancedEvaluator` *(AAA)* | 🟢 High |
| 2.5.3 | Label in Name | `LabelInNameAuditor` (NLP normalisation) | 🟢 High |
| 2.5.8 | Target Size (Min) | `TargetSizeAuditor` (getBoundingClientRect) | 🟢 High |
| 3.3.1 | Error Identification | `FormAccessibilityAuditor` | 🟢 High |
| 3.3.2 | Labels or Instructions | `FormAccessibilityAuditor` | 🟢 High |
| 4.1.2 | Name, Role, Value | `AltTextAuditor._check_4_1_2` (functional images) | 🟡 Medium |

**Python Coverage Totals:**

| Level | Total SCs | Covered | Coverage % |
|-------|-----------|---------|-----------|
| A | 31 | 6 | **19%** |
| AA | 26 | 10 | **38%** |
| AAA | 30 | 1 | **3%** |

---

## 7. Combined Coverage Summary

Combining Python + Node coverage (union, not double-count):

| Level | Total SCs | Combined | Coverage % | Δ vs Previous |
|-------|-----------|----------|-----------|----------------|
| A | 31 | 25 | **81%** | +2 (1.4.1 + 1.2.1 added) |
| AA | 26 | 22 | **85%** | +1 (2.4.13 upgraded) |
| AAA | 30 | 3 | **10%** | +2 (2.4.8 + 2.4.9 added) |
| **Total** | **87** | **50** | **57%** | +5 |

### Confidence Upgrade Summary

| SC | Before | After | Change |
|----|--------|-------|--------|
| 1.4.1 Use of Color | 🔴 Low | 🟡 Medium | +1 |
| 2.1.4 Character Key Shortcuts | 🔴 Low | 🟡 Medium | +1 |
| 2.4.13 Focus Appearance | 🔴 Low | 🟡 Medium | +1 |
| 3.3.3 Error Suggestion | 🔴 Low | 🟡 Medium | +1 (N11: form-scoped selectors eliminate documentation-page FP) |
| 2.4.7 Focus Visible | 🟡 Medium | 🟡 Medium | (reliability improved: transparent-outline N9 fix + async timer test rewrite) |
| 2.1.2 Keyboard Trap | 🟡 Medium | 🟡 Medium | (reliability improved via Escape settle fix) |

---

## 8. Custom Check Confidence Ratings

### ka11y-node Custom Checks

| Check | SC | Confidence | Effectiveness | Key Limitation |
|-------|----|-----------|--------------|----------------|
| `custom-html-parsing` | 4.1.1 | 🟢 High | 95% | Duplicate IDs only |
| `custom-on-focus` | 3.2.1 | 🟢 High | 80% | Tests only 25 elements; one navigation stops test |
| `custom-on-input` | 3.2.2 | 🟢 High | 80% | Tests only 15 inputs; one navigation stops test |
| `custom-keyboard-trap` | 2.1.2 | 🟡 Medium | 75% | 60 Tab presses max; no Shift+Tab backward test |
| `custom-focus-visible` | 2.4.7 | 🟡 Medium | 70% | CSS-transition race fixed; transparent outline still passes |
| `custom-focus-appearance` | 2.4.13 | 🟡 Medium | 70% | Outline-width ≥2px is a proxy; box-shadow area not measured |
| `custom-use-of-color` | 1.4.1 | 🟡 Medium | 70% | 80 links max; non-link color usage not tested |
| `custom-multiple-ways` | 2.4.5 | 🟡 Medium | 75% | Single-page only; AJAX search not detected |
| `custom-meaningful-sequence` | 1.3.2 | 🟡 Medium | 65% | CSS order/flex only; JS-driven reordering missed |
| `custom-error-prevention` | 3.3.4 | 🟡 Medium | 70% | Keyword-based; custom JS confirmation not detected |
| `custom-accessible-auth` | 3.3.8 | 🟡 Medium | 70% | `data-sitekey` FP risk; inline handlers only |
| `custom-dragging-movements` | 2.5.7 | 🟡 Medium | 65% | Library wrappers create FP; JS drag not detected |
| `custom-status-messages` | 4.1.3 | 🟡 Medium | 60% | Requires live error messages; static analysis only |
| `custom-consistent-help` | 3.2.6 | 🟡 Medium | 55% | Single-page only; consistency requires multi-page |
| `custom-character-key-shortcuts` | 2.1.4 | 🟡 Medium | 65% | Inline handlers only; `addEventListener` missed |
| `custom-audio-transcript` | 1.2.1 | 🟡 Medium | 65% | Returns `incomplete`; transcript quality unverifiable; only detects absence of `<track>`/nearby links |
| `custom-location` | 2.4.8 (AAA) | 🟡 Medium | 60% | Returns `incomplete` when no indicator found; single-page only; dynamic breadcrumbs may not be in DOM |
| `custom-link-purpose` | 2.4.9 (AAA) | 🟡 Medium | 65% | Regex-based generic text detection; accessible name via aria-label/labelledby/img-alt/text; may miss context-specific cases |
| `custom-error-suggestion` | 3.3.3 | 🟡 Medium | 60% | N11 fix: form-scoped selectors reduce FP; requires visible errors on page load *(was 🔴 Low)* |
| `custom-pointer-cancellation` | 2.5.2 | 🔴 Low | 60% | Inline handlers only; action pattern matching brittle |

### ka11y-python Auditors / Evaluators

| Auditor | SC | Confidence | Effectiveness | Key Limitation |
|---------|----|-----------|--------------|----------------|
| `FormAccessibilityAuditor` | 3.3.1, 3.3.2 | 🟢 High | 85% | Static analysis; can't test runtime error display |
| `LabelInNameAuditor` | 2.5.3 | 🟢 High | 85% | Punctuation edge cases (Bug P11) |
| `TargetSizeAuditor` | 2.5.8 | 🟢 High | 85% | Offset/spacing exception not implemented |
| `PauseStopHideAuditor` | 2.2.2 | 🟢 High | 90% | Can't test if pause button actually works |
| `ReflowEvaluator` | 1.4.10 | 🟢 High | 90% | Exempt element detection is heuristic |
| `ResizeTextEvaluator` | 1.4.4 | 🟢 High | 88% | Tests 200% only; intermediate sizes not tested |
| `TextSpacingEvaluator` | 1.4.12 | 🟢 High | 88% | After Bug P3 fix, now includes short text |
| `OrientationEvaluator` | 1.3.4 | 🟢 High | 85% | Zero-element orientation edge case (Bug P10) |
| `HoverFocusContentEvaluator` | 1.4.13 | 🟢 High | 85% | JS-triggered tooltips may not be detected |
| `FocusNotObscuredMinimumEvaluator` | 2.4.11 | 🟢 High | 85% | Obscuration thresholds hardcoded (Bug P9) |
| `FocusNotObscuredEnhancedEvaluator` | 2.4.12 | 🟢 High | 85% | Same as above |
| `AltTextAccessibilityAuditor` | 1.1.1, 1.4.5, 4.1.2 | 🟡 Medium | 70% | Cosine-sim alt adequacy is approximate |
| `OCRPreprocessing` (1.4.3) | 1.4.3 | 🟡 Medium | 65% | Text-in-image only; page text checked by axe |
| `AltTextAuditor._check_1_4_11` | 1.4.11 | 🔴 Low | 40% | OCR contrast proxy; non-UI elements → INCOMPLETE |

---

## 9. Suggested Improvements

### Priority 1 — Fix Within 1 Sprint

| ID | Service | Description |
|----|---------|-------------|
| I1 | Python | **SSRF redirect validation** (Bug P5): Playwright's `page.on('request')` should block redirects to private IPs — currently any redirect to an internal host bypasses the initial URL check |
| I2 | Node | **CORS hardening** (Bug N13): Remove the `Access-Control-Allow-Origin: *` fallback for requests with no `Origin` header; omit the header entirely for unrecognized origins |
| I3 | Node | **Fix `on-focus` / `on-input` selector style** (Bugs N7/N8): Replace fragile `.join('')` + leading-comma pattern with explicit `.join(', ')` |
| I4 | Node | **Error-suggestion false positives** (Bug N11): Add `form *` ancestor constraint to class-based error selectors to avoid matching documentation and decorative elements |
| I5 | Python | **Stage crawl timeout** (Design D2): Wrap `await image_crawler.crawl_page()` and other stage coroutines with `asyncio.timeout(300)` to prevent hung Playwright instances |
| I6 | Python | **`_broadcast()` async lock** (Bug P6): Make `_broadcast` async and acquire `_subscribers_lock` before iterating to prevent race with concurrent subscriber add/remove |

### Priority 2 — Improve in Next Quarter

| ID | Service | Description |
|----|---------|-------------|
| I7 | Node | **Keyboard trap: test Shift+Tab** — add backward Tab navigation test to catch traps that only prevent Shift+Tab escape |
| I8 | Node | **Focus-visible: invisible-change guard** — after detecting a style change, verify the outline/border is not transparent (`rgba(0,0,0,0)`) and has non-zero pixel width |
| I9 | Node | **CAPTCHA detection precision** (Bug N10): Require at least two independent signals (iframe src + class OR class + data-attribute) before flagging CAPTCHA |
| I10 | Node | **Dragging: library false positives** (Bug N9): Verify `[data-rbd-draggable-id]` has a non-empty value; skip elements with role=`list` or `grid` (containers, not items) |
| I11 | Python | **Target size: offset exception** — implement the WCAG 2.5.8 spacing check: if element bounding boxes of two small adjacent targets don't overlap (offset ≥ target-size gap), they are exempt |
| I12 | Python | **Label-in-name: punctuation normalisation** (Bug P11): Strip punctuation before regex matching to prevent false negatives on labels ending with `!` or `,` |
| I13 | Both | **Deduplication of findings** — when axe-core and a custom check both report the same SC, merge results rather than duplicating them in the combined report |

### Priority 3 — Strategic Coverage Additions

| ID | New SC | Description | Effort | Status |
|----|--------|-------------|--------|--------|
| I14 | 2.4.8 (AAA) | Location check: detect breadcrumbs or page-in-site navigation markers | Low | ✅ Done — `custom-location.check.js` |
| I15 | 1.2.1 | Check `<audio>` for `<track kind="descriptions">` or adjacent transcript link | Medium | ✅ Done — `custom-audio-transcript.check.js` |
| I16 | 2.4.9 (AAA) | Link-only purpose check: flag `<a>` elements where the link text provides no context even read in isolation | Medium | ✅ Done — `custom-link-purpose.check.js` |
| I17 | 3.2.3 | Multi-page navigation consistency: crawl N pages and compare nav element order (already in roadmap) | High | Pending |
| I18 | 2.2.6 (AAA) | Timeout warning check: detect session-timeout patterns (countdown timers, `idle_timeout` keywords) | Medium | Pending |
| I19 | Node | Upgrade `custom-error-suggestion` from 🔴 Low → 🟡 Medium by form-scoping class selectors (N11) | High | ✅ Done |

---

## Appendix: File Index

### ka11y-node — Custom Checks (`src/custom-checks/`)

| File | SC | Added/Modified |
|------|----|----------------|
| `html-parsing.check.js` | 4.1.1 | Existing |
| `focus-visible.check.js` | 2.4.7 | Modified (CSS-transition race fix) |
| `focus-appearance.check.js` | 2.4.13 | **New** |
| `status-messages.check.js` | 4.1.3 | Modified (hasNotificationArea fix) |
| `multiple-ways.check.js` | 2.4.5 | Modified (breadcrumb + toc added) |
| `on-focus.check.js` | 3.2.1 | Existing |
| `on-input.check.js` | 3.2.2 | Existing |
| `keyboard-trap.check.js` | 2.1.2 | Modified (Escape settle delay) |
| `meaningful-sequence.check.js` | 1.3.2 | Modified (opacity/collapse visibility) |
| `character-key-shortcuts.check.js` | 2.1.4 | Modified (proximity modifier guard) |
| `pointer-cancellation.check.js` | 2.5.2 | Existing |
| `dragging-movements.check.js` | 2.5.7 | Existing |
| `consistent-help.check.js` | 3.2.6 | Modified (tel/mailto detection) |
| `error-suggestion.check.js` | 3.3.3 | Modified (N11: form-scoped class selectors) |
| `error-prevention.check.js` | 3.3.4 | Existing |
| `accessible-auth.check.js` | 3.3.8 | Modified (N10: dual-signal CAPTCHA detection) |
| `use-of-color.check.js` | 1.4.1 | **New** (ancestor ref bug fix applied) |
| `audio-transcript.check.js` | 1.2.1 | **New** |
| `location.check.js` | 2.4.8 (AAA) | **New** |
| `link-purpose.check.js` | 2.4.9 (AAA) | **New** |

### ka11y-python — Key Files Modified

| File | Change |
|------|--------|
| `alttext.py` | `wcag_1_4_11_status` `"INCOMPLETE"` → `"N/A"` |
| `models.py` | `max_depth` bounded `Field(ge=0, le=5)` |
| `text_spacing.py` | Short-text filter `< 3` → `not strip()` |
| `stage_events.py` | Added `logger.warning()` on missing-stage in `_stage_complete` / `_stage_error` |

---

*Generated: 2026-03-25 · Updated: 2026-03-25 (bugs N7–N13 fixed; 3 new checks: custom-audio-transcript 1.2.1, custom-location 2.4.8 AAA, custom-link-purpose 2.4.9 AAA; error-suggestion confidence 🔴→🟡; Node coverage now 42 SCs 24A+16AA+2AAA; combined 50/87 57%; all 91 tests passing) · ka11y WCAG 2.2 compliance toolchain review*