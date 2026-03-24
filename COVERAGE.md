# ka11y — WCAG 2.2 Coverage Report

Combined coverage across the **Python pipeline** (`ka11y-python`) and the **Node.js axe-core engine** (`ka11y-node`).

Legend: ✅ Covered · ❌ Not covered · 🔶 Partial (automated checks only, not full SC)

Confidence: 🟢 High (reliable, low FP/FN) · 🟡 Medium (heuristic, some FP/FN expected) · 🔴 Low (limited detection, flags for manual review) · — (not covered)

---

## Summary

| Level | Total SCs | Python | Node (axe+custom) | Combined | Combined % | Missing |
|-------|-----------|--------|-------------------|----------|------------|---------|
| A     | 31        | 6      | 23                | 24       | **77 %**   | 7       |
| AA    | 26        | 10     | 14                | 20       | **77 %**   | 6       |
| AAA   | 30        | 1      | 0                 | 1        | **3 %**    | 29      |
| **Total** | **87** | **17** | **37**        | **45**   | **52 %**   | **42** |

> Numbers reflect *automatable checks only*. Many criteria (colour contrast,
> reading level, meaningful sequence) require human review and cannot be
> 100 % automated.

---

## Level A — 31 Success Criteria

| SC | Name | Python | Node (axe) | Combined | Confidence | Notes |
|----|------|--------|------------|----------|------------|-------|
| 1.1.1 | Non-text Content | ✅ AltTextAuditor | ✅ axe `image-alt`, `input-image-alt` | ✅ | 🟢 High | Both; Python adds OCR cosine-similarity alt-adequacy check |
| 1.2.1 | Audio-only and Video-only (Prerecorded) | ❌ | ❌ | ❌ | — | Requires content inspection |
| 1.2.2 | Captions (Prerecorded) | ❌ | ✅ axe `video-caption` | ✅ | 🟢 High | axe reliably checks `<video>` for missing `<track kind="captions">` |
| 1.2.3 | Audio Description or Media Alternative (Prerecorded) | ❌ | ❌ | ❌ | — | Requires media analysis |
| 1.3.1 | Info and Relationships | ❌ | ✅ axe `landmark-*`, `list`, `table-*` | ✅ | 🟢 High | axe landmark/table rules are well-established |
| 1.3.2 | Meaningful Sequence | ❌ | 🔶 Node `custom-meaningful-sequence` | 🔶 | 🟡 Medium | Fixed: now detects `flex-direction: row/column-reverse` AND CSS `order` that actually reorders from DOM sequence |
| 1.3.3 | Sensory Characteristics | ❌ | ❌ | ❌ | — | Requires NLP content analysis |
| 1.4.1 | Use of Color | ❌ | 🔶 axe `link-in-text-block` | 🔶 | 🔴 Low | Detects links distinguished only by colour; not fully automatable |
| 1.4.2 | Audio Control | ❌ | 🔶 axe `no-autoplay-audio` | 🔶 | 🟡 Medium | Detects auto-playing audio lacking controls; `audio-caption` rule deprecated in axe v4 |
| 2.1.1 | Keyboard | ❌ | ✅ axe `scrollable-region-focusable`, `frame-focusable-content`, `server-side-image-map` | ✅ | 🟢 High | axe rules are reliable and comprehensive |
| 2.1.2 | No Keyboard Trap | ❌ | 🔶 Node `custom-keyboard-trap` | 🔶 | 🟡 Medium | Fixed: consecutive-repeat key tracking (not cumulative), position-based element ID prevents false positives from shared classes |
| 2.1.4 | Character Key Shortcuts | ❌ | 🔶 Node `custom-character-key-shortcuts` | 🔶 | 🔴 Low | Only catches `accesskey` attrs and inline handlers; misses `addEventListener`-based shortcuts |
| 2.2.1 | Timing Adjustable | ❌ | 🔶 axe `meta-refresh` | 🔶 | 🔴 Low | axe detects `<meta http-equiv="refresh">` only; JS timers and session timeouts not detectable statically |
| 2.2.2 | Pause, Stop, Hide | ✅ PauseStopHideAuditor | 🔶 axe `blink`, `marquee` only | ✅ | 🟢 High | Python covers CSS anims, carousels, autoplay video, animated GIFs — far beyond axe |
| 2.3.1 | Three Flashes or Below Threshold | ❌ | ❌ | ❌ | — | Requires video frame analysis |
| 2.4.1 | Bypass Blocks | ❌ | ✅ axe `bypass` | ✅ | 🟢 High | axe `bypass` reliably checks for skip links and landmarks |
| 2.4.2 | Page Titled | ❌ | ✅ axe `document-title` | ✅ | 🟢 High | Simple deterministic check |
| 2.4.3 | Focus Order | ❌ | 🔶 axe `tabindex` | 🔶 | 🔴 Low | Detects positive tabindex only; full logical order requires manual check |
| 2.4.4 | Link Purpose (In Context) | ❌ | ✅ axe `link-name`, `area-alt` | ✅ | 🟢 High | axe reliably catches empty link names |
| 2.5.1 | Pointer Gestures | ❌ | ❌ | ❌ | — | Requires JS event listener introspection |
| 2.5.2 | Pointer Cancellation | ❌ | 🔶 Node `custom-pointer-cancellation` | 🔶 | 🔴 Low | Fixed: action-pattern matching + onpointerup check; only inline handlers detectable, not `addEventListener` |
| 2.5.3 | Label in Name | ✅ LabelInNameAuditor | ✅ axe `label-content-name-mismatch` | ✅ | 🟢 High | Both tools reliable; Python uses NLP normalisation |
| 2.5.4 | Motion Actuation | ❌ | ❌ | ❌ | — | Requires device-motion API analysis |
| 3.1.1 | Language of Page | ❌ | ✅ axe `html-has-lang`, `html-lang-valid` | ✅ | 🟢 High | Simple deterministic check |
| 3.2.1 | On Focus | ❌ | 🔶 Node `custom-on-focus` | 🔶 | 🟡 Medium | Fixed: now includes form controls (input/select/textarea) in focus selector; URL-change + framenavigated detection |
| 3.2.2 | On Input | ❌ | 🔶 Node `custom-on-input` | 🔶 | 🟡 Medium | Fixed: `<select>` onchange included; type-appropriate test chars; URL-change detection |
| 3.3.1 | Error Identification | ✅ FormAuditor | ❌ | ✅ | 🟢 High | Python only; checks required fields + error messaging patterns |
| 3.3.2 | Labels or Instructions | ✅ FormAuditor | 🔶 axe `form-field-multiple-labels` | ✅ | 🟢 High | Python covers fully; axe detects multiple-label ambiguity only |
| 3.3.7 | Redundant Entry *(WCAG 2.2 new)* | ❌ | ❌ | ❌ | — | Requires multi-step form tracking |
| 4.1.1 | Parsing | ❌ | 🔶 axe `duplicate-id` + Node `custom-html-parsing` | 🔶 | 🟡 Medium | Duplicate-ID detection is reliable; broader parsing errors require HTML validator |
| 4.1.2 | Name, Role, Value | ✅ AltTextAuditor (`_check_4_1_2`) | ✅ axe `aria-*`, `button-name` | ✅ | 🟢 High | Both; Python checks functional images; axe covers ARIA roles/states |

