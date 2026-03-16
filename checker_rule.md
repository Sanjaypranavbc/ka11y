# Ka11y — WCAG 2.2 Automation Coverage Report

> **Project Goal:** Automated WCAG 2.2 rule checking using Python (custom checkers) + Node.js (axe-core engine).
> **Generated:** 2026-03-16
> **Note:** "Manual" axe-core flags are excluded — only truly automated detections are counted as coverage.

---

## Component Overview

| Component | Stack | Automation Type |
|-----------|-------|----------------|
| **ka11y-python** | FastAPI + Playwright + OCR (Tesseract) + NLTK | Deep custom rule checkers (image OCR, form heuristics, contrast) |
| **ka11y-node** | Express + Puppeteer + axe-core 4.9.0 | DOM-based automated accessibility engine |

---

## Section 1 — Covered by BOTH Python + Node.js

> These 4 criteria are implemented in both components. Python provides deeper semantic analysis; Node.js provides broad DOM validation.

---

### 1.1.1 — Non-text Content

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Standard** | WCAG 2.2 |
| **Component** | Python + Node.js |
| **Python File** | `ka11y-python/ka11y/accessibility/rules/non_text/alttext.py` |
| **Node.js File** | `ka11y-node/src/services/accessibility.service.js` (via axe-core: `image-alt`, `input-image-alt`, `area-alt`, `role-img-alt`, `svg-img-alt`, `object-alt`) |
| **Description** | All non-text content (images, icons, buttons, complex graphics) must have a text alternative that describes its purpose or marks it as decorative. |
| **How Python Covers It** | Crawls page images → runs OCR (Tesseract) → classifies each image as Decorative / Informative / Functional (Logo, Icon, Button) / Complex → validates `alt` attribute using cosine similarity between alt text and OCR-detected text → checks decorative images have `alt=""` → checks functional images have action-describing alt |
| **How Node.js Covers It** | axe-core checks all `<img>`, `<input type="image">`, `<area>`, `role="img"`, `<svg>` elements for presence and non-emptiness of accessible name (`alt`, `aria-label`, `aria-labelledby`) |
| **Why Both Cover It** | It is the most automatable WCAG rule — presence of `alt` is a static DOM attribute. Python adds OCR-level quality check (alt text actually matches image content), which axe-core cannot do. |
| **Automation Depth** | Python: quality check (semantic match). Node.js: structural check (attribute presence). |

---

### 4.1.2 — Name, Role, Value

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Standard** | WCAG 2.2 |
| **Component** | Python + Node.js |
| **Python File** | `ka11y-python/ka11y/accessibility/rules/non_text/alttext.py` |
| **Node.js File** | axe-core: `aria-allowed-attr`, `aria-required-attr`, `aria-valid-attr`, `button-name`, `input-button-name`, `select-name`, `aria-roles`, `frame-title`, `nested-interactive` |
| **Description** | All UI components (form inputs, buttons, widgets, iframes) must have accessible names, correct ARIA roles, and expose their state/properties programmatically. |
| **How Python Covers It** | Checks functional images (images inside `<button>`, `<a>`) have accessible names via `alt`, `aria-label`, or `aria-labelledby`. |
| **How Node.js Covers It** | axe-core validates ARIA role correctness, required attributes, allowed attributes, accessible name computation for all interactive elements. |
| **Why Both Cover It** | ARIA attributes are static DOM — fully automatable. Python covers the image-specific subset; axe-core covers the full interactive element tree. |

---

### 3.3.1 — Error Identification

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Standard** | WCAG 2.2 |
| **Component** | Python + Node.js |
| **Python File** | `ka11y-python/ka11y/accessibility/rules/forms/form_auditor.py` |
| **Node.js File** | axe-core: `aria-allowed-attr` (partial), `label` |
| **Description** | If an input error is automatically detected, the item in error must be identified and described to the user in text. |
| **How Python Covers It** | Crawls form fields → checks error messages are programmatically linked via `aria-describedby`, `role="alert"`, or `aria-live` regions → heuristic detection of `*` required markers in labels/placeholders. |
| **How Node.js Covers It** | axe-core checks for ARIA live regions and role="alert" presence — partial structural check only. |
| **Why Both Cover It** | Form error patterns (aria-describedby, role="alert") are static DOM attributes. Python goes deeper with heuristic matching between fields and their error containers. |

---

### 3.3.2 — Labels or Instructions

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Standard** | WCAG 2.2 |
| **Component** | Python + Node.js |
| **Python File** | `ka11y-python/ka11y/accessibility/rules/forms/form_auditor.py` |
| **Node.js File** | axe-core: `label`, `label-content-name-mismatch` |
| **Description** | When user input is required, labels or instructions must be provided so users know what input is expected. |
| **How Python Covers It** | Checks every form field has a visible `<label>`, `aria-label`, or `aria-labelledby` → verifies required fields are explicitly marked → checks `autocomplete` attributes for common field types. |
| **How Node.js Covers It** | axe-core checks all `<input>`, `<select>`, `<textarea>` for associated labels and non-empty accessible names. |
| **Why Both Cover It** | Label association is a static DOM relationship — fully automatable via attribute inspection. |

---

## Section 2 — Covered by Node.js Only (axe-core Automated)

> These criteria are automatically detected by axe-core. Python has no checker for them. Coverage is purely DOM-structural (not semantic/visual).

---

### 1.3.1 — Info and Relationships

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Node.js only |
| **axe-core Rules** | `aria-required-children`, `aria-required-parent`, `definition-list`, `dlitem`, `list`, `listitem`, `table-duplicate-name`, `td-headers-attr`, `th-has-data-cells`, `form-field-multiple-labels`, `heading-order` |
| **Description** | Information, structure, and relationships conveyed visually must be programmatically determinable or available in text. |
| **How Node.js Covers It** | axe-core validates correct semantic HTML structure — list nesting, table header/data relationships, ARIA parent-child role requirements, heading hierarchy. |
| **Why Python Doesn't Cover It** | Python's current scope is images and forms only. Semantic structure checking requires full DOM tree traversal which axe-core already handles. |

