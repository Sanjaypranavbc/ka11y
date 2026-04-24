# ka11y WCAG 2.2 Coverage Report

**Report date:** 2026-04-24
**Scope:** Combined coverage across `ka11y-python` (FastAPI + Playwright + OCR + CV pipeline) and `ka11y-node` (axe-core 4.11.1 + 28 custom checks).
**Basis:** Source inspection plus 2026-04-23 sprint additions (1.2.2 captions, 1.2.3 audio description, 1.4.2 audio control, 1.1.1 / 1.4.5 background-image scan, 2.1.2 F85 modal-without-escape), 2026-04-24 node gap-closure pass (F30/F13/F81/F58/F60/G125/G126/G127/G164/F114 heuristics), and 2026-03-26 empirical validation against seven production sites.

---

## 1. Executive Summary

| Metric | Value |
|---|---|
| WCAG 2.2 Success Criteria emitted (combined) | **56 of 87** |
| Overall coverage | **64.4 percent** |
| Level A coverage | **28 of 31** (90.3 percent) |
| Level AA coverage | **22 of 26** (84.6 percent) |
| Level AAA coverage | **6 of 30** (20.0 percent) |
| Robust principle coverage | **3 of 3** (100 percent) |
| Custom Node checks shipped | 28 `*.check.js` files in `ka11y-node/src/custom-checks/` |
| Python rendered evaluators | 7 (resize, reflow, text-spacing, hover-focus, orientation, focus-not-obscured min and enhanced) |
| Python image and CV pipelines | OCR plus classifier-driven image pipeline across 1.1.1, 1.4.3, 1.4.5, 1.4.6, 1.4.11, 4.1.2 |
| Real-site validation (2026-03-26) | 7 sites, 38 SCs observed firing |
| Test suite status | Python 601 of 618 passing locally, Node 233 of 233 passing |

**What changed since the prior 2026-03-26 baseline:**

1. Three previously missing SCs now have direct custom-check coverage: 1.2.2 Captions (Prerecorded), 1.2.3 Audio Description, and a strengthened 1.4.2 Audio Control beyond axe-core's metadata pass-through.
2. 1.1.1 Non-text Content gained a CSS `background-image` scan that was previously a documented blind spot.
3. 2.1.2 No Keyboard Trap added F85 modal-without-escape detection on top of the existing forward and reverse Tab cycle and Escape verification.
4. 2026-04-24 gap pass extended Node heuristics for 1.2.1 F30 filename-only transcript links, 1.4.1 non-link color-only indicators (F13/F81), 2.1.2 scripted key suppression and non-modal popup dismissibility (F58/F60), 2.4.5 related-links/page-index mechanisms (G125/G126), 2.4.8 table-of-contents signal (G127), 3.3.4 undo-window safeguards (G164), and 4.1.3 toast-without-ARIA (F114).
5. Image-capture failures now propagate end-to-end as `capture_status` with a distinct `incomplete` finding status (was silently treated as N/A before).
6. 3.3.7 Redundant Entry is confirmed to be wired up via `redundant-entry.check.js` (was undercounted in the prior report).

---

## 2. Coverage Totals by Level

| Level | Total SCs | Node | Python | Overlap | Combined covered | Missing | Coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 31 | 26 | 9 | 7 | 28 | 3 | **90.3 percent** |
| AA | 26 | 18 | 12 | 8 | 22 | 4 | **84.6 percent** |
| AAA | 30 | 5 | 2 | 1 | 6 | 24 | **20.0 percent** |
| **Total** | **87** | **49** | **23** | **16** | **56** | **31** | **64.4 percent** |

## Coverage by Principle

| Principle | Total SCs | Node | Python | Combined | Coverage |
|---|---:|---:|---:|---:|---:|
| Perceivable (1.x.x) | 29 | 15 | 13 | 19 | **65.5 percent** |
| Operable (2.x.x) | 34 | 20 | 7 | 22 | **64.7 percent** |
| Understandable (3.x.x) | 21 | 11 | 2 | 12 | **57.1 percent** |
| Robust (4.x.x) | 3 | 3 | 1 | 3 | **100 percent** |

## Stack Contribution Breakdown

| Category | Count | Criteria |
|---|---:|---|
| Overlap between Node and Python | 16 | 1.1.1, 1.2.1, 1.3.1, 1.3.4, 1.4.3, 1.4.4, 1.4.5, 1.4.6, 1.4.12, 2.2.2, 2.4.7, 2.4.13, 2.5.3, 2.5.8, 3.3.2, 4.1.2 |
| Node-only coverage | 33 | 1.2.2, 1.2.3, 1.3.2, 1.3.5, 1.4.1, 1.4.2, 2.1.1, 2.1.2, 2.1.4, 2.2.1, 2.2.4, 2.4.1, 2.4.2, 2.4.3, 2.4.4, 2.4.5, 2.4.6, 2.4.8, 2.4.9, 2.5.2, 2.5.7, 3.1.1, 3.1.2, 3.1.6, 3.2.1, 3.2.2, 3.2.6, 3.3.3, 3.3.4, 3.3.7, 3.3.8, 4.1.1, 4.1.3 |
| Python-only coverage | 7 | 1.3.3, 1.4.10, 1.4.11, 1.4.13, 2.4.11, 2.4.12, 3.3.1 |

---

## 3. Confidence Mix

| Confidence | Meaning |
|---|---|
| High | Direct, repeatable detection close to the criterion intent. |
| Medium | Useful but partly heuristic, context-dependent, or pattern-based. |
| Low | Narrow proxy or covers only one slice of the criterion. |
| Not covered | No current Node or Python emitter outputs this SC. |

| Level | High | Medium | Low | Covered |
|---|---:|---:|---:|---:|
| A | 13 | 12 | 3 | 28 |
| AA | 11 | 10 | 1 | 22 |
| AAA | 2 | 2 | 2 | 6 |
| **Total** | **26** | **24** | **6** | **56** |

---

## 4. Complete Rule Inventory (Table-Wise Analysis)

The table below is the full WCAG 2.2 inventory. The "How addressed" column names the file or pipeline that emits the finding.

