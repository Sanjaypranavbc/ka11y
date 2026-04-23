# ka11y Code Review — WCAG Technique Coverage & Limitations

**Date:** April 23, 2026
**Scope:** Full audit of implemented rules in `ka11y-python/` and `ka11y-node/`, cross-referenced against W3C WCAG 2.2 Techniques (Sufficient + Failure).
**Goal:** Identify what each rule *actually* detects vs. what the WCAG SC requires, so gaps can be closed or documented.

---

## Sprint changes — 2026-04-23

Priority sprint items from the previous review addressed in this pass:

| Item | Status | Files changed |
|---|---|---|
| **§3.1 Silent image-capture failures** | Fixed | `ka11y-python/ka11y/crawler/models.py` (+`capture_status`, `capture_error` fields) · `crawler/crawler.py` (`_safe_screenshot_status` returns `(ok, status, err)`; failed captures still register as `ImageData`) · `accessibility/rules/non_text/alttext.py` (short-circuits to INCOMPLETE status) · `api/v1/combined/findings.py` (new `_capture_incomplete_finding`; 1.1.1 + 4.1.2 converters emit `status="incomplete"`) |
| **1.2.2 Captions (Prerecorded)** | Implemented | New `ka11y-node/src/custom-checks/captions-prerecorded.check.js`; flags `<video>` without `<track kind="captions">` and raises INCOMPLETE for cross-origin embeds (YouTube / Vimeo / Wistia). |
| **1.2.3 Audio Description** | Implemented | New `audio-description.check.js`; detects `<track kind="descriptions">`, alternate description audio, and nearby full-text transcript links. EN + JA keyword coverage inline. |
| **1.4.2 Audio Control** | Implemented | New `audio-control.check.js`; flags unmuted autoplay media without controls or an external pause control within the same figure/region. |
| **CSS `background-image` scan (1.1.1 / 1.4.5)** | Implemented | New `background-image-content.check.js`; walks non-decorative background images, emits INCOMPLETE for elements without an accessible name and a separate 1.4.5 INCOMPLETE when the URL carries text-hint keywords (`banner`/`headline`/`hero`/`cta`). |
| **2.1.2 Shift+Tab + Escape** | Extended | `keyboard-trap.check.js` already had Shift+Tab + cycle-Escape verification; this pass added **F85 modal-without-escape** detection — focuses every visible `dialog[open]` / `[role="dialog"]` / `[aria-modal="true"]`, presses Escape, and FAILs if focus remains inside. |
| **Japanese support** | Verified | Auditing confirmed `config/universal.yml` already carries EN+JA keyword lists across 30+ categories; `sensory_auditor.py` has `SENSORY_WORDS_JA`, `GENERIC_UI_NOUNS_JA`, `STOP_WORDS_JA` with particles (は/が/を/に) and `_detect_lang` overrides `<html lang="en">` when body text is CJK. New checks ship with inline EN+JA copy. |
| **Multi-page crawling (2.4.5 / 3.2.3 / 3.2.4 / 3.2.6)** | Deferred | Explicitly out of scope this sprint — requires a new crawl queue + cross-page dedup layer. Documented as future work. |

Test results after changes: `ka11y-python` 616/618 passing (2 pre-existing failures unrelated to this pass), `ka11y-node` 226/226 passing.

---

## Legend

| Column | Meaning |
|---|---|
| **Covered** | Technique is detectable automatically by the current code path. |
| **Partial** | Detection exists but with known false-positive / false-negative risk. |
| **Missed — automatable** | Could be detected with additional logic; gap to close. |
| **Missed — requires human judgment** | Cannot be reliably automated (subjective, visual, or semantic); out-of-scope. |
| **Missed — requires interactive simulation** | Needs browser interaction (hover, keyboard, submit); not yet wired. |

Technique IDs use WCAG 2.2 numbering: `G*` (general), `H*` (HTML), `C*` (CSS), `SCR*` (script), `ARIA*`, `F*` (failure).

---

## Summary — Implemented SC Coverage

| SC | Level | ka11y-python | ka11y-node | Status |
|---|---|---|---|---|
| 1.1.1 Non-text Content | A | Full pipeline | axe-core only | Strong |
| 1.2.1 Audio/Video-only (Prerecorded) | A | `media_auditor.py` | `audio-transcript.check.js` | Partial |
| 1.2.2 Captions (Prerecorded) | A | — | axe-core only | **Gap** |
| 1.2.3 Audio Description or Media Alt | A | — | axe-core only | **Gap** |
| 1.2.4 Captions (Live) | AA | — | — | **Not implemented** |
| 1.2.5 Audio Description (Prerecorded) | AA | — | — | **Not implemented** |
| 1.3.1 Info and Relationships | A | `policy_1_3_1` | axe-core | Partial |
| 1.3.2 Meaningful Sequence | A | — | `meaningful-sequence.check.js` | Partial |
| 1.3.3 Sensory Characteristics | A | `sensory_auditor.py` | — | Partial (NLP-bounded) |
| 1.3.4 Orientation | AA | rendered evaluator | `orientation.check.js` | Strong |
| 1.3.5 Identify Input Purpose | AA | — | axe-core only | Partial |
| 1.4.1 Use of Color | A | — | `use-of-color.check.js` | Partial (links only) |
| 1.4.2 Audio Control | A | — | — | **Not implemented** |
| 1.4.3 Contrast (Minimum) | AA | `contrast_analyser.py` | axe-core | Strong |
| 1.4.4 Resize Text | AA | rendered evaluator | — | Partial |
| 1.4.5 Images of Text | AA | pipeline + policy | `images-of-text.check.js` | Partial |
| 1.4.6 Contrast (Enhanced) | AAA | `policy_1_4_6` | — | Strong |
| 1.4.10 Reflow | AA | rendered evaluator | — | Partial |
| 1.4.11 Non-text Contrast | AA | `policy_1_4_11` | — | Partial |
| 1.4.12 Text Spacing | AA | `text_spacing_auditor.py` + rendered | — | Partial |
| 1.4.13 Content on Hover or Focus | AA | rendered evaluator | — | Partial |
| 2.1.1 Keyboard | A | — | axe-core only | Partial |
| 2.1.2 No Keyboard Trap | A | — | `keyboard-trap.check.js` | Partial |
| 2.1.4 Character Key Shortcuts | A | — | `character-key-shortcuts.check.js` | Partial |
| 2.2.1 Timing Adjustable | A | — | — | **Not implemented** |
| 2.2.2 Pause, Stop, Hide | A | `pause_stop_hide_auditor.py` | — | Strong |
| 2.3.1 Three Flashes | A | — | — | **Not implemented** |
| 2.4.1–2.4.4 | A | — | axe-core only | axe-covered |
| 2.4.5 Multiple Ways | AA | — | `multiple-ways.check.js` | Partial |
| 2.4.7 Focus Visible | AA | `policy_2_4_7` | `focus-visible.check.js` | Strong |
| 2.4.8 Location | AAA | — | `location.check.js` | Partial |
| 2.4.9 Link Purpose (Link Only) | AAA | — | `link-purpose.check.js` | Partial |
| 2.4.11 Focus Not Obscured (Min) | AA | rendered evaluator | — | Strong |
| 2.4.12 Focus Not Obscured (Enh) | AAA | rendered evaluator | — | Strong |
| 2.4.13 Focus Appearance | AAA | `policy_2_4_13` | `focus-appearance.check.js` | Partial |
| 2.5.2 Pointer Cancellation | A | — | `pointer-cancellation.check.js` | Partial |
| 2.5.3 Label in Name | A | `label_in_name_auditor.py` | — | Strong |
| 2.5.7 Dragging Movements | AA | — | `dragging-movements.check.js` | Partial |
| 2.5.8 Target Size (Minimum) | AA | `target_size_auditor.py` | — | Strong |
| 3.1.1 Language of Page | A | — | axe-core | axe-covered |
| 3.1.2 Language of Parts | AA | — | — | **Not implemented** |
| 3.1.6 Pronunciation | AAA | — | `pronunciation.check.js` | Partial |
| 3.2.1 On Focus | A | — | `on-focus.check.js` | Partial |
| 3.2.2 On Input | A | — | `on-input.check.js` | Partial |
| 3.2.3 Consistent Navigation | AA | — | — | **Not implemented** (single-page scope) |
| 3.2.4 Consistent Identification | AA | — | — | **Not implemented** (single-page scope) |
| 3.2.6 Consistent Help | A | — | `consistent-help.check.js` | Partial (single-page scope) |
| 3.3.1 Error Identification | A | `form_auditor.py` | — | Strong |
| 3.3.2 Labels or Instructions | A | `form_auditor.py` | — | Strong |
| 3.3.3 Error Suggestion | AA | — | `error-suggestion.check.js` | Partial |
| 3.3.4 Error Prevention (Legal/Financial) | AA | — | `error-prevention.check.js` | Partial |
| 3.3.7 Redundant Entry | A | — | `redundant-entry.check.js` | Partial |
| 3.3.8 Accessible Authentication (Min) | AA | — | `accessible-auth.check.js` | Partial |
| 4.1.1 Parsing | (obsolete in 2.2) | — | `html-parsing.check.js` | Strong |
| 4.1.2 Name, Role, Value | A | pipeline | axe-core | Strong |
| 4.1.3 Status Messages | AA | — | `status-messages.check.js` | Partial |