**Level A covered: 24 / 31 (77 %) · includes 11 partial (🔶) · Missing: 7**

### Missing Level A
1. **1.2.1** — Audio-only and Video-only (Prerecorded)
2. **1.2.3** — Audio Description or Media Alternative (Prerecorded)
3. **1.3.3** — Sensory Characteristics
4. **2.3.1** — Three Flashes or Below Threshold
5. **2.5.1** — Pointer Gestures
6. **2.5.4** — Motion Actuation
7. **3.3.7** — Redundant Entry *(WCAG 2.2 new)*

---

## Level AA — 26 Additional Success Criteria

| SC | Name | Python | Node (axe) | Combined | Confidence | Notes |
|----|------|--------|------------|----------|------------|-------|
| 1.2.4 | Captions (Live) | ❌ | ❌ | ❌ | — | Live stream; not automatable |
| 1.2.5 | Audio Description (Prerecorded) | ❌ | ❌ | ❌ | — | Requires media analysis |
| 1.3.4 | Orientation | ✅ OrientationEvaluator (rendered) | ✅ axe `css-orientation-lock` | ✅ | 🟢 High | Both; Python takes actual portrait+landscape snapshots |
| 1.3.5 | Identify Input Purpose | ❌ | ✅ axe `autocomplete-valid` | ✅ | 🟢 High | axe autocomplete-valid is reliable |
| 1.4.3 | Contrast (Minimum) | ✅ `OCRPreprocessing` + `_contrast_to_findings` | ✅ axe `color-contrast` | ✅ | 🟢 High | Both; Python checks text-in-image contrast via OCR; axe checks page text |
| 1.4.4 | Resize Text | ✅ ResizeTextEvaluator (rendered) | ✅ axe `meta-viewport` | ✅ | 🟢 High | Both; Python detects overflow/clip after 200% zoom |
| 1.4.5 | Images of Text | 🔶 `AltTextAuditor` (`_check_1_4_5`) | ❌ | 🔶 | 🟡 Medium | OCR detects text in image; logo-exempt (essential exception); false positives possible on decorative images |
| 1.4.10 | Reflow | ✅ ReflowEvaluator (rendered) | ❌ | ✅ | 🟢 High | Playwright viewport resize to 320 px; detects horizontal scroll and oversized elements |
| 1.4.11 | Non-text Contrast | 🔶 `AltTextAuditor` (`_check_1_4_11`) | ❌ | 🔶 | 🔴 Low | OCR contrast ratio used as proxy for button/icon images only; non-UI elements → INCOMPLETE |
| 1.4.12 | Text Spacing | ✅ TextSpacingAuditor (crawler) + TextSpacingEvaluator (rendered) | 🔶 axe `avoid-inline-spacing` | ✅ | 🟢 High | Static + rendered Playwright override test; comprehensive coverage |
| 1.4.13 | Content on Hover or Focus | ✅ HoverFocusContentEvaluator (rendered) | ❌ | ✅ | 🟢 High | Playwright hover simulation — checks dismissible, persistent, hoverable |
| 2.4.5 | Multiple Ways | ❌ | 🔶 Node `custom-multiple-ways` | 🔶 | 🟡 Medium | Heuristic: search form, sitemap link, nav elements; passes if ≥ 2 found; misses AJAX/JS-based search |
| 2.4.6 | Headings and Labels | ❌ | ✅ axe `heading-order`, `empty-heading` | ✅ | 🟢 High | axe heading-order is reliable |
| 2.4.7 | Focus Visible | ❌ | 🔶 Node `custom-focus-visible` + axe `focus-visible` | 🔶 | 🟡 Medium | Fixed: now checks 50 elements, detects color/opacity/border changes; misses CSS `:focus-within` and Shadow DOM |
| 2.4.11 | Focus Not Obscured (Minimum) *(WCAG 2.2 new)* | ✅ FocusNotObscuredMinimumEvaluator (rendered) | ❌ | ✅ | 🟢 High | getBoundingClientRect obscuration ratio measurement; full obscuration = FAIL |
| 2.4.13 | Focus Appearance *(WCAG 2.2 new)* | ❌ | 🔶 axe `focus-appearance` | 🔶 | 🔴 Low | axe rule is experimental; does not measure contrast ratio of focus ring |
| 2.5.7 | Dragging Movements *(WCAG 2.2 new)* | ❌ | 🔶 Node `custom-dragging-movements` | 🔶 | 🟡 Medium | Fixed: detects native drag + D&D libraries; checks alternatives in element AND parent; misses `addEventListener`-based drag |
| 2.5.8 | Target Size (Minimum) *(WCAG 2.2 new)* | ✅ TargetSizeAuditor | ❌ | ✅ | 🟢 High | Bounding-box measurement; inline + UA-controlled exceptions detected |
| 3.1.2 | Language of Parts | ❌ | ✅ axe `valid-lang` | ✅ | 🟢 High | axe valid-lang is reliable |
| 3.2.3 | Consistent Navigation | ❌ | ❌ | ❌ | — | Requires multi-page analysis |
| 3.2.4 | Consistent Identification | ❌ | ❌ | ❌ | — | Requires multi-page analysis |
| 3.2.6 | Consistent Help *(WCAG 2.2 new)* | ❌ | 🔶 Node `custom-consistent-help` | 🔶 | 🟡 Medium | Keyword-based detection of help/contact links; reports position; single-page only — consistency across pages requires multi-page crawl |
| 3.3.3 | Error Suggestion | ❌ | 🔶 Node `custom-error-suggestion` | 🔶 | 🔴 Low | Fixed: narrowed error selectors to reduce FP; heuristic text analysis; requires errors to be visible on page load |
| 3.3.4 | Error Prevention (Legal, Financial, Data) | ❌ | 🔶 Node `custom-error-prevention` | 🔶 | 🟡 Medium | Fixed: expanded financial/legal/destructive patterns + multi-step wizard detection; keyword-based, no semantic understanding |
| 3.3.8 | Accessible Authentication (Minimum) *(WCAG 2.2 new)* | ❌ | 🔶 Node `custom-accessible-auth` | 🔶 | 🟡 Medium | Fixed: expanded CAPTCHA alt detection, paste-blocking, cognitive tests; misses `addEventListener`-based paste blocking |
| 4.1.3 | Status Messages | ❌ | 🔶 Node `custom-status-messages` | 🔶 | 🟡 Medium | Fixed: detects forms + search results + cart/counter + notification areas; live region presence verified |