| SC | Criterion | Level | Node | Python | Status | Confidence | How addressed in code | Plain-English |
|---|---|---|---|---|---|---|---|---|
| 1.1.1 | Non-text Content | A | Yes | Yes | Covered | High | `alttext.py` plus CNN classifier plus OCR plus `policy_1_1_1.py`; new `background-image-content.check.js` for CSS-painted images | Images, icons, charts, and CSS background images need text alternatives. |
| 1.2.1 | Audio-only and Video-only (Prerecorded) | A | Yes | Yes | Covered | Medium | `media_auditor.py` plus `audio-transcript.check.js` (transcript-link keyword scan with HEAD reachability check + filename-only transcript heuristic) | Pre-recorded audio-only or video-only media needs an equivalent alternative. |
| 1.2.2 | Captions (Prerecorded) | A | Yes | No | Covered | High | New `captions-prerecorded.check.js`: scans `<video>` for `<track kind="captions">`; emits INCOMPLETE for cross-origin embeds (YouTube, Vimeo, Wistia) | Pre-recorded video with sound needs captions. |
| 1.2.3 | Audio Description or Media Alternative (Prerecorded) | A | Yes | No | Covered | Medium | New `audio-description.check.js`: detects `<track kind="descriptions">`, alternate description audio, or nearby full-text transcript link (EN plus JA keywords) | Pre-recorded video needs audio description or a full text alternative. |
| 1.2.4 | Captions (Live) | AA | No | No | Missing | Not covered | Roadmap: extend captions check with live-stream and HLS source detection | Live audio or video needs captions. |
| 1.2.5 | Audio Description (Prerecorded) | AA | Partial | No | Partial | Low | Partly covered by `audio-description.check.js` (1.2.3 path); no separate emitter | Recorded video needs audio description for important visuals. |
| 1.2.6 | Sign Language (Prerecorded) | AAA | No | No | Missing | Not covered | Out of scope | Recorded video should provide sign language for spoken content. |
| 1.2.7 | Extended Audio Description (Prerecorded) | AAA | No | No | Missing | Not covered | Out of scope | Recorded video should offer extended audio description when needed. |
| 1.2.8 | Media Alternative (Prerecorded) | AAA | No | No | Missing | Not covered | Out of scope | Recorded media should have a full text alternative. |
| 1.2.9 | Audio-only (Live) | AAA | No | No | Missing | Not covered | Out of scope | Live audio-only content should have a text alternative. |
| 1.3.1 | Info and Relationships | A | Yes | Yes | Covered | High | axe-core (heading-order, list, landmark, table, label-association rules) plus `policy_1_3_1.py` | Headings, labels, and tables must be coded so assistive tech understands them. |
| 1.3.2 | Meaningful Sequence | A | Yes | No | Covered | Medium | `meaningful-sequence.check.js`: scans flex / grid containers for `*-reverse`, explicit `order`, `flex-direction` reversal | Reading order must make sense when read linearly. |
| 1.3.3 | Sensory Characteristics | A | No | Yes | Covered | Medium | `sensory_auditor.py` with spaCy (en_core_web_sm and ja_core_news_sm) plus `SENSORY_WORDS` and `SENSORY_WORDS_JA` lists | Instructions must not depend only on shape, size, color, or position. |
| 1.3.4 | Orientation | AA | Yes | Yes | Covered | High | `orientation.check.js` plus Python rendered orientation evaluator | Content should work in portrait and landscape unless essential. |
| 1.3.5 | Identify Input Purpose | AA | Yes | No | Covered | High | axe-core `autocomplete-valid` rule | Common personal-data fields should expose machine-readable purpose. |
| 1.3.6 | Identify Purpose | AAA | No | No | Missing | Not covered | Roadmap: NLP-driven purpose taxonomy | More UI elements should expose programmatic purpose. |
| 1.4.1 | Use of Color | A | Yes | No | Covered | Medium | `use-of-color.check.js`: links inside `p / li / td / th / blockquote` checked for non-color cue plus heuristics for required-field color-only indicators and color-only instructional copy | Color alone must not carry the message. |
| 1.4.2 | Audio Control | A | Yes | No | Covered | Medium | New `audio-control.check.js`: flags unmuted autoplay over 3 s without `controls` or external pause control in the same figure or region | Auto-playing sound must be stoppable or controllable. |
| 1.4.3 | Contrast (Minimum) | AA | Yes | Yes | Covered | High | `contrast_analyser.py` plus `text_detector.py` (EAST or CRAFT) plus per-bbox Otsu segmentation; axe-core color-contrast rule | Text contrast must reach the minimum readability ratio. |
| 1.4.4 | Resize Text | AA | Yes | Yes | Covered | High | Python rendered `resize_text.py` evaluator (font-size 200 percent diff) plus axe fallback | Text should stay usable when enlarged to 200 percent. |
| 1.4.5 | Images of Text | AA | Yes | Yes | Covered | Medium | `images-of-text.check.js` (src-keyword and alt-length heuristic) plus Python OCR pipeline plus new `background-image-content.check.js` text-hint branch | Use real text instead of text baked into images where possible. |
| 1.4.6 | Contrast (Enhanced) | AAA | Yes | Yes | Covered | High | `policy_1_4_6.py` (7:1 and 4.5:1 large-text thresholds) on the same OCR contrast pipeline as 1.4.3 | Text needs higher than AA contrast. |
| 1.4.7 | Low or No Background Audio | AAA | No | No | Missing | Not covered | Roadmap: media analysis pipeline | Background audio should be absent or very low behind speech. |
| 1.4.8 | Visual Presentation | AAA | No | No | Missing | Not covered | Roadmap: layout heuristics | Users should have strong control over text presentation. |
| 1.4.9 | Images of Text (No Exception) | AAA | No | No | Missing | Not covered | Tightening of 1.4.5 OCR exception model would unlock | Avoid images of text except where truly essential. |
| 1.4.10 | Reflow | AA | No | Yes | Covered | High | `reflow.py` rendered evaluator: 320 px viewport snapshot plus horizontal-scroll detection | Content should work without two-dimensional scrolling at small viewport or zoom. |
| 1.4.11 | Non-text Contrast | AA | No | Yes | Covered | Low | `policy_1_4_11.py` segmented contrast at UI boundaries (3:1 threshold) | UI parts and graphics need enough contrast against surrounding colors. |
| 1.4.12 | Text Spacing | AA | Yes | Yes | Covered | High | `text_spacing_auditor.py` plus rendered scenario applying C36 / C37 spacing overrides; axe `text-spacing` fallback | Pages should remain usable when line, letter, and word spacing increase. |
| 1.4.13 | Content on Hover or Focus | AA | No | Yes | Covered | High | `hover_focus_content.py` rendered evaluator: hover scan plus Escape dismissal check | Hover or focus popups must be dismissible and stable. |
| 2.1.1 | Keyboard | A | Yes | No | Covered | High | axe-core (`accesskeys`, `widget` rules) plus best-practice fallback | All functionality must work with a keyboard. |
| 2.1.2 | No Keyboard Trap | A | Yes | No | Covered | Medium | `keyboard-trap.check.js`: forward Tab plus Shift Tab plus Escape verification plus arrow-key trap scan plus iframe trap plus F85 modal-without-escape plus F58/F60 heuristics (key suppression and non-modal dismissibility) | Keyboard users must be able to move focus away. |
| 2.1.3 | Keyboard (No Exception) | AAA | No | No | Missing | Not covered | Roadmap: deeper interaction simulation | Everything must work by keyboard with no exceptions. |
| 2.1.4 | Character Key Shortcuts | A | Yes | No | Covered | Medium | `character-key-shortcuts.check.js`: scans `accesskey`, inline `onkeydown / onkeyup / onkeypress` for unguarded single-key handlers | Single-key shortcuts need disable, remap, or focus-only behavior. |
| 2.2.1 | Timing Adjustable | A | Yes | No | Covered | Low | axe `meta-refresh` rule | Users need enough time or a way to extend it. |
| 2.2.2 | Pause, Stop, Hide | A | Yes | Yes | Covered | High | `pause_stop_hide_auditor.py`: `getAnimations()`, GIF frame count, autoplay detection for Bootstrap, Slick, Swiper, Owl, Flickity, Glide, Splide; nearby pause-button regex | Moving or auto-updating content must be pausable or stoppable. |
| 2.2.3 | No Timing | AAA | No | No | Missing | Not covered | Roadmap: session-state monitor | Tasks should not depend on time limits. |
| 2.2.4 | Interruptions | AAA | Yes | No | Covered | Low | axe `meta-refresh-no-exceptions` proxy | Users should be able to delay or avoid interruptions where possible. |
| 2.2.5 | Re-authenticating | AAA | No | No | Missing | Not covered | Roadmap | Re-authentication should not cause data loss. |
| 2.2.6 | Timeouts | AAA | No | No | Missing | Not covered | Roadmap | Users should be warned about data-loss timeouts. |
| 2.3.1 | Three Flashes or Below Threshold | A | No | No | Missing | Not covered | Roadmap: frame-differential analysis on GIF and video (heavy lift) | Content must not flash in a seizure-risk pattern. |
| 2.3.2 | Three Flashes | AAA | No | No | Missing | Not covered | Roadmap: shares pipeline with 2.3.1 | Content should avoid any unsafe flashing. |
| 2.3.3 | Animation from Interactions | AAA | No | No | Missing | Not covered | Roadmap: interaction-animation instrumentation | Motion triggered by interaction should be disableable. |
| 2.4.1 | Bypass Blocks | A | Yes | No | Covered | High | axe `bypass`, `skip-link` rules plus best-practice fallback | Users need a way to skip repeated blocks. |
| 2.4.2 | Page Titled | A | Yes | No | Covered | High | axe `document-title` rule | Each page needs a clear title. |
| 2.4.3 | Focus Order | A | Yes | No | Covered | Low | axe best-practice `tabindex` rule (fallback only) | Keyboard focus should move in a sensible order. |
| 2.4.4 | Link Purpose (In Context) | A | Yes | No | Covered | High | axe `link-name` rule | Link purpose should be clear from its text or nearby context. |
| 2.4.5 | Multiple Ways | AA | Yes | No | Covered | Medium | `multiple-ways.check.js`: requires 2 of {site search, sitemap link, nav, breadcrumb, table of contents, related links, page index list} | More than one way should exist to find a page. |
| 2.4.6 | Headings and Labels | AA | Yes | No | Covered | Medium | axe best-practice `empty-heading` plus heading-order fallback | Headings and labels should describe their purpose clearly. |
| 2.4.7 | Focus Visible | AA | Yes | Yes | Covered | High | `focus-visible.check.js` interactive Tab snapshot plus `policy_2_4_7.py` outline / box-shadow diff | The keyboard focus indicator must be visible. |
| 2.4.8 | Location | AAA | Yes | No | Covered | Medium | `location.check.js`: breadcrumb, sitemap, table of contents, active nav state, `aria-current` markers | Users should know where they are within the site structure. |
| 2.4.9 | Link Purpose (Link Only) | AAA | Yes | No | Covered | Medium | `link-purpose.check.js`: flags generic accessible names ("click here", "read more") without context | Link text alone should make the purpose clear. |
| 2.4.10 | Section Headings | AAA | No | No | Missing | Not covered | Roadmap | Sections should use helpful headings. |
| 2.4.11 | Focus Not Obscured (Minimum) | AA | No | Yes | Covered | High | Python rendered focus-not-obscured-minimum evaluator | Focused items should not be fully hidden behind overlays. |
| 2.4.12 | Focus Not Obscured (Enhanced) | AAA | No | Yes | Covered | High | Python rendered focus-not-obscured-enhanced evaluator | Focused items should not be obscured at all. |
| 2.4.13 | Focus Appearance | AA | Yes | Yes | Covered | Medium | `focus-appearance.check.js` interactive snapshot plus `policy_2_4_13.py` (outline width 2 px or enclosure plus 3:1 contrast) | Focus indicator size and contrast must be strong enough. |
| 2.5.1 | Pointer Gestures | A | No | No | Missing | Not covered | Roadmap | Complex gestures need a simple pointer alternative. |
| 2.5.2 | Pointer Cancellation | A | Yes | No | Covered | Low | `pointer-cancellation.check.js`: flags `onpointerdown` / `onmousedown` triggering navigation or submit without `pointercancel` or `preventDefault` | Pointer actions should not trigger unexpectedly on the down event. |
| 2.5.3 | Label in Name | A | Yes | Yes | Covered | High | `label_in_name_auditor.py`: NFC-normalized casefolded visible label vs computed accessible name | Visible label text should also exist in the accessible name. |
| 2.5.4 | Motion Actuation | A | No | No | Missing | Not covered | Roadmap | Motion-based actions need an alternative and an off switch. |
| 2.5.5 | Target Size | AAA | No | No | Missing | Not covered | Tightening 2.5.8 to 44 px would unlock | Targets should use the larger AAA minimum size. |
| 2.5.6 | Concurrent Input Mechanisms | AAA | No | No | Missing | Not covered | Roadmap | Different input methods should remain available together. |
| 2.5.7 | Dragging Movements | AA | Yes | No | Covered | Medium | `dragging-movements.check.js`: `draggable=true`, HTML5 drag listeners, library detection (Swiper, Slick) | Drag operations need a simpler non-drag alternative. |
| 2.5.8 | Target Size (Minimum) | AA | Yes | Yes | Covered | High | `target_size_auditor.py`: rendered `getBoundingClientRect` vs 24x24 with inline, UA-controlled, and offset exceptions | Tap and click targets need minimum size or safe spacing. |
| 3.1.1 | Language of Page | A | Yes | No | Covered | High | axe `html-has-lang`, `html-lang-valid` | The main page language must be declared. |
| 3.1.2 | Language of Parts | AA | Yes | No | Covered | High | axe `valid-lang` rule | Passages in another language should be marked with that language. |
| 3.1.3 | Unusual Words | AAA | No | No | Missing | Not covered | Roadmap | Uncommon words should be explained. |
| 3.1.4 | Abbreviations | AAA | No | No | Missing | Not covered | Roadmap | Abbreviations should be explained. |
| 3.1.5 | Reading Level | AAA | No | No | Missing | Not covered | Roadmap | Content should be readable at lower complexity or have support. |
| 3.1.6 | Pronunciation | AAA | Yes | No | Covered | Low | `pronunciation.check.js`: `<ruby>`, `<bdi>` with `lang`, `<span lang>` containing IPA | When pronunciation affects meaning, it should be provided. |
| 3.2.1 | On Focus | A | Yes | No | Covered | Medium | `on-focus.check.js`: `onfocus` triggering `window.open` / `location.href` / `submit()` | Focusing an element should not unexpectedly change context. |
| 3.2.2 | On Input | A | Yes | No | Covered | Medium | `on-input.check.js`: `onchange` on `<select>` / radio / checkbox triggering navigation or submit | Changing a field should not unexpectedly submit or navigate. |
| 3.2.3 | Consistent Navigation | AA | No | No | Missing | Not covered | Deferred: needs multi-page crawl queue | Repeated navigation should stay in a consistent order. |
| 3.2.4 | Consistent Identification | AA | No | No | Missing | Not covered | Deferred: needs multi-page crawl queue | The same component should be identified consistently across pages. |
| 3.2.5 | Change on Request | AAA | No | No | Missing | Not covered | Roadmap | Context changes should happen only when requested. |
| 3.2.6 | Consistent Help | AA | Yes | No | Covered | Medium | `consistent-help.check.js`: locates help mechanism (contact, FAQ, chat, support, phone) and records position; single-page scope | Repeated help mechanisms should appear consistently. |
| 3.3.1 | Error Identification | A | No | Yes | Covered | High | `form_auditor.py`: required plus `aria-describedby` plus role `alert` / `aria-live` | Input errors must be identified clearly. |
| 3.3.2 | Labels or Instructions | A | Yes | Yes | Covered | High | `form_auditor.py` plus axe `label`, `form-field-multiple-labels` | Controls need labels or instructions before use. |
| 3.3.3 | Error Suggestion | AA | Yes | No | Covered | Medium | `error-suggestion.check.js`: error containers checked for verb plus target field plus keyword presence | When possible, tell users how to fix an error. |
| 3.3.4 | Error Prevention (Legal, Financial, Data) | AA | Yes | No | Covered | Medium | `error-prevention.check.js`: classifies forms as financial / legal / destructive, requires confirm/review/multi-step/undo safeguards | Important submissions need review, confirmation, or reversal. |
| 3.3.5 | Help | AAA | No | No | Missing | Not covered | Roadmap | Context-sensitive help should be available for complex tasks. |
| 3.3.6 | Error Prevention (All) | AAA | No | No | Missing | Not covered | Roadmap | More workflows should prevent irreversible mistakes. |
| 3.3.7 | Redundant Entry | A | Yes | No | Covered | Medium | `redundant-entry.check.js`: groups related inputs by name or id; flags repeats lacking `autocomplete` or pre-fill | Users should not have to re-enter the same data in one process. |
| 3.3.8 | Accessible Authentication (Minimum) | AA | Yes | No | Covered | Medium | `accessible-auth.check.js`: flags CAPTCHA or cognitive test in auth forms without WebAuthn, magic link, or OTP alternative | Login should not depend only on hard memory or cognitive tests. |
| 3.3.9 | Accessible Authentication (Enhanced) | AAA | No | No | Missing | Not covered | Roadmap | Authentication should avoid cognitive barriers more strongly. |
| 4.1.1 | Parsing | A | Yes | No | Covered | Medium | `html-parsing.check.js`: duplicate id and malformed nesting (kept for back-compat; SC removed in WCAG 2.2) | Markup should not break because of duplicate IDs or invalid structure. |
| 4.1.2 | Name, Role, Value | A | Yes | Yes | Covered | High | axe `aria-*` rules plus image pipeline name-role-value auditor | Custom controls need correct name, role, state, and value. |
| 4.1.3 | Status Messages | AA | Yes | No | Covered | Medium | `status-messages.check.js`: enumerates `role=status / alert`, `aria-live`; emits `custom-status-messages-atomic`, `custom-status-messages-inline-validation`, and `custom-status-messages-toast` | Important status updates must reach assistive tech without stealing focus. |

