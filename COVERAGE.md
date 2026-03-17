# ka11y — WCAG 2.2 Coverage Report

Combined coverage across the **Python pipeline** (`ka11y-python`) and the **Node.js axe-core engine** (`ka11y-node`).

Legend: ✅ Covered · ❌ Not covered · 🔶 Partial (automated checks only, not full SC)

---

## Summary

| Level | Total SCs | Python | Node (axe) | Combined | Combined % | Missing |
|-------|-----------|--------|------------|----------|------------|---------|
| A     | 31        | 6      | 20         | 22       | **71 %**   | 9       |
| AA    | 26        | 1      | 20         | 21       | **81 %**   | 5       |
| AAA   | 30        | 0      | 0          | 0        | **0 %**    | 30      |
| **Total** | **87** | **7** | **40**   | **43**   | **49 %**   | **44** |

> Numbers reflect *automatable checks only*. Many criteria (colour contrast,
> reading level, meaningful sequence) require human review and cannot be
> 100 % automated.

---

## Level A — 31 Success Criteria

| SC | Name | Python | Node (axe) | Combined | Notes |
|----|------|--------|------------|----------|-------|
| 1.1.1 | Non-text Content | ✅ AltTextAuditor | ✅ axe `image-alt`, `input-image-alt` | ✅ | Both; Python adds OCR contrast |
| 1.2.1 | Audio-only and Video-only (Prerecorded) | ❌ | ❌ | ❌ | Requires content inspection |
| 1.2.2 | Captions (Prerecorded) | ❌ | ❌ | ❌ | Requires VTT/transcript analysis |
| 1.2.3 | Audio Description or Media Alternative (Prerecorded) | ❌ | ❌ | ❌ | Requires media analysis |
| 1.3.1 | Info and Relationships | ❌ | ✅ axe `landmark-*`, `list`, `table-*` | ✅ | |
| 1.3.2 | Meaningful Sequence | ❌ | 🔶 axe `tabindex` | 🔶 | Only tabindex heuristic |
| 1.3.3 | Sensory Characteristics | ❌ | ❌ | ❌ | Requires NLP content analysis |
| 1.4.1 | Use of Color | ❌ | 🔶 axe `color-contrast` (partial) | 🔶 | Not fully automatable |
| 1.4.2 | Audio Control | ❌ | 🔶 axe `audio-caption` | 🔶 | Partial |
| 2.1.1 | Keyboard | ❌ | ✅ axe `keyboard-scrollable-region`, `tabindex` | ✅ | |
| 2.1.2 | No Keyboard Trap | ❌ | ✅ axe `scrollable-region-focusable` | ✅ | |
| 2.1.4 | Character Key Shortcuts | ❌ | ❌ | ❌ | Requires JS behaviour analysis |
| 2.2.1 | Timing Adjustable | ❌ | ❌ | ❌ | Requires runtime behaviour |
| 2.2.2 | Pause, Stop, Hide | ✅ PauseStopHideAuditor | 🔶 axe `blink`, `marquee` only | ✅ | Python goes beyond axe (CSS anims, carousels, autoplay video, GIFs) |
| 2.3.1 | Three Flashes or Below Threshold | ❌ | ❌ | ❌ | Requires video frame analysis |
| 2.4.1 | Bypass Blocks | ❌ | ✅ axe `skip-link` | ✅ | |
| 2.4.2 | Page Titled | ❌ | ✅ axe `document-title` | ✅ | |
| 2.4.3 | Focus Order | ❌ | 🔶 axe `tabindex` | 🔶 | Full order requires manual check |
| 2.4.4 | Link Purpose (In Context) | ❌ | ✅ axe `link-name`, `duplicate-id-active` | ✅ | |
| 2.5.1 | Pointer Gestures | ❌ | ❌ | ❌ | Requires JS gesture inspection |
| 2.5.2 | Pointer Cancellation | ❌ | ❌ | ❌ | Requires event handler analysis |
| 2.5.3 | Label in Name | ✅ LabelInNameAuditor | ✅ axe `label-content-name-mismatch` | ✅ | Both |
| 2.5.4 | Motion Actuation | ❌ | ❌ | ❌ | Requires device-motion API analysis |
| 3.1.1 | Language of Page | ❌ | ✅ axe `html-has-lang`, `html-lang-valid` | ✅ | |
| 3.2.1 | On Focus | ❌ | ❌ | ❌ | Requires focus-event inspection |
| 3.2.2 | On Input | ❌ | ❌ | ❌ | Requires input-event inspection |
| 3.3.1 | Error Identification | ✅ FormAuditor | ✅ axe `aria-required-attr` | ✅ | Both |
| 3.3.2 | Labels or Instructions | ✅ FormAuditor | ✅ axe `label`, `input-button-name` | ✅ | Both |
| 3.3.7 | Redundant Entry *(WCAG 2.2 new)* | ❌ | ❌ | ❌ | Requires multi-step form tracking |
| 4.1.1 | Parsing | ❌ | ✅ axe `duplicate-id` | ✅ | |
| 4.1.2 | Name, Role, Value | ❌ | ✅ axe `aria-*`, `button-name`, `form-field-multiple-labels` | ✅ | |