---

# Section 1 — Visual / Non-Text Rules (ka11y-python)

## 1.1.1 Non-text Content
**Files:** `ka11y-python/ka11y/accessibility/rules/non_text/alttext.py`, `ka11y/accessibility/pipeline/decisions/policies/policy_1_1_1.py`, `api/v1/combined/findings.py:413–431`.

### What it checks
Multi-stage pipeline: (1) DOM crawl → `ImageData`, (2) CNN classifier → `{informative, decorative, logo, icon, functional, complex, text}` label, (3) OCR → tokens, (4) policy matches alt text against classifier intent + OCR content + W3C WAI patterns (logo, icon, button).

### Technique coverage

| Technique | Type | Status | Notes |
|---|---|---|---|
| H37 `alt` on `<img>` | Sufficient | **Covered** | Missing `alt` → fail. |
| H67 Null `alt` on decorative | Sufficient | **Covered** | Strict: any non-empty alt on classifier-labelled "decorative" fails. |
| H2 Combining adjacent img + text | Sufficient | Missed — automatable | No detection of `<a><img><span>label</span></a>` double-announce pattern. |
| H36 `alt` on `<input type="image">` | Sufficient | Partial | Crawler captures inputs; policy path for 4.1.2 functional name only — no dedicated `<input type="image">` branch. |
| H53 `<object>` alternative | Sufficient | Missed — automatable | `<object>` and `<embed>` fallback content not traversed. |
| H86 Text alt for ASCII art | Sufficient | Missed — requires human judgment | — |
| ARIA6, ARIA10 `aria-label`/`aria-labelledby` on img | Sufficient | **Covered** | Uses computed accessible name. |
| G94 Short text alternative serves same purpose | Sufficient | Partial | OCR-based literal matching; fails on synonyms (e.g. alt "Look up" vs OCR "Search"). |
| G95 Short text alt provides brief description | Sufficient | Partial | No upper-bound length sanity (very long alts pass silently). |
| F3 CSS background used for meaningful image | Failure | Missed — automatable | No scan of `background-image` URLs for non-decorative intent. |
| F20 `alt=""` on informative | Failure | **Covered** | Classifier + OCR gate it. |
| F30 Filename / placeholder alt ("DSC_1234.jpg", "image") | Failure | **Covered** | `_EMPTY_OR_GENERIC` set. |
| F38 Decorative not marked with null alt | Failure | **Covered** | |
| F39 Empty `alt` on image conveying information | Failure | **Covered** | Classifier-gated. |
| F65 Missing alt, title, aria-label, aria-labelledby | Failure | **Covered** | |
| F67 Long description not functional | Failure | Missed — requires human judgment | — |
| F71 Emoji/symbol without text alt | Failure | Missed — automatable | Glyph-only text nodes (`<span>✉</span>`) are not checked. |
| F72 ASCII art without text alt | Failure | Missed — requires human judgment | — |

### Known limitations
1. **Acronym collision:** 3-char token floor in `_check_1_1_1_informative` causes false negatives for valid 2-letter tokens (e.g., "UI", "Go", "OK").
2. **Synonym blindness:** Literal OCR match. "Search" in image + alt "Look up" → false fail.
3. **Classifier dependency:** ML misclassification propagates. If logo is labelled `informative`, logo-keyword gate (`_check_1_1_1_logo`) is skipped and `brand name` passes.
4. **CSS background images:** Entire category untouched — `<div style="background-image: url(hero.jpg)">` with decorative/informative content is invisible.
5. **SVG `<title>`:** SVGs with inline `<title>` children are parsed inconsistently — accessible-name computation sometimes falls back to filename.

---

## 1.4.3 Contrast (Minimum) / 1.4.6 Contrast (Enhanced)
**Files:** `rules/non_text/contrast_analyser.py`, `pipeline/decisions/policies/policy_1_4_3.py`, `policy_1_4_6.py`, `text_detector/text_detector.py`, `api/v1/combined/findings.py:551–688`.

### What it checks
Computer-vision pipeline: render screenshot → EAST/CRAFT text detection → OCR + bbox → per-bbox Otsu binarization to separate fg/bg → convert to linear sRGB → relative luminance → `(L1+0.05)/(L2+0.05)` → threshold 4.5:1 / 3:1 (large) for 1.4.3; 7:1 / 4.5:1 for 1.4.6.

### Technique coverage

| Technique | Status | Notes |
|---|---|---|
| G18 4.5:1 contrast ratio | **Covered** | Core formula. |
| G145 3:1 contrast for large text | **Covered** | 18pt / 14pt-bold threshold applied. |
| G17 7:1 for 1.4.6 | **Covered** | Policy 1.4.6. |
| G148 No author-specified colors | Missed — requires human judgment | |
| G174 Alternative high-contrast version | Missed — automatable | No detection of theme-toggle link. |
| F24 Foreground w/o background (or vice versa) | Missed — automatable | Only measures rendered pixels; a bg-color rule with no color counterpart passes. |
| F83 Background image fails contrast | Partial | Handled implicitly via pixel rendering, but no warning when OCR bbox sits on low-variance gradient. |

### Known limitations
1. **Gradient failure:** Otsu assumes bimodal distribution; glassmorphism/vivid gradients yield failed segmentation (rule returns N/A rather than WARNING).
2. **Anti-aliasing halo:** Pixel-level analysis captures halo pixels; 10th/90th percentile mitigates but doesn't eliminate skew.
3. **High-DPI noise:** Retina screenshots add interpolation artefacts that shift ratios by ~0.1.
4. **Disabled-state exemption not honoured:** WCAG exempts disabled controls; code flags `:disabled` inputs with low contrast.
5. **Pseudo-content:** Text in `::before`/`::after` is rendered but its CSS color is not inspected directly — reliant on OCR even when CSSOM values are available.

---