---

## 5. Technique-Wise Coverage

This section is organized by Success Criterion. For each SC, the table lists the WCAG 2.2 sufficient techniques and failure techniques the implementation actually exercises, with current status.

Status legend: **Covered** = automatically detectable today; **Partial** = detection exists with known false-positive or false-negative risk; **Missed - automatable** = could be added; **Missed - judgment** = subjective or visual, not reliably automatable; **Missed - simulation** = needs interactive replay not yet wired.

### 1.1.1 Non-text Content (Level A)

| Technique | Type | Status | Notes |
|---|---|---|---|
| H37 alt on img | Sufficient | Covered | Missing alt fails. |
| H67 Null alt on decorative | Sufficient | Covered | Strict: any non-empty alt on classifier-labelled decorative fails. |
| H2 Combining adjacent img and text | Sufficient | Missed - automatable | No detection of `<a><img><span>label</span></a>` double-announce. |
| H36 alt on input type=image | Sufficient | Partial | 4.1.2 functional name path only; no dedicated branch. |
| H53 object element fallback | Sufficient | Missed - automatable | `<object>` and `<embed>` fallback content not traversed. |
| ARIA6, ARIA10 aria-label and aria-labelledby on img | Sufficient | Covered | Uses computed accessible name. |
| G94 Short text alternative serves same purpose | Sufficient | Partial | OCR literal match; fails on synonyms. |
| G95 Short text alt provides brief description | Sufficient | Partial | No upper-bound length sanity. |
| F3 CSS background used for meaningful image | Failure | Covered | New `background-image-content.check.js` (INCOMPLETE for missing accessible name). |
| F20 Empty alt on informative | Failure | Covered | Classifier plus OCR gate. |
| F30 Filename or placeholder alt | Failure | Covered | `_EMPTY_OR_GENERIC` set. |
| F38 Decorative not marked with null alt | Failure | Covered | |
| F39 Empty alt on image conveying information | Failure | Covered | Classifier-gated. |
| F65 Missing alt or accessible name | Failure | Covered | |
| F71 Emoji or symbol without text alt | Failure | Missed - automatable | Glyph-only text nodes not checked. |
| F86 ASCII art without text alt | Failure | Missed - judgment | |