**Level AA covered: 20 / 26 (77 %) · includes 11 partial (🔶) · Missing: 6**

### Missing Level AA
1. **1.2.4** — Captions (Live)
2. **1.2.5** — Audio Description (Prerecorded)
3. **3.2.3** — Consistent Navigation
4. **3.2.4** — Consistent Identification

---

## Level AAA — 30 Additional Success Criteria

> **1 criterion now covered (2.4.12 by Python rendered evaluator).** Most AAA criteria require deep content
> analysis, multi-page behavioural testing, or human judgement and remain beyond
> the scope of automated tools.

| SC | Name | Combined | Notes |
|----|------|----------|-------|
| 1.2.6 | Sign Language (Prerecorded) | ❌ | |
| 1.2.7 | Extended Audio Description (Prerecorded) | ❌ | |
| 1.2.8 | Media Alternative (Prerecorded) | ❌ | |
| 1.2.9 | Audio-only (Live) | ❌ | |
| 1.3.6 | Identify Purpose | ❌ | |
| 1.4.6 | Contrast (Enhanced) | ❌ | Higher ratio variant of 1.4.3 |
| 1.4.7 | Low or No Background Audio | ❌ | |
| 1.4.8 | Visual Presentation | ❌ | |
| 1.4.9 | Images of Text (No Exception) | ❌ | |
| 2.1.3 | Keyboard (No Exception) | ❌ | |
| 2.2.3 | No Timing | ❌ | |
| 2.2.4 | Interruptions | ❌ | |
| 2.2.5 | Re-authenticating | ❌ | |
| 2.2.6 | Timeouts | ❌ | |
| 2.3.2 | Three Flashes | ❌ | |
| 2.3.3 | Animation from Interactions | ❌ | |
| 2.4.8 | Location | ❌ | |
| 2.4.9 | Link Purpose (Link Only) | ❌ | |
| 2.4.10 | Section Headings | ❌ | |
| 2.4.12 | Focus Not Obscured (Enhanced) *(WCAG 2.2 new)* | ✅ FocusNotObscuredEnhancedEvaluator (rendered) | Python: stricter than 2.4.11 — any non-trivial overlap fails |
| 2.5.5 | Target Size | ❌ | |
| 2.5.6 | Concurrent Input Mechanisms | ❌ | |
| 3.1.3 | Unusual Words | ❌ | |
| 3.1.4 | Abbreviations | ❌ | |
| 3.1.5 | Reading Level | ❌ | |
| 3.1.6 | Pronunciation | ❌ | |
| 3.2.5 | Change on Request | ❌ | |
| 3.3.5 | Help | ❌ | |
| 3.3.6 | Error Prevention (All) | ❌ | |
| 3.3.9 | Accessible Authentication (Enhanced) *(WCAG 2.2 new)* | ❌ | |

