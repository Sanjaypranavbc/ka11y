# ka11y — WCAG 2.2 Coverage Report

Combined coverage across the **Python pipeline** (`ka11y-python`) and the **Node.js axe-core engine** (`ka11y-node`).

Legend: ✅ Covered · ❌ Not covered · 🔶 Partial (automated checks only, not full SC)

Confidence: 🟢 High (reliable, low FP/FN) · 🟡 Medium (heuristic, some FP/FN expected) · 🔴 Low (limited detection, flags for manual review) · — (not covered)

---

## Summary

| Level | Total SCs | Python | Node (axe+custom) | Combined | Combined % | Missing |
|-------|-----------|--------|-------------------|----------|------------|---------|
| A     | 31        | 6      | 24                | 25       | **81 %**   | 6       |
| AA    | 26        | 10     | 16                | 22       | **85 %**   | 4       |
| AAA   | 30        | 1      | 2                 | 3        | **10 %**   | 27      |
| **Total** | **87** | **17** | **42**        | **50**   | **57 %**   | **37** |

> Numbers reflect *automatable checks only*. Many criteria (colour contrast,
> reading level, meaningful sequence) require human review and cannot be
> 100 % automated.

---

## Level A — 31 Success Criteria

| SC | Name | Python | Node (axe) | Combined | Confidence | Notes |
|----|------|--------|------------|----------|------------|-------|
| 1.1.1 | Non-text Content | ✅ AltTextAuditor | ✅ axe `image-alt`, `input-image-alt` | ✅ | 🟢 High | Both; Python adds OCR cosine-similarity alt-adequacy check |
| 1.2.1 | Audio-only and Video-only (Prerecorded) | ❌ | 🔶 Node `custom-audio-transcript` | 🔶 | 🟡 Medium | Checks `<audio>` elements for adjacent `<track>`, nearby transcript links, `figcaption`, `aria-describedby`; returns `incomplete` (not `fail`) since transcript quality is unverifiable |
| 1.2.2 | Captions (Prerecorded) | ❌ | ✅ axe `video-caption` | ✅ | 🟢 High | axe reliably checks `<video>` for missing `<track kind="captions">` |
| 1.2.3 | Audio Description or Media Alternative (Prerecorded) | ❌ | ❌ | ❌ | — | Requires media analysis |
| 1.3.1 | Info and Relationships | ❌ | ✅ axe `landmark-*`, `list`, `table-*` | ✅ | 🟢 High | axe landmark/table rules are well-established |
| 1.3.2 | Meaningful Sequence | ❌ | 🔶 Node `custom-meaningful-sequence` | 🔶 | 🟡 Medium | Fixed: now detects `flex-direction: row/column-reverse` AND CSS `order` that actually reorders from DOM sequence |
| 1.3.3 | Sensory Characteristics | ❌ | ❌ | ❌ | — | Requires NLP content analysis |
| 1.4.1 | Use of Color | ❌ | 🔶 axe `link-in-text-block` + Node `custom-use-of-color` | 🔶 | 🟡 Medium | Custom check detects inline links with no non-color cue (underline/border/font-weight/bg); covers axe's gap for text-block links |
| 1.4.2 | Audio Control | ❌ | 🔶 axe `no-autoplay-audio` | 🔶 | 🟡 Medium | Detects auto-playing audio lacking controls; `audio-caption` rule deprecated in axe v4 |
| 2.1.1 | Keyboard | ❌ | ✅ axe `scrollable-region-focusable`, `frame-focusable-content`, `server-side-image-map` | ✅ | 🟢 High | axe rules are reliable and comprehensive |
| 2.1.2 | No Keyboard Trap | ❌ | 🔶 Node `custom-keyboard-trap` | 🔶 | 🟡 Medium | Fixed: consecutive-repeat key tracking + 60ms settle delay after Tab press for accurate focus detection |
| 2.1.4 | Character Key Shortcuts | ❌ | 🔶 Node `custom-character-key-shortcuts` | 🔶 | 🟡 Medium | Fixed: modifier guard now uses proximity check (key + modifier within 120 chars) to reduce false-negatives from unrelated branches; still only catches inline handlers |
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

**Level A covered: 25 / 31 (81 %) · includes 13 partial (🔶) · Missing: 6**