### 1.2.1 Audio-only and Video-only (Prerecorded) (Level A)

| Technique | Type | Status | Notes |
|---|---|---|---|
| G158 Transcript for audio-only | Sufficient | Partial | Detects presence; doesn't verify equivalence. |
| G159 Alternative for video-only | Sufficient | Partial | Same. |
| H96 track element | Sufficient | Covered | Track src is HEAD-fetched to confirm reachability. |
| F30 Text alternative is filename | Failure | Partial | Filename-only transcript links are now heuristically flagged; transcript quality remains manual. |

### 1.2.2 Captions (Prerecorded) (Level A)

| Technique | Type | Status | Notes |
|---|---|---|---|
| G93 Open or closed captions | Sufficient | Partial | Detects `<track>` plus `srclang`; content not verified. |
| H95 track element with captions kind | Sufficient | Covered | |
| G87 Closed captions | Sufficient | Partial | Third-party players need manual review. |
| F75 Video without captions | Failure | Covered | Flags missing captions on first-party `<video>`. Cross-origin embeds (YouTube, Vimeo, Wistia) emit INCOMPLETE. |

### 1.2.3 Audio Description or Media Alternative (Prerecorded) (Level A)

| Technique | Type | Status | Notes |
|---|---|---|---|
| G78 Second user-selectable audio track | Sufficient | Partial | Sibling `<audio>` detection; switch-control not verified. |
| G173 Audio-described version | Sufficient | Partial | |
| H96 track element with descriptions kind | Sufficient | Covered | |
| G8 Full text alternative | Sufficient | Partial | Nearby `<details>` or transcript link recognised (EN plus JA). |

### 1.3.1 Info and Relationships (Level A)

Coverage from axe-core plus `policy_1_3_1`: heading-order, listitem inside list, landmark structure, table headers, form-label association, ARIA roles. Empirically the most-failing SC: 5 of 7 sites failed.

### 1.3.2 Meaningful Sequence (Level A)

| Technique | Status | Notes |
|---|---|---|
| C6 CSS to position content | Partial | Flex and grid only. |
| C27 DOM order matches visual | Partial | Structural only. |
| F1 Reorder via float | Covered | |
| F32 Reverse direction | Covered | `flex-direction: *-reverse` detected. |
| F33 White-space-based layout | Missed | |
| F34 White-space between characters | Missed | |
| F49 Table for layout | Missed | |

### 1.3.3 Sensory Characteristics (Level A)

| Technique | Status | Notes |
|---|---|---|
| G96 Non-sensory identifier in addition | Covered | |
| F14 Identify content only by shape or location | Covered (EN), Partial (JA) | CJK word-boundary issues. |
| F26 Graphical symbol alone | Missed - judgment | Needs visual grounding. |

### 1.3.4 Orientation (Level AA)

| Technique | Status | Notes |
|---|---|---|
| G214 Support orientation | Covered | |
| F97 Locking orientation | Covered | |
| F100 Restricting view based on orientation | Partial | Static CSS only; JS-triggered locks miss. |

### 1.4.1 Use of Color (Level A)

| Technique | Type | Status | Notes |
|---|---|---|---|
| G14 Information not by color alone | Sufficient | Partial | Inline-link prose only. |
| G182 Additional non-color cue | Sufficient | Covered | Six cue categories inspected. |
| G205 Text color plus additional cue | Sufficient | Partial | Inline-link block containers only. |
| C15 CSS to change presentation | Sufficient | Covered | |
| F13 Color-only in charts, forms, maps | Failure | Partial | Heuristic detection added for color-only instructional copy; chart/map semantics still partial. |
| F73 Link distinguished by color only | Failure | Covered | Core path. |
| F81 Required fields by color only | Failure | Partial | Required controls now include color-only cue heuristics when no textual marker is present. |

### 1.4.2 Audio Control (Level A)