---

### 1.3.4 — Orientation

| Field | Detail |
|-------|--------|
| **WCAG Level** | AA |
| **Component** | Node.js only |
| **axe-core Rules** | `css-orientation-lock` |
| **Description** | Content must not restrict its view/operation to a single display orientation unless essential. |
| **How Node.js Covers It** | axe-core detects CSS `transform: rotate` or media queries that lock orientation to portrait/landscape only. |
| **Why Python Doesn't Cover It** | CSS analysis requires parsing computed styles — axe-core handles this via browser rendering context. |

---

### 1.3.5 — Identify Input Purpose

| Field | Detail |
|-------|--------|
| **WCAG Level** | AA |
| **Component** | Node.js only |
| **axe-core Rules** | `autocomplete-valid` |
| **Description** | The purpose of form fields collecting user's personal data must be programmatically determinable. |
| **How Node.js Covers It** | axe-core validates that `autocomplete` attribute values on personal data fields match the WCAG-approved token list. |
| **Why Python Doesn't Cover It** | Python's form checker verifies label presence but doesn't yet validate autocomplete token correctness. |

---

### 1.4.3 — Contrast (Minimum)

| Field | Detail |
|-------|--------|
| **WCAG Level** | AA |
| **Component** | Node.js only (+ Python partial via OCR) |
| **axe-core Rules** | `color-contrast` |
| **Description** | Text and images of text must have a contrast ratio of at least 4.5:1 (3:1 for large text). |
| **How Node.js Covers It** | axe-core computes foreground/background color from computed CSS styles and calculates WCAG contrast ratio for all text nodes. |
| **Python Note** | `contrast_analyzer.py` does OCR-based contrast checking on images (text within images), which axe-core cannot do. Complements Node.js coverage. |

---

### 1.4.11 — Non-text Contrast

| Field | Detail |
|-------|--------|
| **WCAG Level** | AA |
| **Component** | Node.js only |
| **axe-core Rules** | `color-contrast-enhanced` |
| **Description** | UI components (inputs, buttons, focus indicators) and informational graphics must have at least 3:1 contrast ratio against adjacent colors. |
| **How Node.js Covers It** | axe-core computes contrast of UI component borders and graphical elements against their background. |

---

### 2.1.1 — Keyboard

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Node.js only |
| **axe-core Rules** | `scrollable-region-focusable`, `tabindex`, `frame-focusable-content` |
| **Description** | All functionality must be operable through a keyboard interface without specific timing. |
| **How Node.js Covers It** | axe-core checks scrollable regions have focusable elements, detects `tabindex="-1"` removing elements from keyboard flow, validates iframes are keyboard-accessible. |

---

### 2.1.2 — No Keyboard Trap

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Node.js only |
| **axe-core Rules** | `frame-focusable-content` |
| **Description** | If keyboard focus can be moved to a component, it must be possible to move focus away using standard keys. |
| **How Node.js Covers It** | axe-core checks iframe focus management and modal dialog patterns. |

---

### 2.2.2 — Pause, Stop, Hide

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Node.js only |
| **axe-core Rules** | `blink`, `marquee` |
| **Description** | Moving, blinking, or scrolling content that starts automatically and lasts more than 5 seconds must have a mechanism to pause, stop, or hide it. |
| **How Node.js Covers It** | axe-core detects deprecated `<blink>` and `<marquee>` elements which auto-animate. |
| **Coverage Gap** | Only deprecated elements detected. JS-driven carousels, CSS animations, and custom auto-scrolling are not detected by axe-core alone. |

---

### 2.4.1 — Bypass Blocks

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Node.js only |
| **axe-core Rules** | `bypass`, `skip-link` |
| **Description** | A mechanism must be available to bypass blocks of content repeated on multiple pages (e.g., skip-to-main link). |
| **How Node.js Covers It** | axe-core checks for skip links pointing to main content area or presence of landmark regions. |

---

### 2.4.2 — Page Titled

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Node.js only |
| **axe-core Rules** | `document-title` |
| **Description** | Web pages must have titles that describe topic or purpose. |
| **How Node.js Covers It** | axe-core checks `<title>` element exists and is non-empty. |

---

### 2.4.4 — Link Purpose (In Context)

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Node.js only |
| **axe-core Rules** | `link-name` |
| **Description** | The purpose of each link must be determinable from the link text alone or from its context. |
| **How Node.js Covers It** | axe-core checks all `<a>` elements have non-empty, non-generic accessible names. |

---

### 2.4.6 — Headings and Labels

| Field | Detail |
|-------|--------|
| **WCAG Level** | AA |
| **Component** | Node.js only |
| **axe-core Rules** | `empty-heading`, `heading-order` |
| **Description** | Headings and labels must describe topic or purpose. |
| **How Node.js Covers It** | axe-core checks heading elements are non-empty and follow logical hierarchy (h1→h2→h3). |

---

### 2.5.3 — Label in Name

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Node.js only |
| **axe-core Rules** | `label-content-name-mismatch` |
| **Description** | For UI components with visible text labels, the accessible name must contain the visible text. |
| **How Node.js Covers It** | axe-core compares visible label text with computed accessible name to detect mismatches. |

---

### 3.1.1 — Language of Page

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Node.js only |
| **axe-core Rules** | `html-has-lang`, `html-lang-valid` |
| **Description** | The default human language of each web page must be programmatically determined. |
| **How Node.js Covers It** | axe-core checks `<html lang="...">` exists and contains a valid BCP 47 language tag. |

