# a11y Crawler: End-to-End Study Manual

This document provides a complete technical walkthrough of the `a11y` crawler architecture on the `crawler` branch. This is intended for end-to-end study of how the system discovers, analyzes, and extracts web elements for WCAG auditing.

---

## 1. The Design Philosophy: "Single-Shot" Discovery
Traditional crawlers load a page multiple times for different checks (e.g., once for images, once for forms). 
**a11y** uses a "Universal" strategy:
1. **Load Once**: Open the page in a single highly-instrumented session.
2. **Extract All**: Run a comprehensive JavaScript "Brain" that pulls every required signal in one pass.
3. **Snapshot**: Save a `PageSnapshot` object that contains everything needed by the auditors (Forms, Media, Layout, etc.).

---

## 2. The Orchestration Layer (Python)
The entry point is `UniversalPageLoader.load()` in `a11y/crawler/universal_page.py`.

### The Preparation Pipeline
Before extraction begins, the crawler ensures the page is "Audit Ready" using these steps:
1. **Stealth Context**: Launches Chromium with a realistic User-Agent and viewport to bypass basic WAFs (Cloudflare/Imperva).
2. **SSRF Guard**: Installs a network interceptor that blocks the crawler from accessing internal/private IPs (Security).
3. **Smart Navigation**: Tries three fallback modes: `domcontentloaded` -> `load` -> `commit`.
4. **SPA Wait**: If the page is a Single Page App (Next.js, React, Vue), it waits an additional 800ms for the hydration to finish.
5. **DOM Stability**: Uses a `MutationObserver` to wait until nothing on the page has changed for at least 600ms.
6. **Lazy Load Trigger**: Scrolls the page in 6 increments and mocks `IntersectionObserver` to "wake up" lazy-loaded images/content.

---

## 3. The Extraction Logic (JavaScript)
The actual "work" happens in a massive JavaScript payload (`_COMBINED_EXTRACT_JS`).

### Core Functions (The "How it Works")

#### A. Shadow DOM Piercing (`queryShadow`)
Modern websites hide elements inside "Shadow Roots" (Web Components). Standard crawlers are blind to these.
- **Mechanism**: Use a `while` loop with a queue. It finds every element, checks if it has a `shadowRoot`, and if so, adds that root to the queue to search inside it.
- **Why it matters**: This ensures that custom video players, complex widgets, and component libraries are fully audited.

#### B. Universal Selector Generation (`buildSelector`)
To track elements across different auditors, the crawler builds a unique "Address" for every element.
- **Syntax**: Uses `>>>` to denote a Shadow boundary.
- **Example**: `body > main > x-player >>> button.play-btn`

#### C. Accessible Name Computation (`computeAccessibleName`)
This replicates the **W3C AccName 1.1** specification. It determines what a screen reader "says" when it encounters an element.
- **Priority**: `aria-labelledby` > `aria-label` > Native `<label>` > `title` > `innerText`.

---

## 4. What it Takes (Category Deep Dive)

| Category | Key Signals Extracted | WCAG Impact |
| :--- | :--- | :--- |
| **Forms** | `id`, `label_text`, `aria-describedby`, error message IDs, `role="alert"`. | 3.3.1 (Error ID), 3.3.2 (Labels). |
| **Interactive** | `visible_label` vs `accessible_name`, `role`, `href`. | 2.5.3 (Label in Name), 2.1.1 (Keyboard). |
| **Target Sizes** | `getBoundingClientRect()` width/height, padding, nearest neighbour gap. | 2.5.8 (Target Size). |
| **Moving Content** | `animationName` from CSS, `data-autoplay` for carousels, video duration. | 2.2.2 (Pause, Stop, Hide). |
| **Media** | `tracks`, `nearby_links` (transcripts), `nearby_details` (context). | 1.2.1, 1.2.2 (Media Alt). |
| **Text Spacing** | `height`, `overflow`, `fixed-height` flags, `is_clipped` detection. | 1.4.12 (Text Spacing). |

---

## 5. End-to-End Data Flow
1. **Input**: A URL.
2. **Step 1**: `UniversalPageLoader` launches Playwright.
3. **Step 2**: Page is stabilized and lazy-content is triggered.
4. **Step 3**: `_COMBINED_EXTRACT_JS` runs globally.
5. **Step 4**: Data is mapped into a `PageSnapshot` Pydantic model.
6. **Step 5**: Snapshot is passed to individual crawlers (e.g., `AsyncMediaCrawler.from_snapshot()`).
7. **RefID**: Every element gets a SHA-1 hash (`ref_id`) so the results can be highlighted in the dashboard.

---

## 6. Security & Anti-Bot
- **SSRF Guard**: Located in `_ssrf_guard.py`. It prevents internal network probing.
- **Challenge Detection**: Detects Cloudflare/Incapsula challenge pages and reports them as "Degraded" logs rather than empty results.
- **Wait Timing**: Uses a `DOM_STABILITY_TOTAL_MS` limit (12 seconds) to avoid getting stuck on infinite loading spinners.
