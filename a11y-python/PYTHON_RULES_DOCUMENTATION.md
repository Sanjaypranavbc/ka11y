# A11y Python Rules - Comprehensive Technical Reference

This document provides a deep technical breakdown of every accessibility rule implemented in the `a11y-python` service, detailing the goals, high-level architectures, and granular logic.

---

### **Rule ID**: WCAG 1.1.1 — Non-text Content (Level A)
*   **Goal**: Ensure all non-text content (images, icons, buttons) has a text alternative that serves the same purpose and presents the same information.
*   **Solution Approach**: **Hybrid Multimodal Audit Pipeline**. The system uses a tiered approach:
    1.  **Contextual Classification**: A machine learning classifier categorizes the image into functional (logo, icon, button), informative, or decorative.
    2.  **Semantic Extraction**: OCR (PaddleOCR) extracts any readable text within the image.
    3.  **Cross-Modal Validation**: The `AltTextAccessibilityAuditor` merges the classification intent with the OCR reality and compares them against the harvested `alt` attribute.
*   **Logic**:
    *   **Normalization**: Strips all non-alphanumeric characters and collapses whitespace to ensure robust matching despite punctuation differences.
    *   **Informative Branch**: If OCR finds text, it enforces a "Keyword Coverage" check—if at least one 3+ character word from the OCR results is missing from the `alt` text, it triggers a FAIL.
    *   **Functional Branch**: Uses **Word Boundary Regex** (`\b... \b`) to ensure specific keywords like "logo", "search", or "close" are present. Generic names for social icons (e.g., just "Facebook" instead of "Facebook icon") are flagged as Fails.
    *   **Decorative Branch**: Enforces a strict "Null Value" check. Any non-empty string in a decorative image is flagged to prevent screen readers from announcing redundant noise.

### **Rule ID**: WCAG 1.3.4 — Orientation (Level AA)
*   **Goal**: Content does not restrict its view and operation to a single display orientation (portrait or landscape).
*   **Solution Approach**: **Stateful Viewport Rotation Injection**. Use Playwright/Puppeteer to programmatically manipulate the browser environment and monitor for orientation-lock regressions.
*   **Logic**:
    1.  **Baseline State**: Capture visible elements and page height in the initial device orientation.
    2.  **Mutation**: Swap the viewport dimensions (e.g., 390x844 to 844x390) and trigger a `resize` event.
    3.  **Overlay Detection**: Execute a DOM-wide string search for "orientation-lock" patterns (e.g., "Rotate your device") using a localized regex `_ROTATE_RE`.
    4.  **Content Loss Detection**: Compare the number of visible `main` content elements. If >50% of content becomes hidden or obscured by a "Portrait Only" modal, the rule fails.

### **Rule ID**: WCAG 1.4.4 — Resize Text (Level AA)
*   **Goal**: Text can be resized up to 200% without loss of content or functionality (e.g., no clipping, no overlapping).
*   **Solution Approach**: **CSS-Text-Zoom Simulation & Geometric Diffing**. Captures precise element bounding boxes before and after a coordinated CSS text-scaling injection.
*   **Logic**:
    1.  **Injection**: Sets `document.documentElement.style.fontSize = '200%'`.
    2.  **Geometry Audit**: For every text-bearing container, the system calculates `scrollWidth` vs `clientWidth`.
    3.  **Clipping Heuristic**: If an element's `scrollWidth` exceeds its `clientWidth` by even 1px, and the container has `overflow: hidden`, it is flagged as **Clipped Text**.
    4.  **Scrollbar Tracking**: Monitors the `hasHorizontalScroll` flag on the `window` object to detect page-level reflow failures.