### Missing Level A
1. **1.2.3** — Audio Description or Media Alternative (Prerecorded)
2. **1.3.3** — Sensory Characteristics
3. **2.3.1** — Three Flashes or Below Threshold
4. **2.5.1** — Pointer Gestures
5. **2.5.4** — Motion Actuation
6. **3.3.7** — Redundant Entry *(requires multi-step form tracking)*

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
| 2.4.5 | Multiple Ways | ❌ | 🔶 Node `custom-multiple-ways` | 🔶 | 🟡 Medium | Extended: now also detects breadcrumb navigation and table of contents; passes if ≥ 2 of: search/sitemap/nav/breadcrumb/toc |
| 2.4.6 | Headings and Labels | ❌ | ✅ axe `heading-order`, `empty-heading` | ✅ | 🟢 High | axe heading-order is reliable |
| 2.4.7 | Focus Visible | ❌ | 🔶 Node `custom-focus-visible` + axe `focus-visible` | 🔶 | 🟡 Medium | Fixed: per-element evaluate calls with 80ms settle delay after focus — CSS transitions now captured correctly; checks 40 elements |
| 2.4.11 | Focus Not Obscured (Minimum) *(WCAG 2.2 new)* | ✅ FocusNotObscuredMinimumEvaluator (rendered) | ❌ | ✅ | 🟢 High | getBoundingClientRect obscuration ratio measurement; full obscuration = FAIL |
| 2.4.13 | Focus Appearance *(WCAG 2.2 new)* | ❌ | 🔶 axe `focus-appearance` + Node `custom-focus-appearance` | 🔶 | 🟡 Medium | Custom Puppeteer check: measures outline-width (≥2px area req proxy) and contrast ratio (≥3:1) with per-element settle delay |
| 2.5.7 | Dragging Movements *(WCAG 2.2 new)* | ❌ | 🔶 Node `custom-dragging-movements` | 🔶 | 🟡 Medium | Fixed: detects native drag + D&D libraries; checks alternatives in element AND parent; misses `addEventListener`-based drag |
| 2.5.8 | Target Size (Minimum) *(WCAG 2.2 new)* | ✅ TargetSizeAuditor | ❌ | ✅ | 🟢 High | Bounding-box measurement; inline + UA-controlled exceptions detected |
| 3.1.2 | Language of Parts | ❌ | ✅ axe `valid-lang` | ✅ | 🟢 High | axe valid-lang is reliable |
| 3.2.3 | Consistent Navigation | ❌ | ❌ | ❌ | — | Requires multi-page analysis |
| 3.2.4 | Consistent Identification | ❌ | ❌ | ❌ | — | Requires multi-page analysis |
| 3.2.6 | Consistent Help *(WCAG 2.2 new)* | ❌ | 🔶 Node `custom-consistent-help` | 🔶 | 🟡 Medium | Extended: detects help/support links, chat widgets, `tel:` phone links, `mailto:` email links; reports position; single-page only |
| 3.3.3 | Error Suggestion | ❌ | 🔶 Node `custom-error-suggestion` | 🔶 | 🟡 Medium | Fixed: class-based selectors scoped to `form` descendants (N11) to prevent FP on documentation pages; heuristic text analysis; requires errors to be visible on page load |
| 3.3.4 | Error Prevention (Legal, Financial, Data) | ❌ | 🔶 Node `custom-error-prevention` | 🔶 | 🟡 Medium | Fixed: expanded financial/legal/destructive patterns + multi-step wizard detection; keyword-based, no semantic understanding |
| 3.3.8 | Accessible Authentication (Minimum) *(WCAG 2.2 new)* | ❌ | 🔶 Node `custom-accessible-auth` | 🔶 | 🟡 Medium | Fixed: expanded CAPTCHA alt detection, paste-blocking, cognitive tests; misses `addEventListener`-based paste blocking |
| 4.1.3 | Status Messages | ❌ | 🔶 Node `custom-status-messages` | 🔶 | 🟡 Medium | Fixed: detects forms + search results + cart/counter + notification areas; live region presence verified |

**Level AA covered: 22 / 26 (85 %) · includes 11 partial (🔶) · Missing: 4**

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
| 2.4.8 | Location | 🔶 Node `custom-location` | Detects breadcrumb navigation, `aria-current="page"` in nav, active nav item (`.active`), or sitemap link; returns `incomplete` when no indicator found |
| 2.4.9 | Link Purpose (Link Only) | 🔶 Node `custom-link-purpose` | Checks accessible name (aria-label > aria-labelledby > img alt > text) against generic phrases ("click here", "read more", "here", "more", "learn more", etc.); returns `fail` for generic text |
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

