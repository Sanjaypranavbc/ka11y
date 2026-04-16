# ka11y Visual Accessibility: Low-Level Technical Documentation

**Date:** April 16, 2026
**Scope:** Non-text auditing rules (Images, Visual Elements, Interactive Targets)

---

## 1. WCAG 1.1.1 — Non-Text Content
**Primary File:** `ka11y-python/ka11y/accessibility/rules/non_text/alttext.py`

### Implementation Detail
The auditor uses a multi-stage verification pipeline merging Classifier data (for intent) and OCR data (for content verification).

| Function | Logic Description |
| :--- | :--- |
| `_check_1_1_1_informative` | Compares `alt` text against OCR tokens. Requires at least one OCR word (≥3 chars) to exist in the alt text using word-boundary regex (`\bword\b`). |
| `_check_1_1_1_logo` | Enforces W3C WAI pattern. Alt must contain keywords: `logo`, `ロゴ`, `home`, `ホーム`, or `トップ`. |
| `_check_1_1_1_icon` | Validates social icons (must include "icon" qualifier) and functional icons (must match `_BUTTON_ACTION_WORDS` or describe purpose). |
| `_check_1_1_1_decorative` | Strict check: Alt must be exactly `""` or null. Any generic text like "spacer" triggers a FAIL. |
| `_check_1_1_1_button` | Validates accessible name for icon-buttons. Filters out initials/noise by requiring a 3-character minimum. |

### Limitations & Logic Issues
1.  **Acronym Collision:** The 3-character token floor in `_check_1_1_1_informative` causes false negatives for valid 2-letter tokens (e.g., "UI", "Go").
2.  **Synonym Blindness:** OCR matching is literal. If an image has text "Search" and alt is "Look up", it fails despite being semantically correct.
3.  **Classifier Dependency:** If the ML classifier misidentifies a logo as "informative", it bypasses the "logo" keyword check, potentially allowing an alt like "brand name" to pass without the "logo" qualifier.

---

## 2. WCAG 1.4.3 & 1.4.11 — Contrast (Text & UI)
**Primary File:** `ka11y-python/ka11y/accessibility/rules/non_text/contrast_analyser.py`

### Implementation Detail
Uses computer vision (OpenCV) to measure perceived luminance on rendered pixels.

| Function | Logic Description |
| :--- | :--- |
| `segment_text_region` | Uses **Otsu's Binarization** + Luminance Polarity detection to separate foreground (text/icon) from background. |
| `calculate_luminance_contrast` | Converts RGB to Linear sRGB, calculates relative luminance (Y), and applies the formula `(L1 + 0.05) / (L2 + 0.05)`. Uses 10th/90th percentiles to avoid noise. |
| `analyze_ui_component` | **F14 Fix:** Expands the bounding box by a 8px "context pad" to measure the component against the actual page background instead of internal image pixels. |

### Limitations & Logic Issues
1.  **Gradient Failure:** Otsu's thresholding assumes a bimodal distribution. Complex gradients or "Glassmorphism" UI often result in failed segmentation.
2.  **Anti-Aliasing Noise:** Pixel-level analysis often captures "halo" pixels around text, which can skew ratios. The use of percentiles (10/90) is a heuristic, not a perfect fix.
3.  **Resolution Scaling:** High-DPI screenshots (retina) increase processing time and can introduce interpolation artifacts that slightly alter luminance values.

---

## 3. WCAG 1.4.5 — Images of Text
**Primary Files:** `ka11y-node/src/custom-checks/images-of-text.check.js` (Heuristics) & `alttext.py` (OCR)

### Implementation Detail
Employs a "Defense in Depth" strategy:
1.  **Node.js (Crawler Phase):** Scores images based on `src` keywords (e.g., "banner", "text"), alt length (>5 words), and punctuation.
2.  **Python (Audit Phase):** Cross-references with OCR results. If OCR detects substantial text and the image is not a logo, it flags a violation.

### Limitations & Logic Issues
1.  **Logotype False Positives:** Distinguishing between a "Logo" (exempt) and "Styled Text Image" (violation) is a major logic hurdle. The current fix (F12) relies on the classifier's `is_logo` flag, which is hit-or-miss.
2.  **Incidental Text:** Text found in the background of a photograph (e.g., a street sign in a news photo) is flagged as 1.4.5 unless the classifier correctly marks the image as "informative" or "complex".