### **Rule ID**: WCAG 1.4.5 — Images of Text (Level AA)
*   **Goal**: Use text instead of images for better customization (unless the image is a logo or essential presentation like a complex chart/map).
*   **Solution Approach**: **OCR-Gatekeeper Audit**. Every informative image is put through a "Readable Text Detector" to ensure accessibility-best-practices.
*   **Logic**:
    1.  **Exemption Gate**: Skips images classified as `logo` (via `is_logo` flag) or `complex`.
    2.  **OCR Sweep**: Runs PaddleOCR on the remaining informative images.
    3.  **Violation Trigger**: If OCR detects any coherent text blocks (verified by English/Japanese character counts), the rule fails, recommending that the text be moved to HTML/CSS for better accessibility and SEO.

### **Rule ID**: WCAG 1.4.10 — Reflow (Level AA)
*   **Goal**: Ensure no loss of information or functionality when content is resized to a width of 320 CSS pixels (400% zoom on 1280px).
*   **Solution Approach**: **Dynamic Viewport Shrinkage Audit**. Simulates a mobile-width environment on a desktop-resolution page.
*   **Logic**:
    1.  **Resizing**: Shrinks the browser viewport to 320px width.
    2.  **Scroll Check**: Checks if `window.scrollMaxX > 0`.
    3.  **False-Positive Filtering**: Iterates through elements with horizontal scrollbars. If the overflow is caused by a "Permitted Horizontal Container" (like a `table` or `iframe`), it passes. If caused by a standard `div` or `section`, it fails.

### **Rule ID**: WCAG 1.4.11 — Non-text Contrast (Level AA)
*   **Goal**: Visual information required to identify UI components and graphical objects must have a contrast ratio of at least 3:1 against adjacent colors.
*   **Solution Approach**: **Computer Vision Boundary Contrast Analysis (F14 Fix)**. Uses pixel-level luminance calculation on the "interaction boundary" of components.
*   **Logic**:
    1.  **BBox Padding**: Takes the component's bounding box and adds an 8px "Context Wrap".
    2.  **Luminance Extraction**: Calculates sRGB relative luminance for every pixel in the component vs every pixel in the 8px padding (the "adjacent" background).
    3.  **Otsu's Segementation**: Separates the component's edge from the page background.
    4.  **Ratio Calculation**: Computes `(L1 + 0.05) / (L2 + 0.05)` between the component edge and the background area. Fails if < 3.0.

### **Rule ID**: WCAG 1.4.12 — Text Spacing (Level AA)
*   **Goal**: No loss of content or functionality occurs when users override text spacing (line height, letter spacing).
*   **Solution Approach**: **CSS Injection & Overlap Detection**. Programmatically forces WCAG-mandated spacing onto the live page and checks for layout breakages.
*   **Logic**:
    1.  **Force-Spacing**: Applies `line-height: 1.5 !important`, `letter-spacing: 0.12em !important`, and `word-spacing: 0.16em !important`.
    2.  **Regression Check**: Scans for text clipping (v-scroll or h-scroll on p/span tags) and element overlaps via bounding box intersection.

### **Rule ID**: WCAG 1.4.13 — Content on Hover or Focus (Level AA)
*   **Goal**: Content that appears on hover or focus is dismissable (without moving the pointer), hoverable, and persistent.
*   **Solution Approach**: **Event-Driven UI State Verification**. Simulates user interaction and verifies "Dismissability" via keyboard events.
*   **Logic**:
    1.  **Trigger**: Dispatches a `mouseover` event to trigger tooltips/menus.
    2.  **Persistence**: Verifies the content remains visible when the cursor is moved *onto* the new content.
    3.  **Dismissal**: Dispatches a synthetic "Escape" key event. The rule **Fails** if the content remains visible after the keypress, as WCAG requires a keyboard-only dismissal method.