| Technique | Type | Status | Notes |
|---|---|---|---|
| G60 Sound that turns off within 3 s | Sufficient | Partial | Requires `data-duration` or `.duration`; NaN treated as over 3 s. |
| G170 Control near beginning | Sufficient | Covered | Native `controls` or external pause / stop / mute / volume button. |
| G171 Sound only on request | Sufficient | Partial | Inferred via autoplay and muted attrs. |
| F23 Autoplay over 3 s without controls | Failure | Covered | |

### 1.4.3 Contrast (Minimum) and 1.4.6 Contrast (Enhanced)

| Technique | Status | Notes |
|---|---|---|
| G18 4.5:1 ratio | Covered | Core formula. |
| G145 3:1 for large text | Covered | 18 pt or 14 pt-bold threshold. |
| G17 7:1 for 1.4.6 | Covered | Policy 1.4.6. |
| G148 No author-specified colors | Missed - judgment | |
| G174 Alternative high-contrast version | Missed - automatable | No theme-toggle detection. |
| F24 Foreground without background | Missed - automatable | Pixel-based only. |
| F83 Background image fails contrast | Partial | Implicit via pixel rendering. |

### 1.4.4 Resize Text, 1.4.10 Reflow, 1.4.12 Text Spacing, 1.4.13 Hover or Focus Content

Each rule runs a Playwright scenario (viewport resize, font-size 200 percent, CSS overrides, 320 px reflow, hover scan), captures a rendered snapshot, and diffs bounding boxes pre-post.

* **1.4.4:** F69 clipped at 200 percent Covered; G142 ems / percentages Partial; C12 / C13 / C14 stylesheet inspection not done.
* **1.4.10:** F102 fixed-size container Covered; C32 / C34 flex grid responsive Partial.
* **1.4.12:** C36 / C37 user-overrideable spacing Covered; F104 clipping at increased spacing Covered.
* **1.4.13:** F95 pointer-remove triggers hide Covered; dismissible, hoverable, persistent all Partial.

### 1.4.5 Images of Text (Level AA)

| Technique | Status | Notes |
|---|---|---|
| C22 CSS to control text presentation | Partial | Flags candidates; cannot propose CSS replacement. |
| G140 Separate text and decorative image | Missed - judgment | |
| C30 Style switcher | Missed - automatable | |
| F71 Information via image text only | Covered | OCR-heavy detection. |
| **CSS background text** | Covered (incomplete) | New `background-image-content.check.js` text-hint branch (banner, headline, hero, cta, promo, callout, masthead, heading, text). |

### 1.4.11 Non-text Contrast (Level AA)

| Technique | Status | Notes |
|---|---|---|
| G195 Author 3:1 contrast | Partial | Only when boundary is visually present. |
| G207 3:1 active state vs surroundings | Partial | Active and hover states not simulated. |
| G209 Sufficient contrast at default | Covered | |
| F78 Focus indicator without 3:1 | Partial | Handled via 2.4.7 / 2.4.13. |

### 2.1.1 Keyboard (Level A)

axe `accesskeys` plus widget rules. Custom keyboard logic lives in 2.1.2 and 2.1.4 below.

### 2.1.2 No Keyboard Trap (Level A)

| Technique | Type | Status | Notes |
|---|---|---|---|
| G21 No keyboard trap | Sufficient | Covered | Forward plus reverse Tab cycles, 200-tab ceiling. |
| F10 Two non-exiting controls | Failure | Covered | Two-element cycle pattern. |
| F85 Modal traps focus without close | Failure | Covered | Added 2026-04-23: focuses every visible `dialog[open]`, `[role=dialog]`, `[aria-modal=true]`, presses Escape, fails if focus stays inside. |
| F58 Script blocks keyboard events | Failure | Partial | Inline/script key handlers suppressing Tab/Escape/Arrow via `preventDefault()` are heuristically flagged. |
| F60 Pop-up that cannot be closed | Failure | Partial | Non-modal popup candidates are probed for Escape dismissibility and close affordance. |

### 2.1.4 Character Key Shortcuts (Level A)

| Technique | Status | Notes |
|---|---|---|
| G217 Mechanism to remap | Partial | |
| G90 Modifier requirement | Partial | |
| F99 Single-key shortcut without remap | Partial | Bundled JS handlers (React, Vue) invisible. |

### 2.2.2 Pause, Stop, Hide (Level A)

| Technique | Status | Notes |
|---|---|---|
| G4 Content pauses and resumes | Partial | Detects button existence, not state-change. |
| G11 Moving text under 5 s | Covered | |
| G152 Animated GIF stops after 5 s | Covered | Frame-count for infinite loop. |
| G186 Pause button | Partial | 2-level DOM ancestor scan. |
| G191 Pause / stop / hide button with text | Partial | Regex includes EN plus JA. |
| F16 Scrolling without pause | Covered | Marquee. |
| F50 Hand-rolled setInterval or rAF animation | Failure | Missed - automatable | Bypasses library detection. |

### 2.4.5 Multiple Ways (Level AA)

G161 Search Covered; G185 Sitemap link Covered; G63 Sitemap Partial; G64 Table of contents Partial; G125 Related-pages Partial; G126 List-of-links Partial. Single-URL scope limits true site-level verification.

### 2.4.7 Focus Visible (Level AA) and 2.4.13 Focus Appearance (Level AAA)

| Technique | Status | Notes |
|---|---|---|
| G149 UA focus indication | Partial | `:focus-visible` inheritance inconsistent. |
| G165 / G195 Author focus indicator | Covered | |
| C15 :focus styling | Covered | |
| F55 Remove default focus without replacement | Covered | `outline:0` plus no alternative. |
| F78 Focus indicator without 3:1 | Partial for 2.4.13 | |

### 2.4.8 Location (Level AAA)

G65 Breadcrumb Covered; G128 Indication of current location Covered; G63 Sitemap Partial; G127 Table of contents Partial.

### 2.4.9 Link Purpose (Link Only) (Level AAA)

G53, H30, F84 Covered; G91, H33 Partial. Keyword list is finite; localization English plus Japanese mainly.

### 2.5.2 Pointer Cancellation (Level A)

G210 Up-event only Partial; F101 Down-event trigger Covered; F102 No cancel mechanism Partial. Inline-handler bias (React or Vue invisible); draggable essential exemption not detected.

### 2.5.3 Label in Name (Level A)

G208, G211, F96 all Covered. Limitations: icon-only controls have no visible label so no violation possible; whitespace vs punctuation edge cases; shadow DOM not traversed.

### 2.5.7 Dragging Movements (Level AA)

G219 Single-pointer alternative Partial; F105 Dragging without alternative Covered. Custom `pointermove`-with-transform implementations are library-detected only.

### 2.5.8 Target Size (Minimum) (Level AA)

G219 24x24 Covered; inline, UA-controlled, and offset exceptions Covered; essential and equivalent exceptions Missed - judgment. Runs at 1440 px viewport; iframe contents not descended.

### 3.3.1 Error Identification and 3.3.2 Labels or Instructions (Level A)

| Technique | Status | Notes |
|---|---|---|
| G83 / G84 / G85 Text description of error | Partial | Container presence only, not text quality. |
| G139 Text cue adjacent | Missed - automatable | No positional proximity check. |
| ARIA19 Programmatic error announcement | Covered | |
| H44 label associated with control | Covered | |
| H65 title for unlabelled control | Partial | Discouraged; no warning. |
| H90 legend for fieldset | Missed - automatable | Grouping unaudited. |
| F82 Visual grouping without programmatic | Missed - automatable | |

### 3.3.3 Error Suggestion (Level AA)

