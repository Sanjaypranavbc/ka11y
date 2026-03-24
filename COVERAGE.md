# ka11y — WCAG 2.2 Coverage Report

Combined coverage across the **Python pipeline** (`ka11y-python`) and the **Node.js axe-core engine** (`ka11y-node`).

Legend: ✅ Covered · ❌ Not covered · 🔶 Partial (automated checks only, not full SC)

---

## Summary

| Level | Total SCs | Python | Node (axe+custom) | Combined | Combined % | Missing |
|-------|-----------|--------|-------------------|----------|------------|---------|
| A     | 31        | 6      | 21                | 22       | **71 %**   | 9       |
| AA    | 26        | 10     | 9                 | 15       | **58 %**   | 11      |
| AAA   | 30        | 1      | 0                 | 1        | **3 %**    | 29      |
| **Total** | **87** | **17** | **30**         | **38**   | **44 %**   | **49** |

> Numbers reflect *automatable checks only*. Many criteria (colour contrast,
> reading level, meaningful sequence) require human review and cannot be
> 100 % automated.

---

## Level A — 31 Success Criteria

| SC | Name | Python | Node (axe) | Combined | Notes |
|----|------|--------|------------|----------|-------|
| 1.1.1 | Non-text Content | ✅ AltTextAuditor | ✅ axe `image-alt`, `input-image-alt` | ✅ | Both; Python adds OCR contrast |
| 1.2.1 | Audio-only and Video-only (Prerecorded) | ❌ | ❌ | ❌ | Requires content inspection |
| 1.2.2 | Captions (Prerecorded) | ❌ | ✅ axe `video-caption` | ✅ | axe checks `<video>` for missing `<track kind="captions">` |
| 1.2.3 | Audio Description or Media Alternative (Prerecorded) | ❌ | ❌ | ❌ | Requires media analysis |
| 1.3.1 | Info and Relationships | ❌ | ✅ axe `landmark-*`, `list`, `table-*` | ✅ | |
| 1.3.2 | Meaningful Sequence | ❌ | 🔶 Node `custom-meaningful-sequence` | 🔶 | Detects CSS `order` property diverging from DOM order in flex/grid containers |
| 1.3.3 | Sensory Characteristics | ❌ | ❌ | ❌ | Requires NLP content analysis |
| 1.4.1 | Use of Color | ❌ | 🔶 axe `link-in-text-block` | 🔶 | Detects links distinguished only by colour; not fully automatable |
| 1.4.2 | Audio Control | ❌ | 🔶 axe `no-autoplay-audio` | 🔶 | Detects auto-playing audio lacking controls; `audio-caption` rule is deprecated in axe v4 |
| 2.1.1 | Keyboard | ❌ | ✅ axe `scrollable-region-focusable`, `frame-focusable-content`, `server-side-image-map` | ✅ | |
| 2.1.2 | No Keyboard Trap | ❌ | 🔶 Node `custom-keyboard-trap` | 🔶 | Puppeteer Tab-walk: detects focus cycling on same element; Escape-key escape test |
| 2.1.4 | Character Key Shortcuts | ❌ | ❌ | ❌ | Requires JS behaviour analysis |
| 2.2.1 | Timing Adjustable | ❌ | 🔶 axe `meta-refresh` | ❌ | axe detects `<meta http-equiv="refresh">` only; JS timers not covered |
| 2.2.2 | Pause, Stop, Hide | ✅ PauseStopHideAuditor | 🔶 axe `blink`, `marquee` only | ✅ | Python goes beyond axe (CSS anims, carousels, autoplay video, GIFs) |
| 2.3.1 | Three Flashes or Below Threshold | ❌ | ❌ | ❌ | Requires video frame analysis |
| 2.4.1 | Bypass Blocks | ❌ | ✅ axe `bypass` | ✅ | |
| 2.4.2 | Page Titled | ❌ | ✅ axe `document-title` | ✅ | |
| 2.4.3 | Focus Order | ❌ | 🔶 axe `tabindex` | 🔶 | Full order requires manual check |
| 2.4.4 | Link Purpose (In Context) | ❌ | ✅ axe `link-name`, `area-alt` | ✅ | `duplicate-id-active` is deprecated in axe v4 |
| 2.5.1 | Pointer Gestures | ❌ | ❌ | ❌ | Requires JS gesture inspection |
| 2.5.2 | Pointer Cancellation | ❌ | ❌ | ❌ | Requires event handler analysis |
| 2.5.3 | Label in Name | ✅ LabelInNameAuditor | ✅ axe `label-content-name-mismatch` | ✅ | Both |
| 2.5.4 | Motion Actuation | ❌ | ❌ | ❌ | Requires device-motion API analysis |
| 3.1.1 | Language of Page | ❌ | ✅ axe `html-has-lang`, `html-lang-valid` | ✅ | |
| 3.2.1 | On Focus | ❌ | 🔶 Node `custom-on-focus` | 🔶 | Puppeteer: focuses each interactive element, detects unexpected URL change or navigation |
| 3.2.2 | On Input | ❌ | 🔶 Node `custom-on-input` | 🔶 | Puppeteer: types into each input, detects unexpected URL change or navigation |
| 3.3.1 | Error Identification | ✅ FormAuditor | ❌ | ✅ | Python only; axe `aria-required-attr` maps to SC 4.1.2 (wcag412 tag), not 3.3.1 |
| 3.3.2 | Labels or Instructions | ✅ FormAuditor | 🔶 axe `form-field-multiple-labels` | ✅ | Python covers fully; axe detects multiple-label ambiguity only; `label` maps to 4.1.2 |
| 3.3.7 | Redundant Entry *(WCAG 2.2 new)* | ❌ | ❌ | ❌ | Requires multi-step form tracking |
| 4.1.1 | Parsing | ❌ | 🔶 axe `duplicate-id` (RULE_SC_FALLBACK) + Node `custom-html-parsing` | 🔶 | axe still runs `duplicate-id` under wcag2a-obsolete; custom check adds DOM-level duplicate-ID scan |
| 4.1.2 | Name, Role, Value | ✅ AltTextAuditor (`_check_4_1_2`) | ✅ axe `aria-*`, `button-name`, `form-field-multiple-labels` | ✅ | Both; Python checks functional images (logos, icons, buttons) |