**Level AAA covered: 1 / 30 (3 %) · 2.4.12 now covered by Python rendered evaluator**

---

## Planned Improvements

The following uncovered criteria are **partially automatable** and are candidates
for future Python auditors:

| Priority | SC | Name | Approach |
|----------|----|------|----------|
| Medium | **2.4.13** | Focus Appearance | Measure CSS focus-ring area and contrast via Playwright (Python rendered evaluator) |
| Low | **3.3.7** | Redundant Entry | Track form field names across multi-step flows; flag re-asked required fields |
| Low | **3.2.3** | Consistent Navigation | Multi-page crawl: compare nav element order across pages |
| Low | **3.2.4** | Consistent Identification | Multi-page crawl: compare component labels/names across pages |

> **Previously planned, now implemented:** 2.5.8 Target Size (Minimum), 2.4.11 Focus Not Obscured (Minimum), 1.4.13 Content on Hover or Focus, 3.2.6 Consistent Help (Node), 2.5.7 Dragging Movements (Node), 3.3.8 Accessible Authentication (Node), 3.3.3 Error Suggestion (Node), 3.3.4 Error Prevention (Node), 2.1.4 Character Key Shortcuts (Node), 2.5.2 Pointer Cancellation (Node).

---

## Tool Coverage Breakdown