## 1.4.5 Images of Text
**Files:** `ka11y-python/ka11y/api/v1/combined/findings.py:725–744`, `pipeline/decisions/policies/policy_1_4_5.py`, `ka11y-node/src/custom-checks/images-of-text.check.js`.

### What it checks
Defense-in-depth: (a) node heuristic scores `<img>` by `src` keywords, alt length (>5 words), punctuation — producing `looksLikeImageOfText`; (b) python pipeline re-verifies with OCR token count and classifier label.

### Technique coverage

| Technique | Status | Notes |
|---|---|---|
| C22 Use CSS to control text presentation | Partial | Flags candidates but cannot propose CSS replacements. |
| G140 Separate real-text + decorative-image alternative | Missed — requires human judgment | |
| C30 Use style switcher for customizable text | Missed — automatable | No toggle detection. |
| F71 Information via image text only | **Covered** | Via OCR-heavy detection. |

### Known limitations
1. **Logotype false positives:** "logo" vs "styled text image" boundary relies on classifier `is_logo` flag — hit-or-miss on wordmark logos.
2. **Incidental text:** Street sign in news photo flagged unless classifier marks image as `complex`/`informative`.
3. **CSS `background-image` blind spot:** Large hero text rendered via CSS `background-image` is completely missed in the node heuristic (src-keyword only).
4. **Language bias:** Heuristic scoring uses English/ASCII word counts; Japanese/Chinese text-heavy images score lower than intended.

---

## 1.4.11 Non-text Contrast
**Files:** `policy_1_4_11.py`, `api/v1/combined/findings.py:788–826`.

### What it checks
Analyzes rendered boundaries of UI components (button border, focus ring) using segmented contrast. Flags < 3:1.

### Technique coverage

| Technique | Status | Notes |
|---|---|---|
| G195 Author-provided 3:1 contrast | Partial | Only works when boundary is visually present. |
| G207 3:1 between active state UI and surroundings | Partial | Active/hover states not simulated. |
| G209 Provide sufficient contrast at default | **Covered** | Default-state only. |
| F78 Focus indicator w/o 3:1 | Partial | Handled via 2.4.7/2.4.13 branch. |
| F79 No visible focus indicator | Covered | Policy 2.4.7. |

### Known limitations
1. **Invisible boundaries:** Buttons styled only via background fill with no border are treated as having no UI boundary; no pass/fail decision emitted (returns N/A).
2. **Graphs/charts (G207 exempt):** No detection of data-visualization exemptions; decorative chart borders may flag.
3. **State-dependent contrast:** Hover/focus/active state contrast not measured (requires rendered-state simulation).

---

## 1.4.4 Resize Text / 1.4.10 Reflow / 1.4.12 Text Spacing / 1.4.13 Hover-Focus Content
**Files:** `ka11y-python/ka11y/accessibility/rendered/evaluators/resize_text.py`, `reflow.py`, `text_spacing.py`, `hover_focus_content.py`.

### What it checks
Each rule runs a scenario (viewport resize, font-size 200%, 1.4.12 CSS overrides, 320px reflow, hover scan) and captures a rendered snapshot. Diffs bounding boxes pre/post to detect clipping / horizontal-scroll / dismissible popups.

### Technique coverage (per SC)

**1.4.4:** G142 (use ems/percentages) — Partial. C12, C13, C14 (relative units) — not inspected at stylesheet level. F69 clipped text at 200% — **Covered**. F80 at fixed width — Partial.

**1.4.10:** C32/C34 (flexbox/grid responsive) — Partial. F102 fixed-size container — **Covered**. G206 overflow permitted — Partial.

**1.4.12:** C36/C37 (user-overrideable spacing) — **Covered**. F104 clipped at increased spacing — **Covered**.

**1.4.13:** G*: dismissible — Partial (esc-key scan). hoverable — Partial. persistent — Partial. F95 pointer-remove-triggers-hide — **Covered**.

### Known limitations
1. **Clipping detection is geometric only:** `offsetWidth > scrollWidth` is the proxy; padding-hidden text without overflow is missed.
2. **No pre-change baseline sometimes:** `hover_scan` evaluator captures only popup-triggered state, not the dismissal lifecycle — popup stuck open after Escape is not flagged.
3. **Text-spacing override scoped to `<html>`:** Some stylesheets use `!important` on descendants that defeat the override; no stylesheet-level diff.
4. **Reflow false positives on intentionally horizontally-scrolling regions** (data tables, code blocks) — no whitelist.
5. **Animation timing:** 1.4.13 uses a 300 ms settle; short-lived tooltips are captured mid-transition.

---

## 1.3.3 Sensory Characteristics
**File:** `rules/non_text/sensory_auditor.py`, `crawler/sensory_crawler.py`.

### What it checks
spaCy NLP (EN: `en_core_web_sm`, JA: `ja_core_news_sm`) detects instructional sentences; `_remaining_label_words` strips purpose phrases, sensory words, generic UI nouns, stop-words; if any non-sensory label remains → pass.

### Technique coverage

| Technique | Status | Notes |
|---|---|---|
| G96 Non-sensory identifier in addition | **Covered** |
| F14 Identify content only by shape/location | **Covered** for English; Partial for Japanese (CJK word-boundary issues). |
| F26 Using graphical symbol alone | Missed — requires visual grounding. |

### Known limitations
1. **Vocabulary exhaustion:** `SENSORY_WORDS` is finite. Novel terms ("translucent", "neon") escape detection.
2. **CJK word boundaries:** Japanese path uses fallback CJK content-char stripping; leftover structural text can yield false pass.
3. **Semantic disconnect:** Validates phrasing, not visual reality. "Click the red button" passes if *some* non-sensory label remains, even when the real button has no text.

---

## 2.2.2 Pause, Stop, Hide
**File:** `rules/timing/pause_stop_hide_auditor.py`, `crawler/moving_content_crawler.py`.

### What it checks
Playwright `getAnimations()` for keyframe + WAAPI; GIF frame count via Pillow; autoplay detection for Bootstrap/Slick/Swiper/Owl/Flickity/Glide/Splide with library-state introspection (e.g. `el.swiper.autoplay.running`); nearby-pause-button regex 2 levels up.

### Technique coverage

| Technique | Status | Notes |
|---|---|---|
| G4 Content pauses and user can resume | Partial | Only detects existence of button, not state-change. |
| G11 Moving text < 5 sec | **Covered** | Infinite / >5 s threshold. |
| G152 Animated GIF stops after 5 s | **Covered** via frame-count → infinite loop. |
| G186 Pause button | Partial | 2-level DOM ancestor scan; deeper nesting missed. |
| G191 Pause/stop/hide button with text | Partial | Regex includes "pause"/"stop"/"一時停止"; not exhaustive. |
| F16 Scrolling with no pause | **Covered** (marquee). |
| F50 Script that cannot be paused | Missed — automatable | `setInterval`/`requestAnimationFrame` hand-rolled animations without library markers escape detection. |

### Known limitations
1. **State verification gap:** Clicking the pause button is not simulated; "fake" pause buttons pass.
2. **Custom carousels:** Non-library setInterval/rAF animations are invisible.
3. **Pause button depth limit:** Fixed 2-level ancestor scan; deeper component hierarchies miss buttons.

---

## 2.5.3 Label in Name
**File:** `rules/input_modalities/label_in_name_auditor.py`.

### What it checks
For each interactive element, compares NFC-normalized + casefolded visible label text vs computed accessible name. Failure if visible label non-empty and accessible name does not contain it.

### Technique coverage

| Technique | Status | Notes |
|---|---|---|
| G208 Include visible label text in accessible name | **Covered** |
| G211 Match visible label to accessible name | **Covered** |
| F96 Accessible name does not contain visible label | **Covered** |