---

### 3.1.2 — Language of Parts

| Field | Detail |
|-------|--------|
| **WCAG Level** | AA |
| **Component** | Node.js only |
| **axe-core Rules** | `valid-lang` |
| **Description** | Human language of each passage or phrase in the content must be programmatically determined. |
| **How Node.js Covers It** | axe-core checks all `lang` attributes in the DOM are valid BCP 47 language tags. |

---

### 3.2.6 — Consistent Help *(WCAG 2.2 NEW)*

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Node.js only (partial) |
| **axe-core Rules** | `consistent-help` (added in axe-core 4.7+) |
| **Description** | Help mechanisms (contact info, chat, self-help tools) must appear in a consistent location across pages. |
| **How Node.js Covers It** | axe-core detects presence of help mechanisms on single pages. Full cross-page consistency requires multi-page analysis. |
| **Coverage Gap** | Single-page check only; cross-page order verification is not yet implemented. |

---

### 4.1.2 — Name, Role, Value (Node.js extension)

> Already listed in Section 1 (Both). Node.js covers much broader ARIA validation beyond Python's image-focused checks.

---

### 4.1.3 — Status Messages

| Field | Detail |
|-------|--------|
| **WCAG Level** | AA |
| **Component** | Node.js only |
| **axe-core Rules** | `aria-live-region-wait` |
| **Description** | Status messages (success, error, progress, loading) must be programmatically determinable without receiving focus. |
| **How Node.js Covers It** | axe-core validates `aria-live`, `role="status"`, `role="alert"`, `role="log"` are used correctly for status message containers. |

---

## Section 3 — NOT Covered by Either Python or Node.js

> These criteria have no automated implementation in ka11y. Each entry explains **why** it cannot be automated with current architecture and **how** to build automation for it.

---