### Python (`ka11y-python`) — Unique Capabilities

| Auditor / Evaluator | WCAG SC | What it detects beyond axe |
|---------------------|---------|---------------------------|
| `AltTextAccessibilityAuditor` | 1.1.1, 1.4.5, 1.4.11, 4.1.2 | OCR text-in-image detection, generic alt text ("image", "photo"), cosine-similarity alt adequacy; `_check_4_1_2` validates accessible name for functional images (logos, icons, buttons); `_check_1_4_5` flags non-logo images with OCR text; `_check_1_4_11` checks button/icon contrast ratio via OCR proxy (3:1 threshold) |
| `OCRPreprocessing` (`_contrast_to_findings`) | 1.4.3 | EasyOCR detects text regions in images; `contrast_analyser` computes luminance-based contrast ratio per bbox; flags AA-normal failures (< 4.5:1) |
| `FormAccessibilityAuditor` | 3.3.1, 3.3.2 | `required` without error messaging, placeholder-only labels, hidden-label patterns, missing autocomplete on personal-data fields |
| `LabelInNameAuditor` | 2.5.3 | Checks visible label text is substring of accessible name using NLP normalisation |
| `PauseStopHideAuditor` | 2.2.2 | CSS keyframe animations (> 5 s / infinite), autoplay video, animated GIFs, carousels (Bootstrap/Swiper/Slick/Owl/Glide/Splide) — all missed by axe |
| `TargetSizeAuditor` | 2.5.8 | Measures rendered bounding-box (getBoundingClientRect) of all interactive elements; detects inline-link and UA-controlled exceptions automatically |
| `TextSpacingAuditor` (crawler) | 1.4.12 | Static detection of fixed-height containers with overflow:hidden that clip user-adjusted text spacing |
| `ReflowEvaluator` (rendered) | 1.4.10 | Playwright viewport resize to 320 px; detects actual horizontal scroll and oversized elements |
| `ResizeTextEvaluator` (rendered) | 1.4.4 | Playwright 200% text-size override; flags overflow, scroll and clipped text |
| `TextSpacingEvaluator` (rendered) | 1.4.12 | Playwright CSS override (1.5× line-height, 0.12em letter-spacing, etc.); flags newly-clipped elements |
| `OrientationEvaluator` (rendered) | 1.3.4 | Both portrait + landscape snapshots; detects "please rotate" overlays and missing content in either orientation |
| `HoverFocusContentEvaluator` (rendered) | 1.4.13 | Playwright hover simulation; checks popup appeared, dismissible-by-Escape, pointer-can-move-over |
| `FocusNotObscuredMinimumEvaluator` (rendered) | 2.4.11 | Tab-key focus walk; measures obscuration ratio via getBoundingClientRect; full obscuration = FAIL, partial = NEEDS_REVIEW |
| `FocusNotObscuredEnhancedEvaluator` (rendered) | 2.4.12 (AAA) | Same as above but stricter: any non-trivial overlap (≥ 10%) = FAIL |

### Node.js (`ka11y-node`) — axe-core + Custom Puppeteer Checks

Covers **37 unique WCAG SCs** (23 Level A + 14 Level AA) through axe-core v4.9+ and 15 custom Puppeteer check modules.
Results are merged and returned grouped by `successCriteriaId` with `fail / pass / incomplete` status per rule.