**Level AAA covered: 3 / 30 (10 %) · 2.4.12 covered by Python rendered evaluator; 2.4.8 + 2.4.9 (🔶 partial) covered by Node custom checks**

---

## Planned Improvements

The following uncovered criteria are **partially automatable** and are candidates
for future Python auditors:

| Priority | SC | Name | Approach |
|----------|----|------|----------|
| Low | **3.3.7** | Redundant Entry | Track form field names across multi-step flows; flag re-asked required fields |
| Low | **3.2.3** | Consistent Navigation | Multi-page crawl: compare nav element order across pages |
| Low | **3.2.4** | Consistent Identification | Multi-page crawl: compare component labels/names across pages |

> **Previously planned, now implemented:** 2.5.8 Target Size (Minimum), 2.4.11 Focus Not Obscured (Minimum), 1.4.13 Content on Hover or Focus, 3.2.6 Consistent Help (Node), 2.5.7 Dragging Movements (Node), 3.3.8 Accessible Authentication (Node), 3.3.3 Error Suggestion (Node), 3.3.4 Error Prevention (Node), 2.1.4 Character Key Shortcuts (Node), 2.5.2 Pointer Cancellation (Node), 1.4.1 Use of Color custom check (Node), 2.4.13 Focus Appearance custom check (Node).

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
| `TextSpacingAuditor` (crawler) | 1.4.12 | Static heuristic: flags fixed-height containers with `overflow:hidden` as WARNING/INFO (never FAILED); definitive test is the `TextSpacingEvaluator` below |
| `ReflowEvaluator` (rendered) | 1.4.10 | Playwright viewport resize to 320 px; detects actual horizontal scroll and oversized elements |
| `ResizeTextEvaluator` (rendered) | 1.4.4 | Playwright 200% text-size override; flags overflow, scroll and clipped text |
| `TextSpacingEvaluator` (rendered) | 1.4.12 | Playwright CSS override (1.5× line-height, 0.12em letter-spacing, etc.); flags newly-clipped elements |
| `OrientationEvaluator` (rendered) | 1.3.4 | Both portrait + landscape snapshots; detects "please rotate" overlays and missing content in either orientation |
| `HoverFocusContentEvaluator` (rendered) | 1.4.13 | Playwright hover simulation; checks popup appeared, dismissible-by-Escape, pointer-can-move-over |
| `FocusNotObscuredMinimumEvaluator` (rendered) | 2.4.11 | Tab-key focus walk; measures obscuration ratio via getBoundingClientRect; full obscuration = FAIL, partial = NEEDS_REVIEW |
| `FocusNotObscuredEnhancedEvaluator` (rendered) | 2.4.12 (AAA) | Same as above but stricter: any non-trivial overlap (≥ 10%) = FAIL |

### Node.js (`ka11y-node`) — axe-core + Custom Puppeteer Checks

Covers **42 unique WCAG SCs** (24 Level A + 16 Level AA + 2 Level AAA) through axe-core v4.9+ and 20 custom Puppeteer check modules.
Results are merged in both response shapes:
- grouped APIs (`/api/v1/analyze-accessibility`, `/api/v1/analyse-url`) return `fail / pass / incomplete` per rule
- flat API (`/api/v1/analyse-url-flat`) now includes custom-check findings with `fail / pass / needs_review` status (custom `incomplete` is normalised to `needs_review`) and applies WCAG level filtering (`A/AA/AAA`).

**Level A SCs (24):** 1.1.1, 1.2.1 🔶, 1.2.2, 1.3.1, 1.3.2 🔶, 1.4.1 🔶, 1.4.2 🔶, 2.1.1, 2.1.2 🔶, 2.1.4 🔶, 2.2.1 🔶, 2.2.2, 2.4.1, 2.4.2, 2.4.3 🔶, 2.4.4, 2.5.2 🔶, 2.5.3, 3.1.1, 3.2.1 🔶, 3.2.2 🔶, 3.3.2 🔶, 4.1.1 🔶, 4.1.2

**Level AA SCs (16):** 1.3.4, 1.3.5, 1.4.3, 1.4.4, 1.4.12 🔶, 2.4.5 🔶, 2.4.6, 2.4.7 🔶, 2.4.13 🔶, 2.5.7 🔶, 3.1.2, 3.2.6 🔶, 3.3.3 🔶, 3.3.4 🔶, 3.3.8 🔶, 4.1.3 🔶

