# ka11y — WCAG 2.2 Coverage Report

Combined coverage across the **Python pipeline** (`ka11y-python`) and the **Node.js axe-core engine** (`ka11y-node`).

Legend: ✅ Covered · ❌ Not covered · 🔶 Partial (automated checks only, not full SC)

---

## Summary

| Level | Total SCs | Python | Node (axe) | Combined | Combined % | Missing |
|-------|-----------|--------|------------|----------|------------|---------|
| A     | 31        | 6      | 16         | 17       | **55 %**   | 14      |
| AA    | 26        | 7      | 7          | 11       | **42 %**   | 15      |
| AAA   | 30        | 1      | 0          | 1        | **3 %**    | 29      |
| **Total** | **87** | **14** | **23**  | **29**   | **33 %**   | **58** |

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
| 1.3.2 | Meaningful Sequence | ❌ | ❌ | ❌ | axe `tabindex` maps to SC 2.4.3 in rule mapper, not 1.3.2 |
| 1.3.3 | Sensory Characteristics | ❌ | ❌ | ❌ | Requires NLP content analysis |
| 1.4.1 | Use of Color | ❌ | 🔶 axe `link-in-text-block` | 🔶 | Detects links distinguished only by colour; not fully automatable |
| 1.4.2 | Audio Control | ❌ | 🔶 axe `no-autoplay-audio` | 🔶 | Detects auto-playing audio lacking controls; `audio-caption` rule is deprecated in axe v4 |
| 2.1.1 | Keyboard | ❌ | ✅ axe `scrollable-region-focusable`, `frame-focusable-content`, `server-side-image-map` | ✅ | |
| 2.1.2 | No Keyboard Trap | ❌ | ❌ | ❌ | `scrollable-region-focusable` maps to SC 2.1.1 in rule mapper, not 2.1.2 |
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
| 3.2.1 | On Focus | ❌ | ❌ | ❌ | Requires focus-event inspection |
| 3.2.2 | On Input | ❌ | ❌ | ❌ | Requires input-event inspection |
| 3.3.1 | Error Identification | ✅ FormAuditor | ❌ | ✅ | Python only; axe `aria-required-attr` maps to SC 4.1.2 (wcag412 tag), not 3.3.1 |
| 3.3.2 | Labels or Instructions | ✅ FormAuditor | 🔶 axe `form-field-multiple-labels` | ✅ | Python covers fully; axe detects multiple-label ambiguity only; `label` maps to 4.1.2 |
| 3.3.7 | Redundant Entry *(WCAG 2.2 new)* | ❌ | ❌ | ❌ | Requires multi-step form tracking |
| 4.1.1 | Parsing | ❌ | ❌ | ❌ | axe `duplicate-id` is deprecated in v4 (wcag2a-obsolete tag); `duplicate-id-aria` maps to 4.1.2 |
| 4.1.2 | Name, Role, Value | ✅ AltTextAuditor (`_check_4_1_2`) | ✅ axe `aria-*`, `button-name`, `form-field-multiple-labels` | ✅ | Both; Python checks functional images (logos, icons, buttons) |

**Level A covered: 17 / 31 (55 %) · includes 4 partial (🔶) · Missing: 14**

### Missing Level A
1. **1.2.1** — Audio-only and Video-only (Prerecorded)
2. **1.2.3** — Audio Description or Media Alternative (Prerecorded)
3. **1.3.2** — Meaningful Sequence
4. **1.3.3** — Sensory Characteristics
5. **2.1.2** — No Keyboard Trap
6. **2.1.4** — Character Key Shortcuts
7. **2.3.1** — Three Flashes or Below Threshold
8. **2.5.1** — Pointer Gestures
9. **2.5.2** — Pointer Cancellation
10. **2.5.4** — Motion Actuation
11. **3.2.1** — On Focus
12. **3.2.2** — On Input
13. **3.3.7** — Redundant Entry *(WCAG 2.2 new)*
14. **4.1.1** — Parsing

---

## Level AA — 26 Additional Success Criteria