**Level A covered: 22 / 31 (71 %) · Missing: 9**

### Missing Level A
1. **1.2.1** — Audio-only and Video-only (Prerecorded)
2. **1.2.2** — Captions (Prerecorded)
3. **1.2.3** — Audio Description or Media Alternative (Prerecorded)
4. **1.3.3** — Sensory Characteristics
5. **2.1.4** — Character Key Shortcuts
6. **2.2.1** — Timing Adjustable
7. **2.3.1** — Three Flashes or Below Threshold
8. **2.5.1** — Pointer Gestures
9. **2.5.2** — Pointer Cancellation
10. **3.2.1** — On Focus
11. **3.2.2** — On Input
12. **3.3.7** — Redundant Entry *(WCAG 2.2 new)*

---

## Level AA — 26 Additional Success Criteria

| SC | Name | Python | Node (axe) | Combined | Notes |
|----|------|--------|------------|----------|-------|
| 1.2.4 | Captions (Live) | ❌ | ❌ | ❌ | Live stream; not automatable |
| 1.2.5 | Audio Description (Prerecorded) | ❌ | ❌ | ❌ | Requires media analysis |
| 1.3.4 | Orientation | ❌ | ✅ axe `css-orientation-lock` | ✅ | |
| 1.3.5 | Identify Input Purpose | ❌ | ✅ axe `autocomplete-valid` | ✅ | |
| 1.4.3 | Contrast (Minimum) | ❌ | ✅ axe `color-contrast` | ✅ | |
| 1.4.4 | Resize Text | ❌ | ✅ axe `meta-viewport` | ✅ | |
| 1.4.5 | Images of Text | ❌ | ❌ | ❌ | Requires image-content classification |
| 1.4.10 | Reflow | ❌ | ✅ axe `meta-viewport` | ✅ | |
| 1.4.11 | Non-text Contrast | ❌ | ✅ axe `non-text-contrast` | ✅ | |
| 1.4.12 | Text Spacing | ❌ | ✅ axe `p-as-heading` (partial) | 🔶 | |
| 1.4.13 | Content on Hover or Focus | ❌ | ❌ | ❌ | Requires hover/focus simulation |
| 2.4.5 | Multiple Ways | ❌ | ❌ | ❌ | Requires site-structure analysis |
| 2.4.6 | Headings and Labels | ❌ | ✅ axe `heading-order`, `empty-heading` | ✅ | |
| 2.4.7 | Focus Visible | ❌ | ✅ axe `focus-order-semantics` | 🔶 | CSS check partial |
| 2.4.11 | Focus Not Obscured (Minimum) *(WCAG 2.2 new)* | ❌ | ❌ | ❌ | Requires viewport/z-index analysis |
| 2.4.13 | Focus Appearance *(WCAG 2.2 new)* | ❌ | ❌ | ❌ | Requires CSS focus-ring measurement |
| 2.5.7 | Dragging Movements *(WCAG 2.2 new)* | ❌ | ❌ | ❌ | Requires gesture/API inspection |
| 2.5.8 | Target Size (Minimum) *(WCAG 2.2 new)* | ✅ TargetSizeAuditor | ❌ | ✅ | Measures rendered bounding-box; inline + UA-controlled exceptions detected |
| 3.1.2 | Language of Parts | ❌ | ✅ axe `valid-lang` | ✅ | |
| 3.2.3 | Consistent Navigation | ❌ | ❌ | ❌ | Requires multi-page analysis |
| 3.2.4 | Consistent Identification | ❌ | ❌ | ❌ | Requires multi-page analysis |
| 3.2.6 | Consistent Help *(WCAG 2.2 new)* | ❌ | ❌ | ❌ | Requires multi-page layout analysis |
| 3.3.3 | Error Suggestion | ❌ | ✅ axe `aria-errormessage` (partial) | 🔶 | |
| 3.3.4 | Error Prevention (Legal, Financial, Data) | ❌ | ❌ | ❌ | Requires form-flow analysis |
| 3.3.8 | Accessible Authentication (Minimum) *(WCAG 2.2 new)* | ❌ | ❌ | ❌ | Requires auth-flow analysis |
| 4.1.3 | Status Messages | ❌ | ✅ axe `aria-live-region` | ✅ | |