G83 / G84 / G85 Partial; G177 Suggesting valid text Partial. Keyword-based; fails on internationalized error copy. No form submission.

### 3.3.4 Error Prevention (Legal, Financial) (Level AA)

G98 Reversible Partial; G99 Checked Partial; G155 Confirmation Partial; G164 Undo window Partial. Keyword classifier plus undo/revert signal heuristic; still no real submission replay.

### 3.3.7 Redundant Entry (Level A)

G218 Auto-fill from previous step Partial. Single-page evaluation cannot observe wizard step-to-step state.

### 3.3.8 Accessible Authentication (Minimum) (Level AA)

G218 Alternative authentication Partial; F109 CAPTCHA as only auth Partial. Niche CAPTCHA providers miss; invisible reCAPTCHA v3 cannot be flagged.

### 4.1.1 Parsing (Level A)

H93 Unique id Covered; H94 No duplicate attributes Partial. Note: SC 4.1.1 was removed in WCAG 2.2; rule kept for back-compat.

### 4.1.3 Status Messages (Level AA)

ARIA19 `aria-live` Covered; ARIA22 `role=status` Covered; ARIA23 `role=log` Partial; G199 Programmatically determined status Partial; F114 Toast without ARIA Partial via `custom-status-messages-toast`. Snapshot-only; cannot verify announcement on event.

---

## 6. How Each Covered SC Is Addressed

This is a one-paragraph plain-English summary for each covered SC, suitable for sharing with non-technical stakeholders.

**1.1.1 Non-text Content.** A four-stage pipeline. The crawler captures every image into an `ImageData` record. A CNN classifier labels each image as informative, decorative, logo, icon, functional, complex, or text. OCR extracts any text in the image. Then a policy rule compares the alt text against the classifier intent, the OCR content, and W3C WAI naming conventions. As of 2026-04-23, CSS background images are also walked: any non-decorative `background-image` URL on an element without an accessible name raises an INCOMPLETE finding.

**1.2.1 Audio-only and Video-only (Prerecorded).** Two emitters. The Python `media_auditor` checks for transcript presence on `<audio>` elements. The Node `audio-transcript.check.js` looks for transcript links in surrounding `figure / article / section / [role=region]` containers using locale-aware keywords (EN plus JA), HEAD-fetches linked transcript files, and flags filename-only transcript labels as an F30 risk.

**1.2.2 Captions (Prerecorded).** New in 2026-04-23. For every visible `<video>`, the check requires a `<track kind="captions"|"subtitles">` child with a non-empty `srclang`. Cross-origin embeds (YouTube, Vimeo, Wistia) cannot be inspected from outside their iframe and are emitted as INCOMPLETE for manual review.

**1.2.3 Audio Description or Media Alternative.** New in 2026-04-23. Three signals satisfy the rule: a `<track kind="descriptions">` with `srclang`, a sibling `<audio>` source whose title or `data-kind` contains "description", or a nearby transcript link or `<details>` block. EN plus JA keyword coverage built in.

**1.3.1 Info and Relationships.** Driven by axe-core's mature rule set covering heading order, list semantics, landmark structure, table headers, form-label association, and ARIA role validity. This SC was the most common failure in our 2026-03-26 empirical scan (5 of 7 sites failed).

**1.3.2 Meaningful Sequence.** Scans up to 2,000 flex and grid containers for layout reversal patterns: `flex-direction: row-reverse` or `column-reverse`, explicit `grid-column-start` or `grid-row-start`, mixed floats, non-default `order` values on children. Catches the most common DOM-versus-visual mismatch shapes.

**1.3.3 Sensory Characteristics.** Uses spaCy NLP (English `en_core_web_sm`, Japanese `ja_core_news_sm`) to find instructional sentences. The auditor strips purpose phrases, sensory words, generic UI nouns, and stop words; if any non-sensory label remains, the rule passes. Vocabulary lists for both languages are curated.

**1.3.4 Orientation.** Two emitters. Node looks for CSS `@media (orientation:*)` rules, JavaScript `screen.orientation.lock`, meta-viewport `orientation=`, and rotate-overlay prompts. Python rendered evaluator confirms the page reflows in both orientations.

**1.3.5 Identify Input Purpose.** axe-core `autocomplete-valid` rule.

**1.4.1 Use of Color.** Finds links inside prose containers (`p`, `li`, `td`, `th`, `blockquote`, `article > p`, `dd`, `section > p`, `svg`). For each link, computes the ancestor baseline style and verifies at least one non-color cue: text-decoration, border-bottom, outline, font-style, background-color, or 100-unit font-weight delta. It now also adds non-link heuristics for color-only required-field indicators and color-only instructional copy.

**1.4.2 Audio Control.** New in 2026-04-23. Enumerates `<audio>` and `<video>` with `autoplay` (attribute or `data-autoplay`); skips muted media; if duration is unknown or over 3 seconds and there is neither a `controls` attribute nor an external pause / stop / mute / volume button in the same `figure / article / section / [role=region]` container, the rule fails.

**1.4.3 Contrast (Minimum) and 1.4.6 Contrast (Enhanced).** Computer-vision pipeline: render screenshot, EAST or CRAFT text detection, OCR plus bounding box, per-bbox Otsu binarization to separate foreground from background, convert to linear sRGB, compute relative luminance, apply `(L1 + 0.05) / (L2 + 0.05)`, threshold at 4.5:1 (3:1 large) for 1.4.3 and 7:1 (4.5:1 large) for 1.4.6. axe-core `color-contrast` provides cross-check coverage.

**1.4.4 Resize Text.** Rendered evaluator zooms to font-size 200 percent and diffs bounding boxes pre and post for clipping and horizontal scroll.

**1.4.5 Images of Text.** Defense in depth. Node `images-of-text.check.js` scores `<img>` by `src` keywords, alt length over 5 words, and punctuation density. Python OCR pipeline re-verifies via OCR token count and classifier label. New 2026-04-23: `background-image-content.check.js` flags background images whose URL contains text-hint keywords.

**1.4.10 Reflow.** Renders at 320 px viewport, snapshots, detects horizontal scroll. Catches the F102 fixed-size container failure.

**1.4.11 Non-text Contrast.** Analyzes rendered boundaries of UI components (button border, focus ring) using segmented contrast at 3:1.

**1.4.12 Text Spacing.** Applies the WCAG-prescribed CSS overrides (line-height 1.5, letter-spacing 0.12em, word-spacing 0.16em, paragraph-spacing 2x font-size) and diffs bounding boxes for clipping.

**1.4.13 Content on Hover or Focus.** Hover scan plus Escape dismissal check. F95 (pointer-remove triggers hide) is covered; dismissible, hoverable, and persistent properties are partially verified.

**2.1.1 Keyboard.** axe-core widget and accesskey rules.

**2.1.2 No Keyboard Trap.** Probe stack: forward Tab up to 200 times tracking last 4 focused keys, Shift Tab reverse traversal, Escape verification after each suspected trap, arrow-key trap scan for `role=tree / grid / listbox / menu / tablist / radiogroup`, same-origin iframe Tab trap, modal F85 check, plus 2026-04-24 heuristics for scripted key suppression (`preventDefault` on Tab/Escape/Arrow) and non-modal popup dismissibility.

**2.1.4 Character Key Shortcuts.** Scans `accesskey` attributes and inline `onkeypress` / `onkeydown` / `onkeyup` for single printable-character handlers without modifier-key guards or non-input target restriction.

**2.2.1 Timing Adjustable.** axe `meta-refresh` rule.

**2.2.2 Pause, Stop, Hide.** Playwright `getAnimations()` API plus Pillow GIF frame count plus library introspection (Bootstrap, Slick, Swiper, Owl, Flickity, Glide, Splide). Looks for nearby pause buttons via 2-level ancestor scan with EN plus JA keyword regex.