---

## 4. WCAG 2.2.2 — Pause, Stop, Hide
**Primary File:** `ka11y-python/ka11y/crawler/moving_content_crawler.py`

### Implementation Detail
Detects time-based movement via the Playwright `getAnimations()` API and library-specific DOM markers.

| Component | Logic Description |
| :--- | :--- |
| `nearbyPauseButton` | Scans `parentElement` (up to 2 levels) for regex `/(pause|stop|一時停止)/i`. |
| `carouselIsAutoplay` | Hardcoded support for Bootstrap, Slick, Swiper, Owl, Flickity, Glide, and Splide. Checks `data-autoplay` attributes and internal library state (e.g., `el.swiper.autoplay.running`). |
| `_is_animated_gif` | Fetches the GIF source and counts frames using Pillow. Only flags if frame count > 1. |

### Limitations & Logic Issues
1.  **State Verification:** The auditor checks for the *existence* of a button, but cannot verify if clicking it actually stops the animation.
2.  **DOM Depth:** Pause buttons buried deep in nested wrappers (more than 2 levels up) are missed.
3.  **Third-Party Carousels:** Hand-rolled carousels using raw `setInterval` or `requestAnimationFrame` without standard classes/data-attributes are invisible to the crawler.

---

## 5. WCAG 2.5.8 — Target Size (Minimum)
**Primary File:** `ka11y-python/ka11y/crawler/target_size_crawler.py`

### Implementation Detail
Measures the rendered bounding box of every interactive element against the 24x24 CSS pixel requirement.

| Logic | Description |
| :--- | :--- |
| `is_offset_exception` | Calculates a "theoretical" 24px box around the center of the element. If this box does not intersect any other interactive target, the element PASSES despite being < 24px. |
| `isInlineLink` | Uses `window.getComputedStyle(el).display === 'inline'` and verifies parent `textContent` length to identify links in paragraphs (exempt). |
| `isUAControlled` | Checks for `appearance: none`. If native styling is preserved, the element is exempt (browser-specific). |

### Limitations & Logic Issues
1.  **Overlap Complexity:** Elements that are visually stacked (z-index) but transparent may trigger intersection failures in the offset calculation.
2.  **Padding vs. Size:** Some libraries use large transparent padding to meet target size. The logic handles this via `getBoundingClientRect`, but developers often confuse "visible size" with "target size".
3.  **Viewport Sensitivity:** Since it runs at 1440px, mobile-specific target size issues (which are often worse) are not captured unless the crawler is explicitly configured for mobile emulation.

---

## 6. Advanced Deep Dive: WCAG 1.4.1 — Use of Color
**Primary File:** `ka11y-node/src/custom-checks/use-of-color.check.js`

### Implementation Detail
This rule checks whether inline text links are visually distinguishable from surrounding non-link text by means other than color alone (e.g., underline, font-weight, background). 

| Logic | Description |
| :--- | :--- |
| `getAncestorTextStyle` | Traverses the DOM upwards to find the closest non-`<a>` ancestor to establish the baseline text styling (color, font-weight, background). |
| `hasNonColorCue` | Evaluates CSS properties on the link. A PASS requires at least one of the following: `textDecoration` (underline/overline/line-through), `borderBottomWidth > 0`, `outlineWidth > 0`, a `fontStyle` difference (e.g., italic), a `backgroundColor` change, or a `fontWeight` difference of at least 100 units (e.g., 400 to 500). |
| `colorsDiffer` | Custom RGB comparison logic. Returns true if any RGB channel between the link and the ancestor differs by more than 15 units (to account for anti-aliasing or slight design tokens). |

### Limitations & Logic Issues
1.  **Context Strictness:** The crawler only evaluates links within specific structural selectors (`p a`, `li a`, `article > p a`, etc.). It purposefully ignores `section a` or standalone links, as the WCAG rule specifically targets links *within a block of text*. However, this can miss heavily nested, unstructured text blocks that don't use semantic HTML `<p>` tags.
2.  **Hover States Ignored:** The crawler evaluates the static DOM state. If a link has no underline statically, but relies *only* on a color change on `:hover` (which is a violation for color-blind users navigating via mouse), the crawler cannot detect the missing hover cue without simulating interactions.
3.  **Visual "Weight" Thresholds:** The font-weight threshold was recently reduced from a 200-unit delta to a 100-unit delta (e.g., 400 normal to 500 medium). While this fixes false positives for modern design systems, a 100-unit difference in some thin font families is nearly imperceptible and violates the spirit of the WCAG guideline.