**Level AA covered: 15 / 26 (58 %) · Missing: 11**

### Missing Level AA
1. **1.2.4** — Captions (Live)
2. **1.2.5** — Audio Description (Prerecorded)
3. **1.4.5** — Images of Text
4. **1.4.13** — Content on Hover or Focus
5. **2.4.5** — Multiple Ways
6. **2.4.11** — Focus Not Obscured (Minimum) *(WCAG 2.2 new)*
7. **2.4.13** — Focus Appearance *(WCAG 2.2 new)*
8. **2.5.7** — Dragging Movements *(WCAG 2.2 new)*
9. **3.2.3** — Consistent Navigation
10. **3.2.4** — Consistent Identification
11. **3.2.6** — Consistent Help *(WCAG 2.2 new)*
12. **3.3.4** — Error Prevention (Legal, Financial, Data)
13. **3.3.8** — Accessible Authentication (Minimum) *(WCAG 2.2 new)*

---

## Level AAA — 30 Additional Success Criteria

> **None are currently covered.** AAA criteria generally require deep content
> analysis, multi-page behavioural testing, or human judgement and are beyond
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
| 2.4.12 | Focus Not Obscured (Enhanced) *(WCAG 2.2 new)* | ❌ | |
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

**Level AAA covered: 0 / 30 (0 %)**

---

## Planned Improvements

The following uncovered criteria are **partially automatable** and are candidates
for future Python auditors:

| Priority | SC | Name | Approach |
|----------|----|------|----------|
| High | **2.5.8** | Target Size (Minimum) | Measure CSS `width`/`height` + padding of interactive elements via Playwright; flag anything < 24×24 CSS px |
| High | **2.4.11** | Focus Not Obscured (Minimum) | Check sticky/fixed headers/footers via `z-index` + `position: fixed/sticky`; warn if they may cover focused elements |
| Medium | **1.4.13** | Content on Hover or Focus | Detect CSS `:hover`/`:focus` rules that show new content; verify dismissible via Playwright hover simulation |
| Medium | **3.2.6** | Consistent Help | Check each page for `<a>` or `<button>` containing "help", "contact", "support" in the same position across pages |
| Medium | **2.5.7** | Dragging Movements | Detect drag-and-drop widgets; verify single-pointer alternative exists |
| Low | **3.3.7** | Redundant Entry | Track form field names across multi-step flows; flag re-asked required fields |
| Low | **3.3.8** | Accessible Authentication | Detect login forms; flag if CAPTCHA present with no alternative |

---

## Tool Coverage Breakdown

### Python (`ka11y-python`) — Unique Capabilities

| Auditor | WCAG SC | What it detects beyond axe |
|---------|---------|---------------------------|
| `AltTextAccessibilityAuditor` | 1.1.1 | OCR text-in-image detection, generic alt text ("image", "photo"), cosine-similarity alt adequacy |
| `FormAccessibilityAuditor` | 3.3.1, 3.3.2 | `required` without error messaging, placeholder-only labels, hidden-label patterns |
| `LabelInNameAuditor` | 2.5.3 | Checks visible label text is substring of accessible name using NLP |
| `PauseStopHideAuditor` | 2.2.2 | CSS keyframe animations (> 5 s / infinite), autoplay video, animated GIFs, carousels (Bootstrap/Swiper/Slick/Owl/Glide/Splide) — all missed by axe |
| `TargetSizeAuditor` | 2.5.8 | Measures rendered bounding-box (getBoundingClientRect) of all interactive elements; detects inline-link and UA-controlled exceptions automatically |

### Node.js (`ka11y-node`) — axe-core Engine

Covers ~40 WCAG A/AA success criteria through Puppeteer + axe-core browser injection.
Returns results grouped by `successCriteriaId` with `fail / pass / incomplete` status per rule.

---

*Generated: 2026-03-17 · WCAG 2.2 (W3C Recommendation 2023-10-05)*