**2.4.1 to 2.4.4.** axe-core (`bypass`, `document-title`, `tabindex`, `link-name`).

**2.4.5 Multiple Ways.** Counts presence of at least 2 of: site search input, sitemap link, navigation landmarks, breadcrumb component, table of contents, related-links area, or page-index/list-of-pages signal.

**2.4.7 Focus Visible.** Two emitters. Node `focus-visible.check.js` tabs through focusable elements and snapshots before / after CSSOM (outline, box-shadow, border) for delta. Python `policy_2_4_7` performs the same diff at policy level. Empirically failed on 5 of 7 sites in 2026-03-26 scan.

**2.4.8 Location.** Detects breadcrumb nav, sitemap/ToC location aids, active nav state, `aria-current="page"` / `"step"`, and JSON-LD breadcrumb signals.

**2.4.9 Link Purpose (Link Only).** Computes accessible name of every link; flags generic names ("click here", "read more", JA equivalents) without `aria-describedby` or context.

**2.4.11 / 2.4.12 Focus Not Obscured.** Python rendered evaluator focuses each interactive element and verifies the focused element is not occluded (minimum: not fully hidden; enhanced: not partially obscured at all).

**2.4.13 Focus Appearance.** Snapshots each focusable element before and after `focus()`. Requires outline-width 2 px or enclosure plus 3:1 contrast against adjacent color. Empirically failed on 6 of 7 sites in 2026-03-26 scan, the most common failure observed.

**2.5.2 Pointer Cancellation.** Finds elements with `onpointerdown` or `onmousedown` triggering navigation or submit without matching up-event; checks for `pointercancel` or `preventDefault` patterns.

**2.5.3 Label in Name.** For each interactive element, NFC-normalized casefolded visible label text is compared against the computed accessible name. Failure if visible label is non-empty and accessible name does not contain it.

**2.5.7 Dragging Movements.** Detects `draggable=true`, HTML5 drag listeners, Swiper, Slick, native range. Flags when no alternative single-pointer action (button, keyboard) is present in vicinity.

**2.5.8 Target Size (Minimum).** Rendered `getBoundingClientRect` against 24x24. Exceptions implemented for inline (display inline plus paragraph parent), UA-controlled (`appearance` unchanged), and offset (theoretical 24 box around centre does not intersect neighbours).

**3.1.1 Language of Page and 3.1.2 Language of Parts.** axe-core `html-has-lang`, `html-lang-valid`, `valid-lang`.

**3.1.6 Pronunciation.** Scans `<ruby>`, `<bdi>` with `lang`, `<span lang>` containing IPA, and dictionary-link adjacency for ambiguous words.

**3.2.1 On Focus.** Detects `onfocus` handlers triggering `window.open`, `location.href`, or `submit()`.

**3.2.2 On Input.** Detects `onchange` on `<select>`, `<input type=checkbox>`, or radio triggering navigation or submit.

**3.2.6 Consistent Help.** Locates help mechanism (contact, FAQ, chat, support link, phone) and records its position (header, footer, sidebar, inline). Reported per page; cross-page comparison requires a multi-page crawler.

**3.3.1 Error Identification.** For each input, select, textarea: checks `required`, `aria-describedby`, and `role=alert` or `aria-live` presence.

**3.3.2 Labels or Instructions.** axe `label` and `form-field-multiple-labels` plus `form_auditor.py` checking accessible name (label, `aria-label`, `aria-labelledby`) and autocomplete for email, tel, password fields.

**3.3.3 Error Suggestion.** For each error container (`aria-invalid`, `role=alert`, `.error`), checks for suggestion text presence (verb plus target field plus keywords like "must", "should", "cannot be empty").

**3.3.4 Error Prevention (Legal, Financial).** Classifies forms as financial / legal / destructive via keyword scan of submit button plus headings plus form metadata, then requires at least one safeguard: confirm step, review page, irreversibility warning, multi-step indicator, or undo/revert window signal.

**3.3.7 Redundant Entry.** Groups related inputs by name or id; across repeated fields, detects identical fields without `autocomplete` or pre-filled value.

**3.3.8 Accessible Authentication (Minimum).** Finds auth forms (password input or login keywords). Flags presence of CAPTCHA image, reCAPTCHA iframe, or cognitive-test keywords without an alternative (WebAuthn, magic link, OTP).

**4.1.1 Parsing.** Counts duplicate `id=` attributes and flags malformed nesting (`<a>` inside `<a>`, `<button>` inside `<button>`). Note: SC 4.1.1 was removed in WCAG 2.2; emitter retained for back-compat.

**4.1.2 Name, Role, Value.** axe-core ARIA suite plus Python image-pipeline name-role-value auditor.

**4.1.3 Status Messages.** Enumerates `role=status`, `role=alert`, `aria-live="polite"|"assertive"` regions, counts them, inspects form inline-validation containers (`.error`, `[aria-invalid=true]`) for missing live-region association, and heuristically flags toast libraries without ARIA live semantics. Emits `custom-status-messages-atomic`, `custom-status-messages-inline-validation`, and `custom-status-messages-toast`.

---

## 7. Existing Solutions: Known Limitations to Track

These are the gaps **inside SCs we already cover**. They do not move the SC out of "covered" but should be on the remediation backlog.

| SC | Limitation | Impact |
|---|---|---|
| 1.1.1 | 3-char alt floor causes false negatives for valid 2-letter tokens (UI, Go, OK) | False negatives on icon labels |
| 1.1.1 | Synonym blindness in OCR-vs-alt match (alt "Look up" vs OCR "Search") | False positives |
| 1.1.1 | SVG inline `<title>` parsing inconsistent | Accessible-name fallback to filename |
| 1.4.3 | Otsu segmentation fails on glassmorphism and gradients | Returns N/A rather than WARNING |
| 1.4.3 | Disabled-state exemption not honoured | False positives on `:disabled` controls |
| 1.4.3 | `::before` and `::after` pseudo-content not directly inspected | Reliant on OCR even when CSSOM is available |
| 1.4.4 to 1.4.13 | Geometric clipping detection only (`offsetWidth > scrollWidth`) | Padding-hidden text without overflow missed |
| 1.4.4 to 1.4.13 | Reflow false positives on intentional horizontally-scrolling regions (data tables, code blocks) | Whitelist needed |
| 1.4.5 | Heuristic uses English / ASCII word counts | JA / CJK text-heavy images score lower than intended |
| 1.4.11 | Buttons styled only with background fill (no border) treated as having no boundary | Returns N/A |
| 1.4.11 | Hover, focus, active state contrast not measured | Requires rendered-state simulation |
| 2.1.2 | 200-tab ceiling | Very long pages with over 200 focusable elements may miss late traps |
| 2.1.2 | Stable-key fallback uses DOM position when id or name absent | Layout shifts produce noisy cycle detections |
| 2.2.2 | Pause-button click not simulated | "Fake" pause buttons pass |
| 2.2.2 | Custom setInterval / rAF animations invisible | F50 missed |
| 2.4.5 | Single-URL scope | Cannot verify true site-level "multiple ways" |
| 2.4.7 | Fixed 100-step tab limit | Very long forms miss elements |
| 2.4.7 | Custom-drawn focus on canvas or SVG cannot be measured from DOM style | False negatives on canvas widgets |
| 2.4.13 | Time-budget ceiling at 2,000 elements | Late elements unaudited |
| 2.5.3 | Shadow DOM not traversed | Controls inside closed shadow roots missed |
| 2.5.8 | Viewport-coupled at 1440 px | Mobile target-size unmeasured |
| 2.5.8 | Cross-origin iframes not descended | Iframe contents missed |
| 3.3.1 / 3.3.2 | Forms not submitted | Errors that only appear after submit invisible |
| 3.3.1 / 3.3.2 | Fieldset and legend grouping not audited | H90 missed |
| 4.1.3 | Snapshot-only; cannot verify announcement on event | Toast heuristics added for common libraries, but runtime insertion/announcement still requires interaction replay |