### 1.2.1 — Audio-only and Video-only (Prerecorded)

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Neither |
| **Description** | Prerecorded audio-only and video-only content must have a text alternative or audio description. |
| **Why Not Covered** | Requires fetching and parsing actual media files (audio/video content), which is outside DOM analysis scope. axe-core only checks for the HTML structure (track element presence), not actual content quality. |
| **How to Automate** | 1. Detect `<audio>` and `<video>` elements without `<track>` children → flag automatically. 2. For quality: use Whisper (OpenAI) or AWS Transcribe to transcribe audio → compare against provided transcript using cosine similarity (similar to Python's existing text comparison in alttext.py). |
| **Suggested Tool** | Python: `whisper` library + Playwright to extract media URLs → transcript comparison |

---

### 1.2.2 — Captions (Prerecorded)

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Neither |
| **Description** | Captions must be provided for all prerecorded audio content in synchronized media. |
| **Why Not Covered** | Structural check (is a `<track kind="captions">` present?) is easy, but verifying caption accuracy, completeness, and synchronization requires AI/NLP analysis of actual VTT/SRT content vs. audio. |
| **How to Automate** | 1. Check `<track kind="captions" src="...">` presence — automatable via DOM scan. 2. Download VTT file → parse cues → transcribe audio via Whisper → compute similarity score between VTT cues and transcription. |
| **Suggested Tool** | Python: `webvtt-py` for VTT parsing + `whisper` for transcription + existing cosine similarity from alttext.py |

---

### 1.2.3 — Audio Description or Media Alternative (Prerecorded)

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Neither |
| **Description** | An audio description or full text alternative must be provided for prerecorded video content. |
| **Why Not Covered** | Checking for a `<track kind="descriptions">` is possible but verifying the description actually covers all visual information requires video analysis. |
| **How to Automate** | 1. Flag `<video>` elements without `<track kind="descriptions">`. 2. Advanced: Use a vision model (GPT-4V, Gemini) to analyze video frames → compare described events with audio description track cues. |

---

### 1.2.4 — Captions (Live)

| Field | Detail |
|-------|--------|
| **WCAG Level** | AA |
| **Component** | Neither |
| **Description** | Captions must be provided for all live audio content in synchronized media. |
| **Why Not Covered** | Live streams cannot be statically analyzed. Requires real-time monitoring of a live stream and verifying caption delivery within acceptable latency. |
| **How to Automate** | Playwright script that monitors live stream → checks for active `aria-live` region updates or WebVTT stream → verifies captions are appearing within ~2 second latency. Very complex. |

---

### 1.2.5 — Audio Description (Prerecorded)

| Field | Detail |
|-------|--------|
| **WCAG Level** | AA |
| **Component** | Neither |
| **Description** | Audio descriptions must be provided for all prerecorded video content. |
| **Why Not Covered** | Same as 1.2.3. Track presence is checkable; description quality and coverage of visual events is not. |
| **How to Automate** | See 1.2.3. Use vision-language model to compare video frame descriptions with audio description track content. |

---

### 1.3.2 — Meaningful Sequence

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Neither |
| **Description** | If sequence of content affects meaning, the correct reading sequence must be programmatically determinable. |
| **Why Not Covered** | DOM order is detectable but whether visual presentation (via CSS float, grid, flexbox order) matches logical reading order requires rendered layout analysis. |
| **How to Automate** | Playwright: capture element positions via `getBoundingClientRect()` → compare visual top-to-bottom order with DOM order → flag reversals. Python can implement a layout-vs-DOM order comparator. |
| **Suggested Tool** | Python + Playwright: `element.evaluate("el => el.getBoundingClientRect()")` for each focusable element |

---

### 1.3.3 — Sensory Characteristics

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Neither |
| **Description** | Instructions must not rely solely on sensory characteristics (shape, color, size, visual location, sound) to identify content. |
| **Why Not Covered** | Requires NLP to detect text patterns like "click the round button" or "see the box on the right" in page copy — semantic understanding of UI instructions. |
| **How to Automate** | NLP/LLM pipeline: extract all instruction-like text from DOM → run through an LLM with a prompt checking for sensory-only references → flag problematic instructions. Python: use spaCy or an LLM API. |
| **Suggested Tool** | Python + spaCy/OpenAI: pattern matching on instructional text nodes |

---

### 1.4.1 — Use of Color

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Neither |
| **Description** | Color must not be the only visual means of conveying information, indicating an action, prompting a response, or distinguishing a visual element. |
| **Why Not Covered** | Detecting when color is the *only* signal (vs. also having text, icon, pattern) requires semantic understanding of the UI's visual design. DOM alone cannot determine intent. |
| **How to Automate** | Partial: Flag form validation that uses only `color: red` on inputs without a text error message. Playwright screenshot + CV analysis to detect elements that differ only by color. |
| **Suggested Tool** | Python + Playwright: screenshot comparison of element states (default vs. error) using pixel diff |

---

### 1.4.2 — Audio Control

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Neither |
| **Description** | If audio plays automatically for more than 3 seconds, a mechanism to pause or stop it must be provided. |
| **Why Not Covered** | Auto-playing audio is a runtime behavior. Static DOM analysis can detect `<audio autoplay>` and `<video autoplay>` but cannot detect JS-triggered audio or verify a stop mechanism works. |
| **How to Automate** | Playwright: 1. Detect `autoplay` attribute on media elements. 2. Check for visible play/pause controls near the element. 3. Listen to Web Audio API events to detect programmatic audio playback. |

---

### 1.4.4 — Resize Text

| Field | Detail |
|-------|--------|
| **WCAG Level** | AA |
| **Component** | Neither |
| **Description** | Text must be resizable up to 200% without loss of content or functionality (without assistive technology). |
| **Why Not Covered** | Requires browser-level font size doubling and then checking for text overflow, hidden content, or broken layout. Cannot be done with static DOM analysis. |
| **How to Automate** | Playwright: 1. Set `page.evaluate("document.documentElement.style.fontSize = '200%'")`. 2. Check all text elements are still visible and not clipped (`overflow: hidden` detection). 3. Compare element counts before/after scaling. |
| **Suggested Tool** | Python + Playwright: font scaling test + overflow detection script |

---

### 1.4.5 — Images of Text

| Field | Detail |
|-------|--------|
| **WCAG Level** | AA |
| **Component** | Neither |
| **Description** | If technologies are available, text must be used to convey information rather than images of text (unless essential). |
| **Why Not Covered** | Requires OCR to detect text in images, then semantic analysis to determine if the same information could be conveyed as real HTML text. |
| **How to Automate** | Python: already has OCR pipeline in `text_detector.py` → extend to flag images where OCR detects significant text content → check if that same text exists as real DOM text nearby → if not, flag as potential images-of-text violation. |
| **Suggested Tool** | Python: reuse `text_detector.py` OCR + DOM text comparison |

---

### 1.4.10 — Reflow

| Field | Detail |
|-------|--------|
| **WCAG Level** | AA |
| **Component** | Neither |
| **Description** | Content must not require scrolling in two dimensions for a viewport 320px wide (except for content that requires 2D layout). |
| **Why Not Covered** | Requires viewport resize simulation and horizontal scroll detection — a rendered-browser test. |
| **How to Automate** | Playwright: 1. Set viewport to 320×256px. 2. Check `document.documentElement.scrollWidth > 320` → flag 2D scroll. 3. Verify no content is clipped or hidden. Python script wrapping this as an automated test. |
| **Suggested Tool** | Python + Playwright: `page.set_viewport_size({"width": 320, "height": 256})` + scroll width check |

---

### 1.4.12 — Text Spacing

| Field | Detail |
|-------|--------|
| **WCAG Level** | AA |
| **Component** | Neither |
| **Description** | No loss of content when overriding: line-height ≥1.5, letter-spacing ≥0.12em, word-spacing ≥0.16em, spacing after paragraphs ≥2em. |
| **Why Not Covered** | Requires injecting CSS overrides and checking for content loss — a rendered-browser interaction. |
| **How to Automate** | Playwright: 1. Inject CSS bookmarklet-style override (text spacing rules). 2. Check for elements with `overflow: hidden` that now have clipped text using `scrollHeight > clientHeight`. 3. Compare visible text before/after override. |
| **Suggested Tool** | Python + Playwright: CSS injection test + overflow detection |

---

### 1.4.13 — Content on Hover or Focus

| Field | Detail |
|-------|--------|
| **WCAG Level** | AA |
| **Component** | Neither |
| **Description** | Content that appears on hover or focus must be dismissible, hoverable, and persistent. |
| **Why Not Covered** | Requires triggering hover/focus events and observing appearing content — dynamic interaction testing. |
| **How to Automate** | Playwright: 1. `page.hover(selector)` on all elements → detect newly visible elements (DOM diff). 2. Check if hoverable tooltip can be hovered itself. 3. Check if pressing Escape dismisses it. |
| **Suggested Tool** | Python + Playwright: hover simulation + DOM mutation observer |

---

### 2.1.4 — Character Key Shortcuts

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Neither |
| **Description** | If a keyboard shortcut uses only letter, number, punctuation, or symbol characters, a mechanism must exist to turn it off or remap it. |
| **Why Not Covered** | Requires runtime inspection of JavaScript `keydown`/`keyup` event listeners — not visible in static DOM. |
| **How to Automate** | Playwright: inject a script to override `addEventListener` before page load → record all keyboard event registrations → flag single-character shortcuts without modifier keys. |
| **Suggested Tool** | Python + Playwright: `page.evaluate()` to intercept event listener registration |

---

### 2.2.1 — Timing Adjustable

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Neither |
| **Description** | If a time limit is set by content, users must be able to turn off, adjust, or extend it. |
| **Why Not Covered** | Session timeouts and dynamic countdown timers are controlled by JavaScript and server logic — not visible in static DOM. |
| **How to Automate** | Playwright: 1. Detect `<meta http-equiv="refresh">` auto-redirect (static). 2. Monitor `setTimeout`/`setInterval` calls via JS interception for time limits. 3. Check for session timeout warning dialogs. Partial automation only. |

---

### 2.3.1 — Three Flashes or Below Threshold

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Neither |
| **Description** | Pages must not contain content that flashes more than three times per second, unless flash is below thresholds. |
| **Why Not Covered** | Requires video capture of rendered page and frame-by-frame analysis of luminance changes — hardware-level measurement. |
| **How to Automate** | Playwright: record screen using `ffmpeg` → analyze frame sequence for rapid luminance changes. Very complex but theoretically automatable. |
| **Suggested Tool** | Playwright + `ffmpeg` + Python video analysis (frame diff > threshold detection) |

---

### 2.4.3 — Focus Order

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Neither (partially flagged by axe-core but not fully checked) |
| **Description** | If a page can be navigated sequentially, focus order must preserve meaning and operability. |
| **Why Not Covered** | DOM order check is possible but visual layout order can differ from DOM order due to CSS (flex `order`, grid placement, `position: absolute`). Full check requires layout comparison. |
| **How to Automate** | Playwright: 1. Tab through all focusable elements recording order. 2. Record each element's `getBoundingClientRect()` position. 3. Flag cases where tab order moves significantly backward in visual layout. |
| **Suggested Tool** | Python + Playwright: tab simulation + visual position recording |

---

### 2.4.5 — Multiple Ways

| Field | Detail |
|-------|--------|
| **WCAG Level** | AA |
| **Component** | Neither |
| **Description** | More than one way must be available to locate a web page within a set of pages (e.g., site search + navigation menu). |
| **Why Not Covered** | Fundamentally a site-level metric — requires analyzing the whole site to confirm multiple navigation paths exist (search bar, sitemap, navigation menu, breadcrumbs). Single-page analysis is structurally insufficient. |
| **How to Automate** | Python multi-page crawler: crawl entire site → detect presence of search box, sitemap link, navigation menu, breadcrumbs across all pages → confirm at least 2 navigation methods are consistently present. |
| **Suggested Tool** | Python + Playwright: site crawler + navigation pattern detector |

---

### 2.4.7 — Focus Visible

| Field | Detail |
|-------|--------|
| **WCAG Level** | AA |
| **Component** | Neither (axe-core has partial detection but not reliable) |
| **Description** | Any keyboard-operable UI component must have a visible focus indicator. |
| **Why Not Covered** | Focus styling is CSS-based and only visible when element is focused in a rendered browser. Static DOM inspection of `outline: none` is partial — custom focus styles are valid. |
| **How to Automate** | Playwright: 1. Tab to each focusable element. 2. Take screenshot. 3. Compare screenshot with unfocused state using pixel diff. 4. Flag elements where focused/unfocused screenshots are identical (no visible focus change). |
| **Suggested Tool** | Python + Playwright: focused-state screenshot comparison using `Pillow` pixel diff |

---

### 2.4.11 — Focus Not Obscured (Minimum) *(WCAG 2.2 NEW)*

| Field | Detail |
|-------|--------|
| **WCAG Level** | AA |
| **Component** | Neither |
| **Description** | When a UI component receives focus, it must not be entirely hidden by author-created content (sticky headers, modals, cookie banners). |
| **Why Not Covered** | Requires visual overlay detection — checking if a focused element is covered by higher z-index elements. No static DOM signal. |
| **How to Automate** | Playwright: 1. Tab to each element. 2. Check `document.elementFromPoint(rect.x + rect.width/2, rect.y + rect.height/2)` — if returned element is NOT the focused element, it's obscured. |
| **Suggested Tool** | Python + Playwright: `elementFromPoint` check at focused element's center coordinates |

---

### 2.4.13 — Focus Appearance *(WCAG 2.2 NEW)*

| Field | Detail |
|-------|--------|
| **WCAG Level** | AA |
| **Component** | Neither |
| **Description** | Focus indicator must have minimum area (perimeter of unfocused component × 2px) and minimum contrast ratio of 3:1. |
| **Why Not Covered** | Requires pixel-level measurement of focus indicator dimensions, enclosed area, and color contrast — a visual rendering + image processing task. |
| **How to Automate** | Playwright: 1. Tab to element → screenshot. 2. Use Pillow/OpenCV to detect changed pixels (focus ring). 3. Measure area of changed pixels. 4. Compute contrast of focus ring color vs. adjacent background. |
| **Suggested Tool** | Python + Playwright + OpenCV/Pillow: focus ring detection and measurement |

---

### 2.5.1 — Pointer Gestures

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Neither |
| **Description** | All functionality that uses multipoint or path-based gestures must have a single-pointer alternative. |
| **Why Not Covered** | Requires runtime analysis of JavaScript touch event handlers to identify gesture-only interactions. No static DOM attribute indicates this. |
| **How to Automate** | Playwright: inject script to intercept `touchstart`/`touchmove` event listeners → flag elements with multi-touch handlers that have no single-tap alternative. |

---

### 2.5.2 — Pointer Cancellation

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Neither |
| **Description** | For single pointer functionality, at least one of: no down-event trigger, abort/undo mechanism, up-event trigger reversal, or essential exception. |
| **Why Not Covered** | Requires runtime inspection of `mousedown` vs `mouseup` event binding on interactive elements. |
| **How to Automate** | Playwright: inject script to intercept pointer event registrations → flag interactive elements that bind critical actions to `mousedown`/`pointerdown` only. |

---

### 2.5.4 — Motion Actuation

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Neither |
| **Description** | Functionality triggered by device motion must have a UI alternative and be disableable. |
| **Why Not Covered** | Requires inspecting `DeviceMotionEvent` and `DeviceOrientationEvent` JavaScript handlers — sensor APIs not testable in standard browser automation. |
| **How to Automate** | Playwright: inject script to intercept `window.addEventListener('devicemotion', ...)` → flag pages using motion events → check for equivalent UI controls. |

---

### 2.5.7 — Dragging Movements *(WCAG 2.2 NEW)*

| Field | Detail |
|-------|--------|
| **WCAG Level** | AA |
| **Component** | Neither |
| **Description** | All functionality that uses dragging must have a single pointer alternative (e.g., click to select, then click to place). |
| **Why Not Covered** | Requires identifying drag-only interfaces via runtime interaction testing — no static DOM attribute signals draggable-only functionality. |
| **How to Automate** | Playwright: 1. Detect elements with `draggable="true"` or drag event listeners. 2. Check for alternative pointer-based controls (click-to-select patterns). 3. Attempt drag simulation and verify single-click alternative exists. |
| **Suggested Tool** | Python + Playwright: `page.drag_and_drop()` + alternative control detection |

---

### 2.5.8 — Target Size (Minimum) *(WCAG 2.2 NEW)*

| Field | Detail |
|-------|--------|
| **WCAG Level** | AA |
| **Component** | Neither (axe-core `target-size` rule is partial) |
| **Description** | The size of the target for pointer inputs must be at least 24×24 CSS pixels (except where inline, equivalent, or essential). |
| **Why Not Covered** | axe-core's `target-size` rule flags obvious violations but misses dynamically sized elements and inline exceptions. Python has no checker for element dimensions. |
| **How to Automate** | Playwright: iterate all interactive elements (`a`, `button`, `input`, etc.) → call `getBoundingClientRect()` → flag elements where `width < 24 || height < 24` → exclude inline text links per WCAG exception. |
| **Suggested Tool** | Python + Playwright: dimension scan script with WCAG exception handling |

---

### 3.2.1 — On Focus

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Neither |
| **Description** | When a component receives focus, it must not initiate a change of context (navigation, form submission, new window). |
| **Why Not Covered** | Requires simulating Tab/click to each focusable element and detecting context changes (URL change, new window, form submission) after focus. |
| **How to Automate** | Playwright: 1. Record current URL and DOM hash. 2. Tab to each element. 3. After each focus, check if URL changed, new window opened, or major DOM section changed. 4. Flag unexpected context changes. |
| **Suggested Tool** | Python + Playwright: focus simulation + URL/DOM change monitor |

---

### 3.2.2 — On Input

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Neither |
| **Description** | Changing the setting of any UI component must not automatically cause a change of context unless user is advised beforehand. |
| **Why Not Covered** | Requires interacting with form elements (select dropdowns, checkboxes, radio buttons) and monitoring for automatic page navigation or major DOM changes. |
| **How to Automate** | Playwright: 1. Find all `<select>`, `<input type="checkbox">`, `<input type="radio">`. 2. Change their value. 3. Monitor for URL changes or window navigation events. 4. Flag automatic context changes. |
| **Suggested Tool** | Python + Playwright: input simulation + navigation event listener |

---

### 3.2.3 — Consistent Navigation

| Field | Detail |
|-------|--------|
| **WCAG Level** | AA |
| **Component** | Neither |
| **Description** | Navigation mechanisms repeated across pages must occur in the same relative order each time. |
| **Why Not Covered** | Single-page analysis is structurally insufficient. Requires crawling multiple pages, extracting nav elements, and comparing their DOM order across pages. |
| **How to Automate** | Python multi-page crawler: 1. Crawl all pages in the site. 2. Extract navigation landmark HTML fingerprint (link order, aria-labels). 3. Compare fingerprints across pages. 4. Flag pages with different navigation order. |
| **Suggested Tool** | Python + Playwright: site crawler + nav-order fingerprinting |

---

### 3.2.4 — Consistent Identification

| Field | Detail |
|-------|--------|
| **WCAG Level** | AA |
| **Component** | Neither |
| **Description** | Components with the same functionality must be identified consistently across a set of pages. |
| **Why Not Covered** | Requires cross-page component identity comparison — e.g., a search button labeled "Search" on one page but "Find" on another. Single-page analysis cannot detect this. |
| **How to Automate** | Python multi-page crawler: 1. Crawl all pages. 2. Build a component identity map (icon + function → accessible name). 3. Flag functionally equivalent components with different names across pages. |

---

### 3.3.3 — Error Suggestion

| Field | Detail |
|-------|--------|
| **WCAG Level** | AA |
| **Component** | Neither |
| **Description** | If an input error is detected and suggestions for correction are known, the suggestion must be provided to the user. |
| **Why Not Covered** | Requires understanding the *content* of error messages to verify they contain actionable suggestions — NLP/semantic task, not structural DOM check. |
| **How to Automate** | Python: 1. Trigger form validation (via Playwright form submission). 2. Extract error message text. 3. Run through NLP classifier or LLM prompt: "Does this error message contain a specific correction suggestion?" 4. Flag vague errors like "Invalid input." |
| **Suggested Tool** | Python + Playwright + spaCy/LLM: error message quality analyzer |

---

### 3.3.4 — Error Prevention (Legal, Financial, Data)

| Field | Detail |
|-------|--------|
| **WCAG Level** | AA |
| **Component** | Neither |
| **Description** | For pages that cause legal/financial commitments or delete data, submissions must be reversible, verified, or confirmable. |
| **Why Not Covered** | Requires understanding the *purpose* of the page (is this a financial transaction? data deletion?) and verifying the presence of confirmation steps, undo mechanisms, or review screens — semantic + interaction task. |
| **How to Automate** | Playwright: 1. Detect forms with keywords (payment, delete, purchase, submit order) in labels/headings. 2. Check for confirmation dialog patterns, review steps, or undo options. 3. Flag transaction forms without a confirmation step. Partial automation only. |

---

### 3.3.7 — Redundant Entry *(WCAG 2.2 NEW)*

| Field | Detail |
|-------|--------|
| **WCAG Level** | A |
| **Component** | Neither (axe-core maps to `autocomplete-valid` but this is not the same) |
| **Description** | Information previously entered by the user that is required again in the same process must be auto-populated or available for selection. |
| **Why Not Covered** | Requires multi-step form flow tracking — detecting that a field in step 2 asks for information already entered in step 1 without auto-populating it. |
| **How to Automate** | Python + Playwright: 1. Identify multi-step forms (wizard patterns). 2. Record data entered in each step. 3. In subsequent steps, detect fields requesting the same type of information. 4. Check if they are pre-filled or offer a "same as above" option. |

---

### 3.3.8 — Accessible Authentication (Minimum) *(WCAG 2.2 NEW)*

| Field | Detail |
|-------|--------|
| **WCAG Level** | AA |
| **Component** | Neither (axe-core `accessible-auth-min` is partial) |
| **Description** | A cognitive function test (like solving a puzzle, transcribing text) must not be required for authentication unless an alternative or assistance is provided. |
| **Why Not Covered** | Requires detecting CAPTCHA types (text CAPTCHA = violation; image-select CAPTCHA with alt text = ok) and understanding if alternatives exist. Full check requires interaction testing of the auth flow. |
| **How to Automate** | Playwright: 1. Detect login pages (form with password field). 2. Check for CAPTCHA widgets (reCAPTCHA, hCaptcha, text puzzles). 3. Flag text-transcription CAPTCHAs. 4. Check if audio alternative or "I'm human" non-cognitive option exists. |
| **Suggested Tool** | Python + Playwright: CAPTCHA type detector + alternative mechanism checker |

---

## Coverage Summary

### Why the Total is 56, Not 50 — WCAG Version Breakdown

| WCAG Version | Level A | Level AA | Level AAA | Total |
|---|---|---|---|---|
| WCAG 2.0 | 25 | 13 | 23 | 61 |
| WCAG 2.1 | +5 new → **30** | +7 new → **20** | +5 new → **28** | **78** |
| WCAG 2.2 | −1 (4.1.1 removed) +2 new → **31** | +5 new → **25** | +2 new → **30** | **86** |

**Ka11y scope = Level A + Level AA = 31 + 25 = 56 criteria.**

The old document used WCAG 2.1's count (30+20=50) — that was wrong. WCAG 2.2 added 7 new criteria at Level A+AA, making the correct total 56.

**Level AAA (30 criteria) is intentionally out of scope** — WCAG itself does not require AAA conformance as a baseline, and most AAA rules require manual expert review or specialized tooling (sign language, reading level analysis, etc.). They are listed briefly at the end of this document.

---

### Correct Coverage Count (56 Level A+AA criteria)

| Section | Count | Criteria |
|---------|-------|---------|
| **Both Python + Node.js** | 4 | 1.1.1, 4.1.2, 3.3.1, 3.3.2 |
| **Node.js Only — Fully Automated** | 15 | 1.3.1, 1.3.4, 1.3.5, 1.4.3, 1.4.11, 2.1.1, 2.1.2, 2.4.1, 2.4.2, 2.4.4, 2.4.6, 2.5.3, 3.1.1, 3.1.2, 4.1.3 |
| **Node.js Only — Partially Automated** | 2 | 2.2.2 (blink/marquee only), 3.2.6 (single-page only) |
| **Python Only** | 0 | Python rules all overlap with Node.js scope |
| **Not Covered** | 35 | Runtime/visual/multi-page/semantic — see Section 3 |
| **TOTAL** | **56** | Level A (31) + Level AA (25) |

> Verification: 4 + 15 + 2 + 0 + 35 = **56** ✓

### Corrected Status Table (out of 56 Level A+AA)

| Status | Count | % of 56 |
|--------|-------|---------|
| ✅ Fully Automated | 19 (4 Both + 15 Node.js) | 34% |
| ⚠️ Partially Automated | 2 | 4% |
| ❌ Not Covered | 35 | 62% |

### WCAG 2.2 New Criteria (7 new at Level A+AA — all 7 accounted for)

| Criterion | Level | Status | Notes |
|-----------|-------|--------|-------|
| 2.4.11 Focus Not Obscured | AA | ❌ | Needs `elementFromPoint` check in Playwright |
| 2.4.13 Focus Appearance | AA | ❌ | Needs screenshot + pixel measurement |
| 2.5.7 Dragging Movements | AA | ❌ | Needs interaction testing |
| 2.5.8 Target Size (Minimum) | AA | ⚠️ | axe partial; needs full Playwright dimension scan |
| 3.2.6 Consistent Help | A | ⚠️ | axe partial; needs multi-page check |
| 3.3.7 Redundant Entry | A | ❌ | Needs multi-step form flow tracking |
| 3.3.8 Accessible Auth | AA | ❌ | Needs CAPTCHA detection + auth flow testing |

---

## Automation Roadmap (Priority Order)

| Priority | Criterion | Implementation Effort | Recommended Approach |
|----------|-----------|----------------------|---------------------|
| 🔴 High | 1.4.10 Reflow | Low | Playwright viewport 320px + scrollWidth check |
| 🔴 High | 1.4.4 Resize Text | Low | Playwright font 200% + overflow detection |
| 🔴 High | 2.4.7 Focus Visible | Medium | Playwright tab + screenshot pixel diff |
| 🔴 High | 2.4.11 Focus Not Obscured 🆕 | Low | Playwright `elementFromPoint` at focus center |
| 🔴 High | 2.5.8 Target Size 🆕 | Low | Playwright `getBoundingClientRect` scan |
| 🟡 Medium | 1.3.2 Meaningful Sequence | Medium | Playwright DOM order vs. visual position comparison |
| 🟡 Medium | 1.4.12 Text Spacing | Medium | Playwright CSS injection + overflow detection |
| 🟡 Medium | 1.4.13 Content on Hover/Focus | Medium | Playwright hover simulation + DOM diff |
| 🟡 Medium | 2.4.3 Focus Order | Medium | Playwright tab sequence + layout position recording |
| 🟡 Medium | 2.4.13 Focus Appearance 🆕 | High | OpenCV focus ring measurement |
| 🟡 Medium | 3.2.1 On Focus | Medium | Playwright focus + URL/DOM change monitor |
| 🟡 Medium | 3.2.2 On Input | Medium | Playwright input change + navigation monitor |
| 🟡 Medium | 1.4.5 Images of Text | Medium | Reuse Python OCR + DOM text comparison |
| 🟢 Low | 3.2.3 Consistent Navigation | High | Multi-page crawler + nav fingerprinting |
| 🟢 Low | 3.2.4 Consistent Identification | High | Multi-page crawler + component identity map |
| 🟢 Low | 2.4.5 Multiple Ways | High | Site crawler + navigation method detection |
| 🟢 Low | 3.3.3 Error Suggestion | High | LLM-based error message quality analysis |
| 🟢 Low | 2.5.7 Dragging Movements 🆕 | High | Playwright drag detection + alternative check |
| 🟢 Low | 3.3.7 Redundant Entry 🆕 | High | Multi-step form flow tracker |
| 🟢 Low | 3.3.8 Accessible Auth 🆕 | High | CAPTCHA detector + auth flow tester |

---

## Level AAA — Out of Scope (30 criteria)

> WCAG does not require AAA conformance as a baseline. These are aspirational and most require expert manual review. Listed here for completeness so the total adds up to **86**.

| Criterion | Title | Why Out of Scope |
|-----------|-------|-----------------|
| 1.2.6 | Sign Language (Prerecorded) | Requires video sign language overlay — human production |
| 1.2.7 | Extended Audio Description | Requires pausing video for full descriptions — production task |
| 1.2.8 | Media Alternative (Prerecorded) | Full text transcript of video — content creation task |
| 1.2.9 | Audio-only (Live) | Live transcript — real-time human captioning |
| 1.3.6 | Identify Purpose | Icons/regions need purpose tokens — complex semantic mapping |
| 1.4.6 | Contrast (Enhanced) | 7:1 ratio — stricter version of 1.4.3 (already covered) |
| 1.4.7 | Low or No Background Audio | Audio recording quality — production-level check |
| 1.4.8 | Visual Presentation | Full text presentation control — complex CSS validation |
| 1.4.9 | Images of Text (No Exception) | Zero images of text — stricter version of 1.4.5 |
| 2.1.3 | Keyboard (No Exception) | Zero exceptions for keyboard — stricter 2.1.1 |
| 2.2.3 | No Timing | Zero time limits — requires full interaction testing |
| 2.2.4 | Interruptions | Allow suppressing non-emergency interruptions — JS behavior |
| 2.2.5 | Re-authenticating | Session expiry with data preservation — server + UI testing |
| 2.2.6 | Timeouts | Warn users about inactivity timeouts — JS runtime monitoring |
| 2.3.2 | Three Flashes | Zero flashes allowed — stricter version of 2.3.1 |
| 2.3.3 | Animation from Interactions | Motion must be disableable — CSS/JS preference detection |
| 2.4.8 | Location | Indicate position within site — site-level metadata check |
| 2.4.9 | Link Purpose (Link Only) | Link text alone must describe destination — stricter 2.4.4 |
| 2.4.10 | Section Headings | Content organized by headings — structural analysis |
| 2.4.12 | Focus Not Obscured (Enhanced) 🆕 | Zero obscuring allowed — stricter version of 2.4.11 |
| 2.5.5 | Target Size (Enhanced) | 44×44px minimum — stricter version of 2.5.8 |
| 2.5.6 | Concurrent Input Mechanisms | Don't restrict input modality — JS event listener analysis |
| 3.1.3 | Unusual Words | Glossary for jargon — NLP + content creation |
| 3.1.4 | Abbreviations | Expand abbreviations — NLP text analysis |
| 3.1.5 | Reading Level | Reading grade ≤ lower secondary — NLP readability scoring |
| 3.1.6 | Pronunciation | Pronunciation for ambiguous words — NLP + content |
| 3.2.5 | Change on Request | Context changes only on request — full interaction testing |
| 3.3.5 | Help | Context-sensitive help — requires semantic UI understanding |
| 3.3.6 | Error Prevention (All) | All forms need confirmation — stricter version of 3.3.4 |
| 3.3.9 | Accessible Authentication (Enhanced) 🆕 | Zero cognitive tests in auth — stricter version of 3.3.8 |

**Level AAA total: 30 criteria**

---

## Grand Total — All WCAG 2.2 Criteria

| Level | Total | In Scope | Covered | Partial | Not Covered |
|-------|-------|----------|---------|---------|-------------|
| **A** | 31 | ✅ Yes | 19 | 2 | 10 |
| **AA** | 25 | ✅ Yes | 0 | 0 | 25 |
| **AAA** | 30 | ❌ Out of scope | — | — | — |
| **4.1.1** | 1 | 🗑️ Removed in 2.2 | — | — | — |
| **Grand Total** | **86** | **56 in scope** | **19** | **2** | **35** |

> 19 + 2 + 35 = **56** in-scope criteria accounted for. All 86 WCAG 2.2 criteria documented.