### **Rule ID**: WCAG 2.2.2 — Pause, Stop, Hide (Level A)
*   **Goal**: For moving, blinking, or scrolling information, the user can pause, stop, or hide it.
*   **Solution Approach**: **Animation Persistence Heuristics**. Identifies auto-triggering motion components and searches for accessible controls.
*   **Logic**:
    1.  **Identification**: Scans for `<video autoplay>`, `<canvas>`, or elements with CSS `animation-iteration-count: infinite`.
    2.  **Duration Gate**: Verifies if the motion lasts > 5 seconds.
    3.  **Control Sweep**: Uses a specific regex `(pause|stop|hide)` to search the immediate parent containers for buttons or ARIA-label controls. Fails if no such control exists.

### **Rule ID**: WCAG 2.4.11 — Focus Not Obscured (Minimum) (Level AA)
*   **Goal**: When a component receives focus, it is not entirely hidden by author-created content (e.g., sticky headers).
*   **Solution Approach**: **Focus-Trap Intersectional Geometry**. Crawls the tab order and calculates the "Visible Focus Area" for every interactive element.
*   **Logic**:
    1.  **Focus Loop**: Iteratively calls `.focus()` on every element in the tab order.
    2.  **Overlay Mapping**: Maps out all elements with `position: fixed` or `position: sticky`.
    3.  **Intersectional Ratio**: Calculates the ratio of the focused element's area that is obscured by any mapped overlays.
    4.  **Threshold**: Fails if **Obscuration Ratio ≥ 95%** (allowing for 5% scrollbar/edge noise).

### **Rule ID**: WCAG 2.5.3 — Label in Name (Level A)
*   **Goal**: For UI components with labels that include text, the accessible name contains the visible text.
*   **Solution Approach**: **Multilingual Substring Validation**. Matches the visible label text against the programmatically resolved accessible name (ARIA-label/title).
*   **Logic**:
    1.  **Extraction**: Compares `element.textContent` (visible) with `aria-label` (hidden).
    2.  **Normalization**: Lowercases and strips all decorative punctuation from both strings.
    3.  **Word-Boundary Logic**: For Latin scripts, ensures the visible label is a discrete word within the name (regex `\b`).
    4.  **CJK Exception**: For languages without spaces (system-detected via Unicode range check), it uses a direct substring search.

### **Rule ID**: WCAG 2.5.8 — Target Size (Minimum) (Level AA)
*   **Goal**: The size of the target for pointer inputs is at least 24 by 24 CSS pixels, or has sufficient spacing.
*   **Solution Approach**: **Inter-Target Distance Analysis**. Measures both the physical size and the "Collision Envelope" of interactive elements.
*   **Logic**:
    1.  **Size Check**: If `rect.width >= 24` and `rect.height >= 24`, the target passes.
    2.  **Spacing Check (Offset)**: If size < 24px, the system measures the distance to the nearest sibling target.
    3.  **24px Diameter Check**: Fails if a 24px circle centered on the target overlaps with any other interactive element.

### **Rule ID**: WCAG 3.3.1 — Error Identification (Level A)
*   **Goal**: If an input error is automatically detected, the item that is in error is identified and the error is described to the user in text.
*   **Solution Approach**: **ARIA Relationship Audit**. Verifies the programmatic link between inputs and error messages.
*   **Logic**:
    1.  **Trigger Detection**: Scans for inputs with `aria-invalid="true"`.
    2.  **Linkage Check**: Verifies that the input has a valid `aria-describedby` attribute pointing to a visible element.
    3.  **Live Region Check**: Ensures the error container has `role="alert"` or `aria-live="polite"` to facilitate real-time screen reader notification.

### **Rule ID**: WCAG 3.3.2 — Labels or Instructions (Level A)
*   **Goal**: Labels or instructions are provided when content requires user input.
*   **Solution Approach**: **Form-Label Associative Heuristics**. Cross-references inputs against the labeling map of the page.
*   **Logic**:
    1.  **Association Check**: Fails if an `input` lacks a matching `<label for="">`, an `aria-label`, or a labeled parent.
    2.  **Heuristic "Required" Search**: Scans the text nodes adjacent to inputs for "Required" markers (e.g., `*`, `必须`). If found, it verifies the input has the programmatic `required` attribute.