### Known limitations
1. **Icon-only controls:** No visible label → no violation possible (correct by WCAG, but hides misnamed icons).
2. **Whitespace vs punctuation:** "Sign-up" vs "Sign up" casefolds match; but "Sign up!" vs "Sign up" substring succeeds — a semi-false pass if accessible name lacks exclamation.
3. **Multi-line labels:** Collapses newlines → edge case where visible label has line break but accessible-name substring check passes (usually desired).
4. **Shadow DOM:** Not traversed; controls inside closed shadow roots miss.

---

## 2.5.8 Target Size (Minimum)
**File:** `rules/input_modalities/target_size_auditor.py`, `crawler/target_size_crawler.py`.

### What it checks
Rendered `getBoundingClientRect` vs 24×24. Exceptions: inline (`display: inline` + paragraph parent), UA-controlled (`appearance` unchanged), offset (theoretical 24×24 around centre does not intersect neighbouring targets).

### Technique coverage

| Technique | Status | Notes |
|---|---|---|
| G219 Ensure 24×24 | **Covered** |
| Inline exception | **Covered** | `display: inline` + paragraph parent check. |
| UA-controlled exception | **Covered** | `appearance: none` signals override. |
| Offset exception | **Covered** | Theoretical 24-box intersection. |
| Essential exception | Missed — requires human judgment | |
| Equivalent exception | Missed — requires human judgment | |

### Known limitations
1. **Z-index stacking:** Transparent overlaid elements may trigger false offset intersection.
2. **Padding vs target area confusion:** Developers style small visual + large padding; handled via `getBoundingClientRect`, but test messaging may confuse users.
3. **Viewport-coupled:** Runs at 1440 px; mobile target-size issues unmeasured unless crawler reconfigured.
4. **Iframe contents:** Crawler does not descend into cross-origin iframes.

---

## 3.3.1 Error Identification / 3.3.2 Labels or Instructions
**File:** `rules/forms/form_auditor.py`, `crawler/forms_crawler.py`.

### What it checks
For each `<input>` / `<select>` / `<textarea>`: (3.3.1) required + aria-describedby + role=alert/aria-live; (3.3.2) accessible name (label/aria-label/aria-labelledby) + autocomplete for email/tel/password.

### Technique coverage

| Technique | Status | Notes |
|---|---|---|
| G83/G85/G84 Text description of error | Partial | Only detects container presence, not error text quality. |
| G139 Text cue adjacent | Missed — automatable | No positional proximity check. |
| ARIA19 Programmatic error announcement | **Covered** |
| H44 `<label>` associated with control | **Covered** |
| H65 `title` for unlabelled control | Partial | `title` alone is discouraged; no warning. |
| H90 `<legend>` for `<fieldset>` | Missed — automatable | `<fieldset>` grouping not audited. |
| F82 Visual grouping without programmatic | Missed — automatable | |

### Known limitations
1. **Client-side validation triggering:** Does not submit forms; errors that appear only after submit are invisible.
2. **CAPTCHA instructions:** Fields without labels but within a CAPTCHA exemption are still flagged.
3. **Combobox pattern:** Custom ARIA comboboxes may have the accessible-name lookup misfire when `aria-labelledby` references a hidden node.
4. **Fieldset/legend:** Grouping-level labels unchecked.

---

## 2.4.7 Focus Visible / 2.4.13 Focus Appearance (python side)
**Files:** `pipeline/decisions/policies/policy_2_4_7.py`, `policy_2_4_13.py`, `text_detector`, rendered focus_scan scenario.

### What it checks
2.4.7: tab through focusable elements, compare before/after outline/box-shadow; if delta under threshold and no ring → fail.
2.4.13: rendered focus ring thickness + contrast against adjacent colour; area ≥ perimeter×2 OR encloses; ≥3:1 contrast.

### Technique coverage

| Technique | Status | Notes |
|---|---|---|
| G149 UA-provided focus indication | Partial | `:focus-visible` inheritance inconsistent. |
| G165/G195 Author focus indicator | **Covered** |
| C15 `:focus` styling | **Covered** |
| F55 Remove default focus w/o replacement | **Covered** | `outline:0` + no alternative detected. |
| F78 Focus indicator w/o 3:1 | Partial for 2.4.13 |

### Known limitations
1. **Fixed 100-step tab limit** in focus_scan; very long forms miss elements.
2. **Custom-drawn focus** (canvas/SVG) cannot be measured from DOM style.
3. **Colour-only focus cue** (no thickness change) — measured via contrast, but anti-aliasing noise creates grey-zone passes.

---

# Section 2 — Node Custom Checks (ka11y-node)

## 1.2.1 Audio/Video-only (Prerecorded) — `audio-transcript.check.js`
**Logic:** Finds `<audio>` elements lacking `<track>` alternatives; searches for a transcript link within a `figure/article/section/[role=region]` ancestor using a locale-aware keyword list (`config/universal.yml → audio_transcript.transcript_keywords`). Also accepts `<figcaption>`, `<details>` with transcript text, and `aria-describedby` fallbacks.

### Technique coverage

| Technique | Type | Status | Notes |
|---|---|---|---|
| G158 Transcript for audio-only | Sufficient | Partial | Detects presence; doesn't verify content equivalence. |
| G159 Alternative for video-only | Sufficient | Partial | Same as above. |
| H96 `<track>` element | Sufficient | **Covered** | Track `src` is HEAD-fetched to confirm reachability. |
| G166 Synchronized alternatives | Sufficient | Missed — belongs to 1.2.2 / 1.2.3 | Now handled by the new `audio-description.check.js`. |
| F30 Text alternative is filename | Failure | Missed — automatable | Filename-only transcript links should be flagged. |

### Known limitations
1. **Cross-page transcripts** — only same-page links are checked; PDF/`/transcripts/` destinations are not fetched or verified.
2. **Keyword-only match** — mis-triggers on non-transcript links containing "text" / "subtitles" in other contexts.
3. **Content equivalence** — transcript text isn't compared against audio content.

---

## 1.3.2 Meaningful Sequence — `meaningful-sequence.check.js`
**Logic:** Scans up to 2000 flex/grid containers for: `flex-direction: *-reverse`, explicit `grid-column/row-start`, mixed floats, non-default `order` values on children.

**Technique coverage:** C6 CSS to position content — Partial (only flex/grid). C27 DOM order matches visual — Partial. F1 reorder via float — **Covered**. F32 reverse direction — **Covered**. F33 white-space-based layout — Missed. F34 white-space between characters — Missed. F49 table for layout — Missed.

**Limitations:**
1. **Container limit (2000):** Very dense pages skip later containers.
2. **Absolute-positioned reorder:** `position: absolute` with explicit `top/left` reordering is invisible.
3. **Screen-reader DOM order check is structural only** — semantic correctness not verified.

---

## 1.3.4 Orientation — `orientation.check.js`
**Logic:** Looks for CSS `@media (orientation:*)` rules locking to one orientation, `screen.orientation.lock`, meta-viewport `orientation=`, and rotate-overlay prompts.

**Technique coverage:** G214 Support orientation — **Covered**. F97 Locking orientation — **Covered**. F100 Restricting view based on orientation — Partial (only static CSS, not JS-triggered).

**Limitations:**
1. **JS orientation lock:** Detects API call only in inline/static `<script>` content; imported modules miss.
2. **Essential exemption:** Not detected (bank check-deposit, virtual piano); false positives.

---

## 1.4.1 Use of Color — `use-of-color.check.js`
**Logic:** Finds links inside `p/li/td/th/blockquote/article>p/dd/section>p/svg`. For each, computes ancestor baseline style and checks at least one non-colour cue: text-decoration, border-bottom, outline, font-style, background-color, ≥100-unit font-weight delta.