| SC | Name | Python | Node (axe) | Combined | Notes |
|----|------|--------|------------|----------|-------|
| 1.2.4 | Captions (Live) | ❌ | ❌ | ❌ | Live stream; not automatable |
| 1.2.5 | Audio Description (Prerecorded) | ❌ | ❌ | ❌ | Requires media analysis |
| 1.3.4 | Orientation | ✅ OrientationEvaluator (rendered) | ✅ axe `css-orientation-lock` | ✅ | Both |
| 1.3.5 | Identify Input Purpose | ❌ | ✅ axe `autocomplete-valid` | ✅ | |
| 1.4.3 | Contrast (Minimum) | ❌ | ✅ axe `color-contrast` | ✅ | |
| 1.4.4 | Resize Text | ✅ ResizeTextEvaluator (rendered) | ✅ axe `meta-viewport` | ✅ | Both; Python detects overflow/clip after 200% zoom |
| 1.4.5 | Images of Text | ❌ | ❌ | ❌ | Requires image-content classification |
| 1.4.10 | Reflow | ✅ ReflowEvaluator (rendered) | ❌ | ✅ | Python only; axe `meta-viewport` maps to SC 1.4.4 not 1.4.10 |
| 1.4.11 | Non-text Contrast | ❌ | ❌ | ❌ | `non-text-contrast` rule absent from axe v4.11.1; requires manual check |
| 1.4.12 | Text Spacing | ✅ TextSpacingAuditor (crawler) + TextSpacingEvaluator (rendered) | 🔶 axe `avoid-inline-spacing` | ✅ | Python: static fixed-height/overflow detection + Playwright override test |
| 1.4.13 | Content on Hover or Focus | ✅ HoverFocusContentEvaluator (rendered) | ❌ | ✅ | Python: Playwright hover simulation — checks dismissible, persistent, hoverable |
| 2.4.5 | Multiple Ways | ❌ | ❌ | ❌ | Requires site-structure analysis |
| 2.4.6 | Headings and Labels | ❌ | ✅ axe `heading-order`, `empty-heading` | ✅ | |
| 2.4.7 | Focus Visible | ❌ | ❌ | ❌ | `focus-order-semantics` maps to SC 2.4.3; no axe rule with wcag247 tag in v4.11.1 |
| 2.4.11 | Focus Not Obscured (Minimum) *(WCAG 2.2 new)* | ✅ FocusNotObscuredMinimumEvaluator (rendered) | ❌ | ✅ | Python: measures obscuration ratio via getBoundingClientRect; full obscuration = FAIL |
| 2.4.13 | Focus Appearance *(WCAG 2.2 new)* | ❌ | ❌ | ❌ | Requires CSS focus-ring measurement |
| 2.5.7 | Dragging Movements *(WCAG 2.2 new)* | ❌ | ❌ | ❌ | Requires gesture/API inspection |
| 2.5.8 | Target Size (Minimum) *(WCAG 2.2 new)* | ✅ TargetSizeAuditor | ❌ | ✅ | Measures rendered bounding-box; inline + UA-controlled exceptions detected |
| 3.1.2 | Language of Parts | ❌ | ✅ axe `valid-lang` | ✅ | |
| 3.2.3 | Consistent Navigation | ❌ | ❌ | ❌ | Requires multi-page analysis |
| 3.2.4 | Consistent Identification | ❌ | ❌ | ❌ | Requires multi-page analysis |
| 3.2.6 | Consistent Help *(WCAG 2.2 new)* | ❌ | ❌ | ❌ | Requires multi-page layout analysis |
| 3.3.3 | Error Suggestion | ❌ | ❌ | ❌ | No axe rule with wcag333 tag in v4.11.1 |
| 3.3.4 | Error Prevention (Legal, Financial, Data) | ❌ | ❌ | ❌ | Requires form-flow analysis |
| 3.3.8 | Accessible Authentication (Minimum) *(WCAG 2.2 new)* | ❌ | ❌ | ❌ | Requires auth-flow analysis |
| 4.1.3 | Status Messages | ❌ | ❌ | ❌ | No axe rule with wcag413 tag in v4.11.1 |

**Level AA covered: 11 / 26 (42 %) · Missing: 15**

### Missing Level AA
1. **1.2.4** — Captions (Live)
2. **1.2.5** — Audio Description (Prerecorded)
3. **1.4.5** — Images of Text
4. **1.4.11** — Non-text Contrast
5. **2.4.5** — Multiple Ways
6. **2.4.7** — Focus Visible
7. **2.4.13** — Focus Appearance *(WCAG 2.2 new)*
8. **2.5.7** — Dragging Movements *(WCAG 2.2 new)*
9. **3.2.3** — Consistent Navigation
10. **3.2.4** — Consistent Identification
11. **3.2.6** — Consistent Help *(WCAG 2.2 new)*
12. **3.3.3** — Error Suggestion
13. **3.3.4** — Error Prevention (Legal, Financial, Data)
14. **3.3.8** — Accessible Authentication (Minimum) *(WCAG 2.2 new)*
15. **4.1.3** — Status Messages

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
| `AltTextAccessibilityAuditor` | 1.1.1, 4.1.2 | OCR text-in-image detection, generic alt text ("image", "photo"), cosine-similarity alt adequacy; `_check_4_1_2` validates accessible name for functional images (logos, icons, buttons) |
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

### Node.js (`ka11y-node`) — axe-core Engine

Covers **23 unique WCAG SCs** (16 Level A + 7 Level AA) through Puppeteer + axe-core v4.11.1 browser injection.
Returns results grouped by `successCriteriaId` with `fail / pass / incomplete` status per rule.

**Level A SCs (16):** 1.1.1, 1.2.2, 1.3.1, 1.4.1 🔶, 1.4.2 🔶, 2.1.1, 2.2.1 🔶, 2.2.2, 2.4.1, 2.4.2, 2.4.3 🔶, 2.4.4, 2.5.3, 3.1.1, 3.3.2 🔶, 4.1.2

**Level AA SCs (7):** 1.3.4, 1.3.5, 1.4.3, 1.4.4, 1.4.12 🔶, 2.4.6, 3.1.2

**Known axe v4.11.1 gaps:** `non-text-contrast` rule absent (1.4.11 uncovered); `duplicate-id` deprecated (4.1.1 uncovered); no rules with wcag247, wcag333, wcag413 tags (2.4.7, 3.3.3, 4.1.3 uncovered). Several best-practice rules (`accesskeys`, `skip-link`, `aria-dialog-name`) have no WCAG SC tag and require additions to `RULE_SC_FALLBACK` to be counted.

---

*Generated: 2026-03-17 · Updated: 2026-03-24 (axe v4.11.1 audit) · WCAG 2.2 (W3C Recommendation 2023-10-05)*