---

## 7. Advanced Deep Dive: WCAG 1.3.3 — Sensory Characteristics
**Primary Files:** `ka11y-python/ka11y/accessibility/rules/sensory/wcag_133_auditor.py` & `sensory_crawler.py`

### Implementation Detail
This is one of the most complex heuristics, relying on Natural Language Processing (spaCy) to determine if instructional text relies *solely* on sensory properties (shape, size, color, position, orientation, sound) without a non-sensory identifier.

| Logic | Description |
| :--- | :--- |
| `_is_instruction_text` | Detects whether text is instructional using imperative verbs (e.g., "Click", "Press") or declarative positional hints (e.g., "Located on the right"). |
| `_remaining_label_words` | The core validation heuristic. It strips out purpose phrases ("to continue"), sensory words ("red", "round"), generic UI nouns ("button", "link"), and stop words. If any non-stop-word tokens remain, the auditor assumes a valid non-sensory label is present (e.g., "Click the red **Submit** button" leaves "Submit"). |
| `_get_nlp` (spaCy) | Uses `en_core_web_sm` for English sentence tokenization and `ja_core_news_sm` for Japanese. It preserves the parser pipe for Japanese because word segmentation in CJK languages lacks spaces. |

### Limitations & Logic Issues
1.  **Vocabulary Exhaustion:** The `GENERIC_UI_NOUNS` and `SENSORY_WORDS` lists are finite. If a developer uses a novel sensory word (e.g., "Click the *translucent* orb"), the auditor will likely fail to flag the sensory characteristic.
2.  **CJK Word Boundaries:** Japanese implementation (`_has_meaningful_label_text_ja`) cannot use standard regex word boundaries (`\b`). It resorts to complex stripping and assumes a meaningful label exists if *any* CJK content characters remain after stripping. This can lead to false passes if the leftover text is grammatically structural but not actually a label.
3.  **Semantic Disconnect:** The auditor evaluates the sentence in isolation. It cannot visually verify if the instruction "Click the red button" actually corresponds to a button that only has a red background and no text label. It only validates the *instructional phrasing*, not the visual reality of the target component.

---

## 8. Systemic Pipeline Issue: Silent Image Capture Failures
**Primary Area:** `ka11y-python/ka11y/crawler/crawler.py` & API response formatters

### Issue Description
During the execution of visual rules (1.1.1, 1.4.5, 1.4.11, etc.), the pipeline relies extensively on Playwright capturing element screenshots or downloading image blobs. However, the system currently suffers from **silent failures** when these visual assets cannot be fetched.

### Symptoms
*   **Broken Frontend UI:** Users frequently encounter broken image icons (like a network failure icon) when viewing violation reports in the frontend.
*   **Missing Feedback:** There are no explicit system warnings, UI alerts, or detailed log outputs notifying the user that specific images failed to download or that a snapshot operation timed out.
*   **False Negatives/Incomplete Audits:** If an image fails to download, rules dependent on computer vision (like OCR text detection or boundary contrast analysis) are silently skipped or marked as "N/A" without informing the user that a technical failure occurred rather than a clean pass.

### Limitations & Logic Flaws
1.  **Swallowed Exceptions:** The `_safe_screenshot` and `download_image` methods in the crawler often catch and suppress exceptions (e.g., CORS restrictions, lazy-loading not triggering, or 504 timeouts) to prevent the entire crawl from crashing. While this ensures stability, it discards the error context.
2.  **No Fallback State in API:** The combined JSON findings model doesn't enforce a "failed_to_capture" flag. If `screenshot_path` or `image_src` ends up empty or invalid, the API simply passes the bad/empty path to the frontend.
3.  **Dynamic Rendering Quirks:** Highly dynamic elements (e.g., canvas-based UI or SVGs that rely on external font networks) often fail to snapshot correctly if the `timeout_ms` triggers before full rendering. This results in empty or partial images being saved, again with zero user-facing diagnostic warnings.