### Cross-cutting systemic issues

| Area | Issue | Status |
|---|---|---|
| Image capture failures | Now propagated as `capture_status` end to end with INCOMPLETE finding status | **Fixed 2026-04-23** |
| Cross-service finding duplication | axe and Python pipeline both emit for shared SCs (1.1.1, 2.4.7, 2.5.3, 4.1.2); element-signature divergence causes duplicates | Open: harmonise signatures at formatter |
| Language detection drift | DOM `lang` plus CJK heuristic; mismatched `<html lang="en">` with JA body underperforms sensory check | Open: per-element `fasttext-langid` |
| Browser settle timing per-rule | `SETTLE_MS` 60 / 80 / 300 scattered with no central budget; flakes on slow CI | Open: centralise in `shared-config.yaml` |
| Japanese CJK word-boundary | `_remaining_label_words` strips by character class, destroying word boundaries | Open: SudachiPy morpheme tokenization |

---

## 8. Empirical Validation Snapshot (2026-03-26)

7 production sites tested via `POST /api/v1/analyse-url-flat`. **38 of 53** then-covered SCs observed firing.

| Site | Total | Fail | Pass | Needs Review | Top WCAG failures |
|---|---:|---:|---:|---:|---|
| W3Schools | 266 | 179 | 56 | 31 | 1.3.1 (aria), 1.4.3 (contrast), 2.5.8 (targets), 2.4.13 (focus) |
| IRS.gov | 101 | 6 | 58 | 37 | 1.3.1 (landmarks), 2.4.7 (focus visible), 4.1.1 (dup IDs) |
| BBC | 135 | 39 | 55 | 41 | 1.4.3 (contrast), 2.4.7 (focus visible), 2.4.13 (focus appearance) |
| Amazon | 27 | 3 | 20 | 4 | 1.3.1 (aria), limited crawl (anti-bot) |
| Stack Overflow | 35 | 4 | 27 | 4 | 2.4.6 (headings), 4.1.2 (aria) |
| Wikipedia | 81 | 6 | 60 | 15 | 2.4.2 (title), 2.4.7 (focus visible) |
| NHS UK | 69 | 8 | 57 | 4 | 2.4.13 (focus), 3.2.1 (on-focus), 4.1.3 (status) |

**Most-failing SCs in the wild:** 2.4.13 Focus Appearance (6 of 7 sites), 1.3.1 Info and Relationships (5 of 7), 2.4.7 Focus Visible (5 of 7), 1.4.3 Contrast (5 of 7 needs-review or fail). High remediation ROI for these four.

---

## 9. Missing Rules Summary

| Level | Missing count | Missing criteria |
|---|---:|---|
| A | 3 | 2.3.1 Three Flashes; 2.5.1 Pointer Gestures; 2.5.4 Motion Actuation |
| AA | 4 | 1.2.4 Captions (Live), 1.2.5 Audio Description (Prerecorded), 3.2.3 Consistent Navigation, 3.2.4 Consistent Identification |
| AAA | 24 | 1.2.6, 1.2.7, 1.2.8, 1.2.9, 1.3.6, 1.4.7, 1.4.8, 1.4.9, 2.1.3, 2.2.3, 2.2.5, 2.2.6, 2.3.2, 2.3.3, 2.4.10, 2.5.5, 2.5.6, 3.1.3, 3.1.4, 3.1.5, 3.2.5, 3.3.5, 3.3.6, 3.3.9 |

_Note: 1.2.5 Audio Description (Prerecorded) still remains partial via `audio-description.check.js` and is excluded from the covered-count totals._

## 10. Coverage Growth Opportunities (Roadmap)

| Technique family | Missing SCs unlocked | Why this is efficient |
|---|---:|---|
| Multi-page crawl queue | 4 (3.2.3, 3.2.4, plus elevates 2.4.5 and 3.2.6 from "single-page scope") | Largest remaining gap; explicitly deferred from 2026-04-23 sprint |
| Media analysis pipeline | 10 (1.2.4 to 1.2.9, 1.4.7, 2.3.1, 2.3.2, plus tightens 1.2.5) | Single pipeline covers prerecorded alternatives, live captions, flash checks, background audio |
| NLP enrichment (fasttext-langid plus ja_core_news_lg) | 5 (3.1.3, 3.1.4, 3.1.5, 1.3.6, plus elevates 1.3.3 quality) | Language, sensory-instruction, readability cluster naturally |
| Stateful workflow replay | 4 (3.3.5, 3.3.6, plus tightens 3.3.7 and 3.3.9) | Help, error-prevention, enhanced authentication |
| Motion and gesture instrumentation | 3 (2.3.3, 2.5.1, 2.5.4) | Gesture, motion-from-interaction, motion-actuation share runtime hooks |
| Session-state monitor | 3 (2.2.3, 2.2.5, 2.2.6) | Timeout and interruption handling |
| Deeper interaction simulation | 3 (2.1.3, 2.5.6, 3.2.5) | Keyboard-no-exception, concurrent input, change-on-request |
| Layout heuristics extension | 2 (1.4.8, 2.4.10) | Section headings and visual presentation |
| OCR exception tightening | 1 (1.4.9) | Tightens current 1.4.5 model |
| Target-size threshold extension | 1 (2.5.5) | Existing 24x24 crawler extended to 44x44 |
| Dynamic status-message replay | quality boost on 4.1.3 | Needed to verify that live-region updates are actually announced at runtime |

## 11. Counting Rules and Caveats

| Topic | Decision | Why it matters |
|---|---|---|
| Unit of coverage | WCAG 2.2 success criteria only | Prevents best-practice-only rules from inflating compliance coverage |
| Best-practice rules | Counted only when fallback-mapped to a WCAG SC by the Node mapper | Reflects what the API actually emits |
| Python metadata vs implementation | Counted from emitted findings, not from `combined/constants.py` | Includes `_run_pipeline_stage()` policy outputs in addition to direct `findings.py` converters |
| Node version basis | `axe-core 4.11.1` inventory | Differs from semver in `package.json` |
| Requested WCAG level | Behaviour is level-gated; Node keeps best-practice enabled at all levels | Fallback-mapped SCs can appear at lower requested levels |
| 1.4.5 Node check | Heuristic (src-path plus alt-text signals); not OCR | For confirmed text-in-image use the Python OCR pipeline |
| Cross-origin embeds (1.2.2 / 1.2.3 / 1.4.2) | Emitted as INCOMPLETE | Caption and audio-track state cannot be inspected across origins |
| Image capture failures | Now distinct status `incomplete` with `capture_error` | Was silently treated as N/A pre-2026-04-23 |

---

## 12. Test-Suite Status

| Suite | Tests | Status |
|---|---:|---|
| `ka11y-python` (pytest) | 618 | 601 passing, 17 failing locally (15 due missing `nltk`, 2 assertion failures) |
| `ka11y-node` (jest) | 226 | All passing |
| Custom-check files | 28 | All registered and emitting |
| Real-world site validation | 7 sites | Verified 2026-03-26 |

---

*Prepared for client review on 2026-04-24. Built from `code-review.md` (2026-04-23 sprint review) and the prior `COVERAGE.md` empirical baseline (2026-03-26).*