### Technique coverage

| Technique | Type | Status | Notes |
|---|---|---|---|
| G14 Information not by colour alone | Sufficient | Partial | Links in prose are covered; non-link colour-coded information is not. |
| G182 Additional non-colour cue | Sufficient | **Covered** | Six different cue categories inspected. |
| G205 Text colour + additional cue | Sufficient | Partial | Only inline-link block containers are scanned. |
| C15 Using CSS to change the presentation | Sufficient | **Covered** |
| F13 Information by colour alone (charts/forms/maps) | Failure | Missed — automatable | Not yet extended to chart legends or form field colour-coding. |
| F73 Link distinguished by colour only | Failure | **Covered** | Core path. |
| F81 Required fields by colour only | Failure | Missed — automatable | Despite 3.3.2 coverage, no cross-check with colour usage. |

### Known limitations
1. **Strict container scope** — misses nested block containers that don't match the fixed selector list.
2. **Hover-state blind** — static DOM only; hover-underline-only patterns pass falsely.
3. **100-unit font-weight threshold** — imperceptible in thin typefaces.
4. **No form / chart / legend coverage** — rule is limited to prose links.

---

## 2.1.2 No Keyboard Trap — `keyboard-trap.check.js`
**Logic:** (1) Forward Tab up to 200 times, track last 4 focused keys via `CYCLE_WINDOW`, flag stuck / A-B-A-B cycles. (2) Shift+Tab reverse traversal with the same heuristic. (3) Escape verification after each suspected trap. (4) Arrow-key-trap scan for `role=tree/grid/listbox/menu/tablist/radiogroup`. (5) Same-origin iframe Tab trap. (6) **New (2026-04-23):** focuses every visible `dialog[open]` / `[role="dialog"]` / `[aria-modal="true"]`, presses Escape, fails if focus remains inside (F85).

### Technique coverage

| Technique | Type | Status | Notes |
|---|---|---|---|
| G21 No keyboard trap | Sufficient | **Covered** | Forward + reverse Tab cycles. |
| F10 Two non-exiting controls | Failure | **Covered** | Two-element cycle pattern. |
| F85 Modal traps focus without close | Failure | **Covered** | Added in this sprint. |
| F58 Script that blocks keyboard events | Failure | Missed — automatable | No `preventDefault()` inspection on key handlers. |
| F60 Pop-up that cannot be closed | Failure | Partial | Covered via F85 for modals; non-modal pop-ups not tested. |

### Known limitations
1. **200-tab ceiling** — very long pages with >200 focusable elements may miss a trap beyond the ceiling.
2. **Stable-key fallback** — when an element lacks `id` / `name`, the key is derived from DOM position; layout shifts between tabs can produce noisy cycle detections.
3. **Escape-only dismissal** — pop-ups that require a specific close button but not Escape are detected only when they are modal (role=dialog).
4. **Scripted keypress suppression** (F58) — not inspected.

---

## 2.1.4 Character Key Shortcuts — `character-key-shortcuts.check.js`
**Logic:** Scans `accesskey` attributes and inline `onkeypress`/`onkeydown`/`onkeyup` for single printable-character handlers without a guard for modifier key, non-input target, or disable-toggle UI.

**Technique coverage:** G217 Provide mechanism to remap / G90/G93 modifier requirement — Partial. F99 single key shortcut without remap — Partial.

**Limitations:**
1. **Event handlers in bundled JS** not scanned (only inline + `accesskey`).
2. **React/Vue synthetic handlers** invisible.
3. **Remap UI detection heuristic:** Based on keyword matching for a nearby "shortcut settings" element.

---

## 2.4.5 Multiple Ways — `multiple-ways.check.js`
**Logic:** Counts presence of at least 2 of: site search, sitemap link, nav with ≥3 links, breadcrumb.

**Technique coverage:** G63 Sitemap — Partial. G64 ToC — Missed. G125 Related-pages links — Missed. G126 List of links to all pages — Missed. G161 Search — **Covered**. G185 Link to sitemap — **Covered**.

**Limitations:**
1. **Single-page scope:** True "multiple ways" is a site-level property; single-URL evaluation cannot confirm.
2. **Breadcrumb detection:** Relies on `aria-label="breadcrumb"` + schema.org markup; unconventional patterns missed.

---

## 2.4.7 Focus Visible — `focus-visible.check.js` (interactive)
**Logic:** Runs in interactive mode; tabs through focusable elements; for each, snapshots before/after CSSOM (outline, box-shadow, border) and diff.

**Technique coverage:** Same as Python side (G149, G165, G195, C15, F55, F78).

**Limitations:**
1. **Delta threshold tuned per-browser** — Firefox default outline differs from Chrome.
2. **SVG focus rings** (via `focusRing` proposal) not measured.
3. **Missed elements with `:focus-visible` differing from `:focus`:** the test simulates plain focus, not keyboard-only navigation.

---

## 2.4.8 Location — `location.check.js`
**Logic:** Presence of breadcrumb nav, `<title>`-reflecting-page-position, or aria-current="page".

**Technique coverage:** G65 Breadcrumb — **Covered**. G63 Sitemap — Partial. G127 ToC — Missed. G128 Indication of current location — **Covered**.

**Limitations:**
1. **AAA-only criterion** — often intentionally skipped.
2. **Semantic page-title parsing** is weak; won't detect "Home > Products > X" in document title.

---

## 2.4.9 Link Purpose (Link Only) — `link-purpose.check.js`
**Logic:** Computes accessible name of every link; flags generic names ("click here", "read more") when no aria-describedby or context.

**Technique coverage:** G53 Identify link by accessible name — **Covered**. G91 Link text describes purpose — Partial. H30 Text content of link describes purpose — **Covered**. H33 title supplements link text — Partial. F84 "click here" pattern — **Covered**.

**Limitations:**
1. **Keyword list finite** — novel generic phrases ("discover now", "learn more") depend on seed list.
2. **Localisation:** English + Japanese mainly; other locales may have gaps.

---

## 2.4.13 Focus Appearance — `focus-appearance.check.js` (interactive)
**Logic:** Snapshots each focusable element before/after `focus()`. Requires outline-width ≥ 2 px OR enclosure; contrast ≥ 3:1.

**Technique coverage:** G195 Author focus indicator — **Covered**. SCR31 focus change via script — Missed. F78 — Partial.

**Limitations:**
1. **Area requirement ≥ perimeter×2 CSS px** is approximated by MIN_OUTLINE_WIDTH=2 — not a strict geometric check.
2. **Contrast against the adjacent colour, not against the whole component** — imperfect when focus ring sits partly on gradient.
3. **Time-budget ceiling:** Stops after 2000 elements.

---

## 2.5.2 Pointer Cancellation — `pointer-cancellation.check.js`
**Logic:** Finds elements with `onpointerdown`/`onmousedown` that trigger navigation or submit without matching up-event; checks for `pointercancel` or `preventDefault` patterns.

**Technique coverage:** G210 Up-event only — Partial. F101 Down-event trigger — **Covered**. F102 No cancel mechanism — Partial.

**Limitations:**
1. **Inline-handler bias:** React/Vue synthetic handlers invisible.
2. **Draggable essential exemption:** Not detected — drag-and-drop widgets falsely flagged.
3. **Abort semantics not tested** — only pattern-matches source code.

---

## 2.5.7 Dragging Movements — `dragging-movements.check.js`
**Logic:** Finds `draggable="true"` elements, HTML5 drag listeners, Swiper/Slick/native range; flags when no alternative single-pointer action (buttons, keyboard) present in vicinity.