**Level A covered: 22 / 31 (71 %) · includes 9 partial (🔶) · Missing: 9**

### Missing Level A
1. **1.2.1** — Audio-only and Video-only (Prerecorded)
2. **1.2.3** — Audio Description or Media Alternative (Prerecorded)
3. **1.3.3** — Sensory Characteristics
4. **2.1.4** — Character Key Shortcuts
5. **2.3.1** — Three Flashes or Below Threshold
6. **2.5.1** — Pointer Gestures
7. **2.5.2** — Pointer Cancellation
8. **2.5.4** — Motion Actuation
9. **3.3.7** — Redundant Entry *(WCAG 2.2 new)*

---

## Level AA — 26 Additional Success Criteria

| SC | Name | Python | Node (axe) | Combined | Notes |
|----|------|--------|------------|----------|-------|
| 1.2.4 | Captions (Live) | ❌ | ❌ | ❌ | Live stream; not automatable |
| 1.2.5 | Audio Description (Prerecorded) | ❌ | ❌ | ❌ | Requires media analysis |
| 1.3.4 | Orientation | ✅ OrientationEvaluator (rendered) | ✅ axe `css-orientation-lock` | ✅ | Both |
| 1.3.5 | Identify Input Purpose | ❌ | ✅ axe `autocomplete-valid` | ✅ | |
| 1.4.3 | Contrast (Minimum) | ✅ `OCRPreprocessing` + `_contrast_to_findings` | ✅ axe `color-contrast` | ✅ | Both; Python checks text-in-image contrast (OCR bbox) via `contrast_analyser`; axe checks page text |
| 1.4.4 | Resize Text | ✅ ResizeTextEvaluator (rendered) | ✅ axe `meta-viewport` | ✅ | Both; Python detects overflow/clip after 200% zoom |
| 1.4.5 | Images of Text | 🔶 `AltTextAuditor` (`_check_1_4_5`) | ❌ | 🔶 | Python: OCR detects text in image + classifier determines type; logos exempt (essential exception); non-logo images with OCR text → FAIL |
| 1.4.10 | Reflow | ✅ ReflowEvaluator (rendered) | ❌ | ✅ | Python only; axe `meta-viewport` maps to SC 1.4.4 not 1.4.10 |
| 1.4.11 | Non-text Contrast | 🔶 `AltTextAuditor` (`_check_1_4_11`) | ❌ | 🔶 | Python: OCR contrast ratio used as proxy for button/icon images (3:1 threshold); non-UI or no OCR data → INCOMPLETE; `non-text-contrast` absent from axe v4.11.1 |
| 1.4.12 | Text Spacing | ✅ TextSpacingAuditor (crawler) + TextSpacingEvaluator (rendered) | 🔶 axe `avoid-inline-spacing` | ✅ | Python: static fixed-height/overflow detection + Playwright override test |
| 1.4.13 | Content on Hover or Focus | ✅ HoverFocusContentEvaluator (rendered) | ❌ | ✅ | Python: Playwright hover simulation — checks dismissible, persistent, hoverable |
| 2.4.5 | Multiple Ways | ❌ | 🔶 Node `custom-multiple-ways` | 🔶 | Heuristic: checks for search form, sitemap link, and nav elements; passes if ≥ 2 found |
| 2.4.6 | Headings and Labels | ❌ | ✅ axe `heading-order`, `empty-heading` | ✅ | |
| 2.4.7 | Focus Visible | ❌ | 🔶 Node `custom-focus-visible` + axe `focus-visible` (RULE_SC_FALLBACK + wcag22aa tag) | 🔶 | Custom check: Puppeteer compares computed outline/box-shadow before/after focus for each focusable element |
| 2.4.11 | Focus Not Obscured (Minimum) *(WCAG 2.2 new)* | ✅ FocusNotObscuredMinimumEvaluator (rendered) | ❌ | ✅ | Python: measures obscuration ratio via getBoundingClientRect; full obscuration = FAIL |
| 2.4.13 | Focus Appearance *(WCAG 2.2 new)* | ❌ | 🔶 axe `focus-appearance` (RULE_SC_FALLBACK + wcag22aa tag) | 🔶 | axe rule active after adding wcag22aa tag to runOnly |
| 2.5.7 | Dragging Movements *(WCAG 2.2 new)* | ❌ | ❌ | ❌ | Requires gesture/API inspection |
| 2.5.8 | Target Size (Minimum) *(WCAG 2.2 new)* | ✅ TargetSizeAuditor | ❌ | ✅ | Measures rendered bounding-box; inline + UA-controlled exceptions detected |
| 3.1.2 | Language of Parts | ❌ | ✅ axe `valid-lang` | ✅ | |
| 3.2.3 | Consistent Navigation | ❌ | ❌ | ❌ | Requires multi-page analysis |
| 3.2.4 | Consistent Identification | ❌ | ❌ | ❌ | Requires multi-page analysis |
| 3.2.6 | Consistent Help *(WCAG 2.2 new)* | ❌ | ❌ | ❌ | Requires multi-page layout analysis |
| 3.3.3 | Error Suggestion | ❌ | ❌ | ❌ | No axe rule with wcag333 tag in v4.11.1 |
| 3.3.4 | Error Prevention (Legal, Financial, Data) | ❌ | ❌ | ❌ | Requires form-flow analysis |
| 3.3.8 | Accessible Authentication (Minimum) *(WCAG 2.2 new)* | ❌ | ❌ | ❌ | Requires auth-flow analysis |
| 4.1.3 | Status Messages | ❌ | 🔶 Node `custom-status-messages` | 🔶 | Checks for ARIA live regions; fails if forms exist without any live region |

