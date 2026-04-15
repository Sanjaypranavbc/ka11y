# ka11y Rule Confidence Report

**Generated:** 2026-04-15 (Updated after false-positive audit)
**Scope:** All 12 Python auditor rules + 5 supporting infrastructure layers
**Method:** Full static analysis + runtime heuristic refinement

---

## Score legend

| Score | Meaning |
|-------|---------|
| 90–100% | High confidence — result is almost always accurate |
| 70–89%  | Good — occasional edge-case misses or false positives |
| 50–69%  | Moderate — heuristic-dependent; expect manual verification needed |
| < 50%   | Low — structural flaw, missing exception, or fragile detection |

---

## Summary table

| # | Rule | WCAG SC | Engine | Confidence | Status |
|---|------|---------|--------|-----------|--------|
| 1 | Alt Text | 1.1.1 | py-static | **80%** | IMPROVED — fixed OCR substring matching & icon validation |
| 2 | Contrast (OCR) | 1.4.3 | py-static | **82%** | IMPROVED — added logo and decorative exemptions |
| 3 | Form Labels / Errors | 3.3.1, 3.3.2 | py-static | **78%** | IMPROVED — multi-ID aria-describedby support |
| 4 | Label in Name | 2.5.3 | py-static | **82%** | Stable |
| 5 | Pause / Stop / Hide | 2.2.2 | py-static | **75%** | IMPROVED — fixed naive regex false positives |
| 6 | Target Size | 2.5.8 | py-static | **70%** | IMPROVED — fixed inverted UA logic |
| 7 | Reflow | 1.4.10 | py-rendered | **75%** | Stable |
| 8 | Text Spacing | 1.4.12 | py-rendered | **63%** | Needs stable selector matching |
| 9 | Resize Text | 1.4.4 | py-rendered | **65%** | Needs stable selector matching |
| 10 | Orientation | 1.3.4 | py-rendered | **70%** | IMPROVED — widened regex and interactive ratio |
| 11 | Content on Hover/Focus | 1.4.13 | py-rendered | **45%** | Needs persistence testing |
| 12 | Focus Not Obscured (Min) | 2.4.11 | py-rendered | **58%** | Needs dynamic overlay collection |
| 13 | Focus Not Obscured (Enh) | 2.4.12 | py-rendered | **55%** | Needs dynamic overlay collection |

---

## Recent Improvements (April 2026)

### 1 · Alt Text & Images of Text — Confidence: 80%
- **Fix:** Prevented decorative images from failing 1.4.5 even when OCR detects text. WCAG allows decorative images of text.
- **Fix:** Added dynamic failure reasons for 1.4.5 that include the detected text snippet for easier verification.
- **Fix:** Refined chart detection in `classifier.py` to reduce false positives on news photos in `<figure>` tags.
- **Fix:** Replaced naive substring matching (`w in norm_alt`) with word-boundary regex for OCR text verification.
- **Fix:** Strengthened icon validation to require at least 4 characters and a real word, preventing "ok" or "hi" from passing automatically.

### 2 · Contrast (OCR-backed) — Confidence: 82%
- **Fix:** Implemented WCAG exceptions for Logotypes and Decorative images. Contrast rules 1.4.3 and 1.4.6 now skip these categories based on classifier results.
- **Fix:** Improved findings report to include `image_src` for contrast violations, allowing developers to see the failing element.

### 3 · Form Labels & Error Messages — Confidence: 78%
- **Fix:** Re-engineered `aria-describedby` resolution in the crawler to handle multiple space-separated IDs. It now combines text from all linked elements and correctly flags `role="alert"` if present in any of them.

### 5 · Pause / Stop / Hide — Confidence: 75%
- **Fix:** Addressed naive pause button regex matching. Applied word boundaries `\b(pause|stop)\b` to prevent false positives like "stop-motion gallery" from skipping violations.

### 6 · Target Size — Confidence: 70%
- **Fix:** Corrected inverted logic for User-Agent controlled widgets. Previously, custom-styled radios were exempt while native ones were not. This has been flipped to align with WCAG 2.5.8 exception 4.

### 10 · Orientation — Confidence: 70%
- **Fix:** Broadened `_ROTATE_RE` to capture more device rotation instructions (e.g., "landscape only", "please use portrait") avoiding exact-phrase dependency.
- **Fix:** Lowered the interactive-element count ratio threshold from 0.5 to 0.1 to drastically reduce false positives on responsive (hamburger) menus.

### Node Engine Checks
Several node-side checks (`ka11y-node/src/custom-checks`) were also evaluated and improved:
- **status-messages (4.1.3):** Fixed `\bnew\b` regex flagging unrelated terms ("New York") by switching to specific numeric counter contexts.
- **link-purpose (2.4.4):** Fixed `textContent` capturing screen-reader-only text (e.g., "open in new tab") when it is visually hidden.
- **audio-transcript (1.2.1):** Fixed `<details>`-based transcripts not being correctly identified as valid alternatives.

---

## Rule-by-rule breakdown

[... rest of the document remains for reference ...]