**Technique coverage:** G219 Single-pointer alternative — Partial. F105 Dragging without alternative — **Covered**.

**Limitations:**
1. **Custom drag implementations** using `pointermove` + transform: matrix are library-detected only.
2. **Essential exemption** (signature pads, map pan) not distinguished.
3. **Alternative detection heuristic** based on nearby `<button>` keywords ("next", "previous").

---

## 3.1.6 Pronunciation — `pronunciation.check.js`
**Logic:** Scans `<ruby>`, `<bdi>` with `lang`, `<span lang="…">` containing IPA, dictionary-link adjacency for ambiguous words.

**Technique coverage:** G62 Glossary — Partial. G120 Pronunciation near ambiguous word — Partial. H62 `<ruby>` — **Covered**. 

**Limitations:**
1. **AAA rule** — rarely required.
2. **Ambiguity detection:** Requires a hand-crafted list of homographs; incomplete.

---

## 3.2.1 On Focus / 3.2.2 On Input — `on-focus.check.js`, `on-input.check.js`
**Logic:** Detects `onfocus` handlers triggering `window.open`/`location.href`/`submit()`; detects `onchange` on `<select>` or `<input type="checkbox"/radio>` triggering navigation or submit.

**Technique coverage:** G107 Not submitting on input — Partial. F36 Submit on select — **Covered**. F37 Submit on radio — **Covered**.

**Limitations:**
1. **Inline handlers only** — framework event delegation bypasses.
2. **Window.open inside nested function calls** not detected.
3. **No simulation** — cannot confirm behaviour, only pattern-match.

---

## 3.2.6 Consistent Help — `consistent-help.check.js`
**Logic:** Finds help mechanism (contact, FAQ, chat, support link, phone) and records its position on the page (header/footer/sidebar/inline).

**Technique coverage:** G220 Consistent help location — Partial. Criterion is cross-page; single-page scope yields only a "no help found" vs "help at location X" status.

**Limitations:**
1. **Single-page scope:** Cannot verify "consistent across pages" — needs crawl comparison.
2. **Keyword taxonomy:** Localised but not exhaustive.

---

## 3.3.3 Error Suggestion — `error-suggestion.check.js`
**Logic:** For each error container (aria-invalid / role=alert / `.error`), checks for presence of suggestion text (has verb + target field reference; keywords "must", "should", "cannot be empty").

**Technique coverage:** G83/G84/G85 Suggestions for input errors — Partial. G177 Suggesting valid text — Partial.

**Limitations:**
1. **Suggestion-quality heuristic:** keyword-based; fails for internationalized or novel error copy.
2. **No submission** — errors appearing only after form submit are missed.

---

## 3.3.4 Error Prevention (Legal/Financial) — `error-prevention.check.js`
**Logic:** Classify forms as financial/legal/destructive via keyword scan of submit button + headings + form meta. Then require at least one of: confirm step, review page, irreversibility warning.

**Technique coverage:** G98 Reversible — Partial. G99 Checked — Partial. G155 Confirmation — Partial. G164 Undo window — Missed.

**Limitations:**
1. **Keyword classification:** False positives ("privacy policy" in footer) and false negatives (crypto/web3 transactions).
2. **Multi-step wizard detection:** Heuristic step counter may miscount.
3. **No real submission** — cannot verify reversibility.

---

## 3.3.7 Redundant Entry — `redundant-entry.check.js`
**Logic:** Groups related forms/inputs via name/id matching; across repeated steps, detects identical fields without `autocomplete` or pre-filled value.

**Technique coverage:** G218 Auto-fill from previous step — Partial.

**Limitations:**
1. **Session scope:** Single-page evaluation; cannot observe wizard step-to-step state.
2. **Security exemption:** Re-entry for password confirmation is correct but may be flagged.

---

## 3.3.8 Accessible Authentication (Minimum) — `accessible-auth.check.js`
**Logic:** Finds auth forms (password input or login keywords). Flags presence of CAPTCHA image, reCAPTCHA iframe, or cognitive-test keywords without an alternative (WebAuthn, magic link, OTP).

**Technique coverage:** G218 Alternative authentication — Partial. F109 CAPTCHA as only auth — Partial.

**Limitations:**
1. **CAPTCHA provider detection** is heuristic; niche providers miss.
2. **Alternative-method detection** requires explicit button text.
3. **Invisible reCAPTCHA v3** cannot be flagged (no visible UI).

---

## 4.1.1 Parsing — `html-parsing.check.js`
**Logic:** Counts duplicate `id=` attributes; flags malformed nesting (`<a>` inside `<a>`, `<button>` inside `<button>`).

**Technique coverage:** H93 Unique id — **Covered**. H94 No duplicate attributes — Partial.

**Limitations:**
1. **WCAG 2.2 deprecation:** SC 4.1.1 was dropped in WCAG 2.2; kept for back-compat.
2. **Parse errors beyond id:** No validation of unclosed tags (browsers auto-correct before DOM inspection).

---

## 4.1.3 Status Messages — `status-messages.check.js`
**Logic:** Enumerates `role="status"` / `role="alert"` / `aria-live="polite"|"assertive"` regions, counts them, and inspects form inline-validation containers (`.error`, `[aria-invalid=true]`) for missing live-region association. Emits separate rule IDs for `custom-status-messages-atomic` (missing `aria-atomic`) and `custom-status-messages-inline-validation`.

### Technique coverage

| Technique | Type | Status | Notes |
|---|---|---|---|
| ARIA19 `aria-live` | Sufficient | **Covered** | Counts polite + assertive. |
| ARIA22 `role="status"` | Sufficient | **Covered** |
| ARIA23 `role="log"` | Sufficient | Partial | Role is detected but not validated against 4.1.3 applicability. |
| G199 Programmatically determined status | Sufficient | Partial | Presence-based; not dynamic-announcement verified. |
| F114 Text that is a status but cannot be programmatically determined | Failure | Missed — automatable | Toast notification containers without any ARIA are not heuristically detected. |

### Known limitations
1. **Snapshot-only** — the page is scanned once. Cannot verify that a message actually becomes announced when an event happens.
2. **`aria-atomic` / `aria-relevant`** — only `aria-atomic` emit is checked; `aria-relevant` semantics (additions vs. removals vs. text) are ignored.
3. **Toast libraries** — container classes from react-toastify, sonner, react-hot-toast are not matched heuristically.

---

# Section 2b — Node Checks Added in 2026-04-23 Sprint

## 1.2.2 Captions (Prerecorded) — `captions-prerecorded.check.js`
**Logic:** For every visible `<video>`, inspect `<track kind="captions"|"subtitles">` children with a non-empty `srclang`. Skip muted / live-hint videos. Additionally enumerate cross-origin embeds (`youtube.com/embed`, `player.vimeo.com`, `wistia`) and emit INCOMPLETE because CC state isn't inspectable across origins.

### Technique coverage

| Technique | Type | Status | Notes |
|---|---|---|---|
| G93 Open / closed captions | Sufficient | Partial | Detects presence of a `<track>` + `srclang`; doesn't verify content. |
| H95 `<track>` element with captions kind | Sufficient | **Covered** |
| G87 Closed captions | Sufficient | Partial | Third-party players require manual review. |
| F75 Video without captions | Failure | **Covered** | Flags missing captions on first-party `<video>`. |

### Known limitations
1. **Cross-origin embeds** — YouTube / Vimeo caption tracks are controlled by the hosting platform and aren't DOM-observable; always emitted as INCOMPLETE.
2. **Live / muted detection** is heuristic (attribute + src substring / `.muted`); misclassification possible.

---