**Level A SCs (23):** 1.1.1, 1.2.2, 1.3.1, 1.3.2 🔶, 1.4.1 🔶, 1.4.2 🔶, 2.1.1, 2.1.2 🔶, 2.1.4 🔶, 2.2.1 🔶, 2.2.2, 2.4.1, 2.4.2, 2.4.3 🔶, 2.4.4, 2.5.2 🔶, 2.5.3, 3.1.1, 3.2.1 🔶, 3.2.2 🔶, 3.3.2 🔶, 4.1.1 🔶, 4.1.2

**Level AA SCs (14):** 1.3.4, 1.3.5, 1.4.3, 1.4.4, 1.4.12 🔶, 2.4.5 🔶, 2.4.6, 2.4.7 🔶, 2.4.13 🔶, 2.5.7 🔶, 3.1.2, 3.2.6 🔶, 3.3.3 🔶, 3.3.4 🔶, 3.3.8 🔶, 4.1.3 🔶

**axe-core config:** `wcag22a` and `wcag22aa` tags added to `runOnly` — activates WCAG 2.2 rules (`focus-appearance` → 2.4.13, `focus-visible` → 2.4.7, `target-size` → 2.5.8).

**Custom check modules** (`src/custom-checks/`):

| Module | SC | Mechanism |
|---|---|---|
| `html-parsing.check.js` | 4.1.1 | DOM scan for duplicate `id` attributes |
| `focus-visible.check.js` | 2.4.7 | Compare computed `outline`/`box-shadow` before/after `el.focus()` |
| `status-messages.check.js` | 4.1.3 | Check `role="status/alert"` and `aria-live` presence; fail if forms exist with no live regions |
| `multiple-ways.check.js` | 2.4.5 | Detect search form, sitemap link, nav elements; pass if ≥ 2 found |
| `on-focus.check.js` | 3.2.1 | Focus each interactive element; detect unexpected URL navigation |
| `on-input.check.js` | 3.2.2 | Type into each input; detect unexpected URL navigation |
| `keyboard-trap.check.js` | 2.1.2 | Tab-walk 60 iterations; detect focus cycling + Escape-key escape test |
| `meaningful-sequence.check.js` | 1.3.2 | Detect CSS `order` property in flex/grid containers diverging from DOM order |
| `character-key-shortcuts.check.js` | 2.1.4 | Detect `accesskey` single-char attributes and inline key handlers without modifier keys |
| `pointer-cancellation.check.js` | 2.5.2 | Detect `onmousedown`/`onpointerdown` handlers without matching `onmouseup`/`onclick` cancellation path |
| `dragging-movements.check.js` | 2.5.7 | Detect `draggable="true"`, `ondragstart`, D&D library markers; check for single-pointer button alternative |
| `consistent-help.check.js` | 3.2.6 | Detect help/contact/support links and chat widgets; report position (header/footer/nav); flag absence |
| `error-suggestion.check.js` | 3.3.3 | Check visible error messages for correction guidance; flag terse messages like "Invalid" or "Error" |
| `error-prevention.check.js` | 3.3.4 | Detect financial/legal/destructive forms; check for review step, confirmation checkbox, or preview button |
| `accessible-auth.check.js` | 3.3.8 | Detect auth forms; flag CAPTCHA without audio alternative, paste-blocked password fields, cognitive puzzles |

**Node.js future possibilities (custom Puppeteer):**

| SC | Name | Approach |
|----|------|----------|
| 1.4.5 | Images of Text | `page.evaluate` to find `<img>` inside `<button>`/`<a>` with matching text content; or Canvas pixel-sampling after rendering to detect text-like patterns. Requires OCR — full implementation is Python-side. |
| 1.4.11 | Non-text Contrast | Puppeteer screenshot + Canvas pixel-sampling around UI component boundaries; measure contrast of component edge colour vs adjacent background. Complex but feasible without OCR. |

---

*Generated: 2026-03-17 · Updated: 2026-03-24 (axe v4.9 audit + 15 custom Puppeteer checks + Python 1.4.3/1.4.5/1.4.11 image pipeline; +7 new Node checks: 2.1.4, 2.5.2, 2.5.7, 3.2.6, 3.3.3, 3.3.4, 3.3.8) · WCAG 2.2 (W3C Recommendation 2023-10-05)*