### **Rule ID**: WCAG 4.1.2 — Name, Role, Value (Level A)
*   **Goal**: Ensure that all UI components have a programmatically determinable name and role.
*   **Solution Approach**: **Programmatic Identity Resolution**. Audits the "Identity Map" of interactive elements.
*   **Logic**:
    1.  **Role Verification**: Ensures functional images have `role="button"` or are contained within interactive tags.
    2.  **Name Resolution**: Follows the WCAG Name Computation algorithm: checks `aria-labelledby` > `aria-label` > `alt` > `title`. Fails if all are missing or generic (e.g., "button1").

---

### **Rule ID**: WCAG 3.2.3 — Consistent Navigation (Level AA)
*   **Goal**: Repeated navigational mechanisms across multiple pages occur in the same relative order.
*   **Solution Approach**: **Relative Sequence Alignment Mapping**. Simulates human-like browsing by crawling identical-domain menus and computing relative-order sequence checks.
*   **Logic**:
    1.  **Landmark Harvesting**: Extracts standard `<nav>`, `role="navigation"`, `<header>`, and common class-based (`navbar`, `main-menu`) menus.
    2.  **Accessible Name Extraction**: Compares the links by standard name computation to build structured navigational lists.
    3.  **Relative Alignment Matching**: Compares repeated menus (having 3+ common items) and verifies if they match in exact relative sequence order. Fails on mismatches.

### **Rule ID**: WCAG 3.2.4 — Consistent Identification (Level AA)
*   **Goal**: Components that perform the same function across multiple pages are identified consistently.
*   **Solution Approach**: **Region-Based Functional Component Analysis**. Groups repeated components (Search, Login, Logout, Contact, etc.) by layout region and compares labels.
*   **Logic**:
    1.  **Region Mapping**: Groups elements within `header`, `footer`, `navigation`, or `main` landmarks.
    2.  **Function Matching**: Detects intended actions (e.g. login, register, cart, search) via specialized regex and clean label normalizers.
    3.  **Consistency Audit**: Asserts that all repeated elements mapped to the same function in identical regions share exactly consistent accessible labels.

### **Rule ID**: WCAG 3.1.3 — Unusual Words (Level AAA)
*   **Goal**: Provide a mechanism for explaining unusual words, jargon, idioms, and abbreviations.
*   **Solution Approach**: **NLP-Driven Terminology Extraction & Explanation Checking**. Employs lightweight, lazy-loaded keyphrase singletons (spaCy, YAKE, and KeyBERT) to analyze vocabulary rarity and explanation mapping.
*   **Logic**:
    1.  **Unusual Candidates Discovery**: Uses YAKE and KeyBERT to extract prominent phrases, filtered against a fast text frequency database (`wordfreq`) to identify statistical rarity.
    2.  **Explanation Scanner**: Cross-references rare candidates against known grammatical definition patterns (e.g., `X is a...`, `X refers to...`) within the sentence context.
    3.  **Programmatic Verification**: Inspects native definition elements (`<dfn>`, `<abbr>`) and `aria-describedby` linkages to verify appropriate accessibility wiring.

### **Rule ID**: WCAG 2.4.10 — Section Headings (Level AAA)
*   **Goal**: Section headings are used to organize content.
*   **Solution Approach**: **Visual & Semantic Layout Region Audit**. Evaluates structural blocks within the browser viewport to verify heading presence, size, and significance.
*   **Logic**:
    1.  **Structural Region Sweep**: Gathers landmark regions (`section`, `article`, `main`, `[role="region"]`).
    2.  **Semantic Heading Verification**: Searches for h1–h6 tags or `aria-labelledby` pointing to appropriate heading elements within each section.
    3.  **Visual Styling Analysis**: Flags non-semantic styled heading tags (e.g., bold paragraphs with 16px+ size) that mimic sections without being screen-reader discoverable.