## 1.2.3 Audio Description — `audio-description.check.js`
**Logic:** For every `<video>`, check for a `<track kind="descriptions">` with `srclang`, a sibling `<audio>` / `<source>` whose `data-kind` / `title` contains "description", or a container transcript/details link matching the multi-locale `ALT_KEYWORDS` regex (EN + JA).

### Technique coverage

| Technique | Type | Status | Notes |
|---|---|---|---|
| G78 Second user-selectable audio track | Sufficient | Partial | Element-sibling detection; no switch-control verification. |
| G173 Audio-described version of video | Sufficient | Partial | |
| H96 `<track>` element with descriptions kind | Sufficient | **Covered** |
| G8 Full text alternative | Sufficient | Partial | Nearby `<details>` / transcript link recognised. |

### Known limitations
1. **Audio description quality** not verified — only track presence.
2. **Dubbed extended audio description tracks** (for 1.2.7) aren't distinguished from 1.2.3.

---

## 1.4.2 Audio Control — `audio-control.check.js`
**Logic:** Enumerates `<audio>` / `<video>` elements with `autoplay` (attribute or `data-autoplay`). Skip when `muted`. If duration is unknown or > 3 s AND there is neither a `controls` attribute nor an external pause/stop/mute/volume button in the figure/article/section/`[role=region]` container → FAIL.

### Technique coverage

| Technique | Type | Status | Notes |
|---|---|---|---|
| G60 Playing a sound that turns off automatically within 3 s | Sufficient | Partial | Requires `data-duration` or `.duration`; NaN-duration treated as > 3 s. |
| G170 Providing a control near the beginning | Sufficient | **Covered** | Native `controls` or external button with pause/stop/mute/volume text. |
| G171 Playing sound only on request | Sufficient | Partial | Inferred via autoplay/muted attrs. |
| F23 Autoplay > 3 s without controls | Failure | **Covered** |

### Known limitations
1. **Web Audio API** sounds (scripted playback outside `<audio>`/`<video>`) are invisible.
2. **Background music in iframes** — cross-origin media cannot be introspected.
3. **Duration detection** — if `duration` hasn't loaded and no `data-duration` hint exists, the check pessimistically assumes > 3 s. May false-flag very short SFX.

---

## 1.1.1 / 1.4.5 CSS Background Images — `background-image-content.check.js`
**Logic:** Scans every DOM element's `computedStyle.backgroundImage`. Skips gradients, `data:` URIs, URLs matching decorative-hint patterns (`gradient`/`pattern`/`noise`/`texture`/`overlay`/`mask`/`fade`/`blur`/`dot`/`divider`), and elements < 24×24 px. Emits two rules: the primary 1.1.1 INCOMPLETE for non-decorative background images on elements without an accessible name; a secondary `-text-image` rule targeting 1.4.5 when the URL contains text-hint keywords (`banner`/`headline`/`hero`/`cta`/`promo`/`callout`/`masthead`/`heading`/`text`).

### Technique coverage

| Technique | Type | SC | Status | Notes |
|---|---|---|---|---|
| F3 CSS background used for meaningful image | Failure | 1.1.1 | **Covered (incomplete)** | New — previously invisible to the pipeline. |
| C22 Use CSS to control text presentation | Sufficient | 1.4.5 | Partial | Keyword-based candidate detection. |
| G140 Separate text and decorative image | Sufficient | 1.4.5 | Missed — judgment |

### Known limitations
1. **Intent classification is URL-keyword based** — a genuine decorative image with "banner" in its filename will raise a false positive.
2. **Background size / position** not interpreted — an image cropped by `background-position` to a non-text region may still be flagged.
3. **Inline `<style>` vs stylesheet origin** not distinguished — can't tell whether the background is author-set or injected by a third-party script.

---

# Section 3 — Systemic Pipeline Issues

## 3.1 Silent image-capture failures
**Area:** `ka11y-python/ka11y/crawler/crawler.py`, `_safe_screenshot`, `download_image`, API response formatters.

### Symptoms
- Frontend renders broken-image icons when crawler fails to capture.
- No warnings surfaced to user — failures are silently swallowed.
- OCR/CV rules skip silently on empty images and mark the underlying SC as "N/A" — indistinguishable from a genuine clean pass.

### Root causes
1. `_safe_screenshot` and `download_image` swallow exceptions (CORS, timeout, 504) to keep the crawl alive.
2. Combined-findings JSON has no `failed_to_capture` flag; empty `screenshot_path` flows to the UI.
3. Canvas/SVG elements with external font deps often snapshot mid-paint; partial PNGs are persisted silently.

### Fix recommendations
- Introduce a `capture_status: ok|timeout|cors|network|dom_missing` enum per image and propagate to findings JSON.
- In the formatter, downgrade rules that required a capture but got `capture_status != ok` from PASS/N-A to INCOMPLETE with reason.
- Add user-visible banner at report top when ≥N images failed capture.

---

## 3.2 Cross-service finding duplication
- Both `axeResultMapper.js` and Python pipeline emit findings for shared SCs (1.1.1, 2.4.7, 2.5.3, 4.1.2).
- Runner dedup key is `(wcag_sc, status, element_signature)` — when the element signature differs between axe and Python (XPath vs selector), the same violation shows up twice.

**Fix:** harmonise element signatures at the formatter level.

---

## 3.3 Language-detection drift
- Sensory auditor and several node checks use inline `lang` attribute detection + CJK heuristic.
- When `<html lang="en">` but the actual text is Japanese (common on mixed-language microsites), the wrong spaCy model is used — sensory check underperforms.

**Fix:** per-element language detection via a lightweight `fasttext-langid` rather than DOM `lang`.

---

## 3.4 Browser settle timing is per-rule
- `SETTLE_MS = 60/80/300` scattered across checks with no central budget.
- On low-end CI runners, settle elapses before React hydration finishes; tests flake.

**Fix:** centralise in `shared-config.yaml` under `timing.settle_ms_profile: { fast|standard|slow }`.

---

## 3.5 Japanese Language Compatibility

**Scope:** All modules that perform NLP, keyword matching, or text analysis — `sensory_auditor.py`, `link-purpose.check.js`, `multiple-ways.check.js`, `consistent-help.check.js`, `error-suggestion.check.js`, `error-prevention.check.js`, `pronunciation.check.js`, `i18n/loader.py`.

### Current Japanese coverage status

| Module | JA Support | Quality |
|---|---|---|
| `sensory_auditor.py` (1.3.3) | `ja_core_news_sm` spaCy model + CJK char stripping | Weak |
| `link-purpose.check.js` (2.4.9) | Static JA keyword list (`"こちら"`, `"詳細"`, etc.) | Partial |
| `multiple-ways.check.js` (2.4.5) | JA breadcrumb / nav keyword detection | Partial |
| `consistent-help.check.js` (3.2.6) | JA help-link keywords (`"お問い合わせ"`, etc.) | Partial |
| `error-suggestion.check.js` (3.3.3) | JA suggestion keyword patterns | Partial |
| `error-prevention.check.js` (3.3.4) | JA financial / legal keyword patterns | Partial |
| `pronunciation.check.js` (3.1.6) | `<ruby>` detection + CJK character density | Strong |
| `i18n/loader.py` | Locale overlay for finding text fields | Strong |
| OCR (PaddleOCR / EasyOCR) | JA character detection when `lang=ja` is set | Partial |

### Root causes of incomplete Japanese coverage

1. **CJK word-boundary problem (critical).** Japanese text has no spaces between words. spaCy's `ja_core_news_sm` depends on a SudachiPy-derived dictionary tokenizer that is both smaller and less accurate than its English counterpart. The sensory auditor's `_remaining_label_words` method strips words by set membership, which requires correct tokenization — incorrect token splits cause structural text to survive the filter, yielding false passes for SC 1.3.3.