**Level AA covered: 15 / 26 (58 %) · includes 6 partial (🔶) · Missing: 11**

### Missing Level AA
1. **1.2.4** — Captions (Live)
2. **1.2.5** — Audio Description (Prerecorded)
3. **2.5.7** — Dragging Movements *(WCAG 2.2 new)*
4. **3.2.3** — Consistent Navigation
5. **3.2.4** — Consistent Identification
6. **3.2.6** — Consistent Help *(WCAG 2.2 new)*
7. **3.3.3** — Error Suggestion
8. **3.3.4** — Error Prevention (Legal, Financial, Data)
9. **3.3.8** — Accessible Authentication (Minimum) *(WCAG 2.2 new)*

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
| Medium | **3.2.6** | Consistent Help | Check each page for `<a>` or `<button>` containing "help", "contact", "support" in the same position across pages |
| Medium | **2.5.7** | Dragging Movements | Detect drag-and-drop widgets; verify single-pointer alternative exists |
| Medium | **2.4.13** | Focus Appearance | Measure CSS focus-ring area and contrast via Playwright |
| Low | **3.3.7** | Redundant Entry | Track form field names across multi-step flows; flag re-asked required fields |
| Low | **3.3.8** | Accessible Authentication | Detect login forms; flag if CAPTCHA present with no alternative |

> **Previously planned, now implemented:** 2.5.8 Target Size (Minimum), 2.4.11 Focus Not Obscured (Minimum), 1.4.13 Content on Hover or Focus.

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

Covers **30 unique WCAG SCs** (21 Level A + 9 Level AA) through axe-core v4.9+ and 8 custom Puppeteer check modules.
Results are merged and returned grouped by `successCriteriaId` with `fail / pass / incomplete` status per rule.

**Level A SCs (21):** 1.1.1, 1.2.2, 1.3.1, 1.3.2 🔶, 1.4.1 🔶, 1.4.2 🔶, 2.1.1, 2.1.2 🔶, 2.2.1 🔶, 2.2.2, 2.4.1, 2.4.2, 2.4.3 🔶, 2.4.4, 2.5.3, 3.1.1, 3.2.1 🔶, 3.2.2 🔶, 3.3.2 🔶, 4.1.1 🔶, 4.1.2

**Level AA SCs (9):** 1.3.4, 1.3.5, 1.4.3, 1.4.4, 1.4.12 🔶, 2.4.5 🔶, 2.4.6, 2.4.7 🔶, 2.4.13 🔶, 3.1.2, 4.1.3 🔶

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

**Node.js future possibilities (custom Puppeteer):**

| SC | Name | Approach |
|----|------|----------|
| 1.4.5 | Images of Text | `page.evaluate` to find `<img>` inside `<button>`/`<a>` with matching text content; or Canvas pixel-sampling after rendering to detect text-like patterns. Requires OCR — full implementation is Python-side. |
| 1.4.11 | Non-text Contrast | Puppeteer screenshot + Canvas pixel-sampling around UI component boundaries; measure contrast of component edge colour vs adjacent background. Complex but feasible without OCR. |

---

*Generated: 2026-03-17 · Updated: 2026-03-24 (axe v4.9 audit + 8 custom Puppeteer checks + Python 1.4.3/1.4.5/1.4.11 image pipeline) · WCAG 2.2 (W3C Recommendation 2023-10-05)*