**Level AAA SCs (2):** 2.4.8 🔶, 2.4.9 🔶

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
| `use-of-color.check.js` | 1.4.1 | Detect inline links (in `<p>`, `<li>`, `<td>`, etc.) that rely solely on color difference (no underline/border/bg/font-weight change) |
| `focus-appearance.check.js` | 2.4.13 | Measure outline-width (≥2px area requirement) and contrast ratio (≥3:1) between focused and unfocused states with settle delay |
| `audio-transcript.check.js` | 1.2.1 | Check `<audio>` elements for `<track>`, adjacent transcript links, `figcaption`, or `aria-describedby`; returns `incomplete` (not `fail`) when no text alternative detected |
| `location.check.js` | 2.4.8 (AAA) | Detect breadcrumb nav, `aria-current="page"` in nav, active nav item (`.active`), or sitemap link; returns `incomplete` when none found |
| `link-purpose.check.js` | 2.4.9 (AAA) | Check link accessible name (aria-label > aria-labelledby > img alt > text) against generic phrases ("click here", "read more", "here", etc.); returns `fail` for non-descriptive links |

**Current backdrops (Node custom checks):**

1. Most custom checks are rule-level heuristics, so flat findings currently return `element: null` (no stable CSS target/HTML snippet).
2. Interactive checks (`on-focus`, `on-input`, `keyboard-trap`, `focus-visible`) can alter page state and may stop early after navigation for safety.
3. Runtime check failures must be surfaced as `incomplete/needs_review` findings (never silently dropped), otherwise SC-level coverage appears inconsistent.

### Engineering Analysis (2026-03-24)

**High-priority bugs / risks**

1. **Result reflection risk (Node custom checks):** running static + interactive checks on a shared page in parallel can produce state interference (navigation/focus side effects) and missing findings.
2. **SSRF hardening gap (Python combined route):** hostname-prefix checks alone are insufficient; DNS-resolved private/link-local IPs must be blocked.
3. **Output collision risk (Python combined jobs):** output directory naming by `domain + minute` can collide for concurrent jobs.

**Performance hotspots**

1. **Image crawler session churn:** creating a fresh `aiohttp.ClientSession` per image download adds connection setup overhead.
2. **Crawler duplication across stages:** form/interactive/target/text-spacing crawlers independently revisit the same pages.
3. **Heavy parallelism pressure:** multiple Playwright-based stages launched together can saturate CPU/RAM on moderate hosts.

**Fixes applied in this pass**

1. **Python image crawler I/O optimization:** reused a single `aiohttp.ClientSession` per crawl run instead of creating one per download.
2. **Python combined output isolation:** output path now includes `job_id` suffix to prevent report/artifact collisions.

**Automation roadmap**

1. Add nightly CI smoke audits against 3 stable fixture sites and diff pass/fail deltas by WCAG SC.
2. Persist per-stage timings (`crawl`, `audit`, `serialize`) and alert when p95 latency regresses >20%.
3. Introduce a cached crawl artifact layer (DOM snapshots + extracted elements) reused by multiple auditors in one job.
4. Emit machine-readable QA gates (`critical_failures`, `needs_review_count`, `coverage_by_sc`) for release pipelines.

**Node.js future possibilities (custom Puppeteer):**

| SC | Name | Approach |
|----|------|----------|
| 1.4.5 | Images of Text | `page.evaluate` to find `<img>` inside `<button>`/`<a>` with matching text content; or Canvas pixel-sampling after rendering to detect text-like patterns. Requires OCR — full implementation is Python-side. |
| 1.4.11 | Non-text Contrast | Puppeteer screenshot + Canvas pixel-sampling around UI component boundaries; measure contrast of component edge colour vs adjacent background. Complex but feasible without OCR. |

---

*Generated: 2026-03-17 · Updated: 2026-03-25 (+3 new Node checks: custom-audio-transcript 1.2.1, custom-location 2.4.8 AAA, custom-link-purpose 2.4.9 AAA; bug fixes N7–N13: on-focus/on-input selector leading comma, focus-visible transparent outline FP, accessible-auth dual-signal CAPTCHA detection, error-suggestion form-scoped selectors → confidence 🔴→🟡, server CORS wildcard removal; focus-visible test rewrite with jest.runAllTimersAsync(); +2 new Node checks: 1.4.1 custom-use-of-color, 2.4.13 custom-focus-appearance; count updates: Level A 25/31 81%, AAA 3/30 10%, Node 42 SCs 24A+16AA+2AAA, 20 custom modules) · WCAG 2.2 (W3C Recommendation 2023-10-05)*