2. **`lang` attribute drift.** Language routing is driven by `<html lang="...">`. When `lang="en"` but the page contains Japanese body text (common on mixed-language corporate sites), the English spaCy pipeline loads and processes JA characters as unknown tokens. The per-element `lang` attribute override is respected by DOM crawlers but is not propagated to the NLP layer.

3. **`SENSORY_WORDS` vocabulary is English-primary.** The sensory auditor's word sets (`SENSORY_WORDS`, `GENERIC_UI_NOUNS`, `PURPOSE_WORDS`, `STOP_WORDS`) are curated for English. The JA fallback path strips CJK content characters with a regex, but residual structural text — particles (は, が, を), postpositions, sentence-final particles — is not filtered by POS tag, causing false passes or false fails depending on sentence structure.

4. **OCR gaps for Japanese text.** PaddleOCR handles Japanese reasonably when `lang=ja` is configured. EasyOCR's JA model struggles with:
   - Vertical text (縦組み / tategumi) — OCR reads left-to-right, columns are merged.
   - Mixed kanji + kana + ASCII — common on Japanese web; model confidence drops.
   - Small fonts below 12 pt — misread rate increases substantially.
   - Half-width katakana (`ｶﾀｶﾅ`) — treated as ASCII symbols, not Japanese.

5. **Node keyword lists are not exhaustive.** Static JA patterns in Node custom checks do not cover the full range of generic Japanese phrases. Common patterns like `"ここをクリック"`, `"詳しくはこちら"`, `"→"` (bare arrow), `"続きはこちら"` are absent from the generic-link-text seed list and other heuristic dictionaries.

6. **`ja_core_news_sm` accuracy ceiling.** The small spaCy JA model achieves ~91% POS accuracy on clean newswire. On web copy — casual registers, katakana loan words, ASCII-mixed text — accuracy drops several points. The medium model (`ja_core_news_md`) is 2–3 points better; the large model (`ja_core_news_lg`) uses contextual word vectors and is significantly better on mixed-register text.

7. **No morpheme-level stop-word filtering.** Japanese stop-word filtering uses CJK character-class stripping (`re.sub(r'[一-鿿぀-ゟ...]', '', text)`) which destroys word boundaries and content simultaneously. A morpheme-level stop-word list (filtering by POS tag: 助詞, 助動詞, 記号) via MeCab or SudachiPy would be far more accurate.

### Fix recommendations

1. **Per-element language detection via `fasttext-langid`.** Replace DOM `lang` attribute routing with a per-text-node language classifier. `fasttext-langid` identifies 176 languages from ≥ 20 characters in < 1 ms per call, handles mixed-language paragraphs, and removes the `lang` drift problem across all modules. This single change would fix issues 2 and partially 3.

2. **Upgrade spaCy model to `ja_core_news_lg`.** The large model includes word vectors (94%+ POS accuracy on web text). The size increase (~400 MB vs ~12 MB for `sm`) is acceptable for server deployment; load lazily on first JA request and cache per-process.

3. **Replace CJK character stripping with SudachiPy morpheme tokenization.** SudachiPy is the tokenizer underlying the spaCy JA pipeline — use it directly in `_remaining_label_words` to produce proper morpheme lists, then apply a morpheme-level stop-word filter (discard POS: 助詞, 助動詞, 記号, 接続詞).

4. **Expand `SENSORY_WORDS` with Japanese sensory vocabulary.** Minimum additions: `右` (right), `左` (left), `上` (top / above), `下` (bottom / below), `赤い` (red), `青い` (blue), `丸い` (round), `四角` (square), `点滅` (flashing), `音声` (audio), `形` (shape), `色` (color), `位置` (position).

5. **Extend Node JA keyword lists.** In `link-purpose.check.js`, `consistent-help.check.js`, `error-suggestion.check.js`, add: `"ここをクリック"`, `"詳しくはこちら"`, `"→"`, `"続きはこちら"`, `"もっと詳しく"`, `"お問い合わせ"`, `"サポートページ"`, `"ヘルプセンター"`.

6. **OCR: handle vertical text.** When PaddleOCR confidence is below 0.6 on a text region, add a Tesseract `--psm 5` (vertical single column) fallback step — vertical Japanese columns produce this low-confidence pattern consistently.

7. **Half-width katakana normalization.** Normalize `ｶﾀｶﾅ` → `カタカナ` before any NLP pipeline step using `unicodedata.normalize('NFKC', text)` in Python and `text.normalize('NFKC')` in Node. This prevents half-width variants from escaping Japanese keyword matches in all Node and Python checks.

---

# Section 4 — Unimplemented SCs (Automatable Gaps)

| SC | Priority | Why it's detectable | Est. effort | Status |
|---|---|---|---|---|
| 1.2.2 Captions (Prerecorded) | High | Presence of `<track kind="captions">` on `<video>` | S | **Shipped 2026-04-23** |
| 1.2.3 Audio Description | High | Presence of `<track kind="descriptions">` or second audio | S | **Shipped 2026-04-23** |
| 1.4.2 Audio Control | Medium | `<audio autoplay>` + no controls, >3 s inferred | S | **Shipped 2026-04-23** |
| 1.2.4 Captions (Live) | Medium | `<track kind="captions">` on live `<video>` | M | Pending |
| 1.2.5 Audio Description (Prerecorded) | Medium | Second audio track or `descriptions` track | M | Partially covered by 1.2.3 check |
| 2.2.1 Timing Adjustable | Medium | `<meta http-equiv="refresh">` + session-timeout detection | M | Pending |
| 2.3.1 Three Flashes | Low | Frame-differential analysis of GIF/video — heavy | L | Pending |
| 3.1.2 Language of Parts | Medium | Mixed-language text vs `lang=` attribute | M | Pending |
| 3.2.3 Consistent Navigation | High (multi-page) | Requires crawler across pages | L | **Deferred — needs multi-page crawler** |
| 3.2.4 Consistent Identification | High (multi-page) | Cross-page element-function identity | L | **Deferred — needs multi-page crawler** |

---

## Priority sprint list

**Completed 2026-04-23 sprint:**
1. ✅ Silent capture failures (§3.1) — `capture_status` now propagates end-to-end and emits INCOMPLETE.
2. ✅ 1.2.2 / 1.2.3 / 1.4.2 — three new node checks registered with fallback metadata and localised copy.
3. ✅ CSS `background-image` scan — new `background-image-content.check.js` targeting 1.1.1 + 1.4.5.
4. ✅ 2.1.2 keyboard-trap — Shift+Tab + Escape verification + F85 modal-without-escape detection.
5. ✅ Per-finding `capture_status` — distinct `incomplete` status with reason & error context.
6. ✅ Japanese support verification — confirmed existing infrastructure (EN+JA keyword lists across 30+ categories, `SENSORY_WORDS_JA`, `_detect_lang` CJK heuristic); new checks ship with inline JA translations.

**Next sprint (proposed):**
1. Multi-page crawling for 2.4.5 / 3.2.3 / 3.2.4 / 3.2.6 — largest remaining gap, requires new crawl queue.
2. 1.2.4 Captions (Live) — extend `captions-prerecorded` to detect `is-live` / HLS / WebRTC sources.
3. 3.1.2 Language of Parts — per-text-node language detection via `fasttext-langid`.
4. Toast-library heuristic for 4.1.3 — whitelist react-toastify, sonner, react-hot-toast class patterns.
5. Extend `capture_status` plumbing to OCR/contrast (1.4.3 / 1.4.5 / 1.4.11 converters currently still trust OCR silently).
