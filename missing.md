# Missing WCAG Rules and Automation Feasibility

This document lists notable WCAG Success Criteria (SC) that are not implemented as explicit custom checks in the repository (based on a quick scan of src/custom-checks and audits). Each entry includes an automation feasibility score (percentage + qualitative band), a short rationale, and recommended tech stack to implement automated detection.

> Note: many SCs are already covered indirectly by axe-core. This list focuses on rules missing as bespoke checks/audits in the project and/or that require additional techniques beyond a straight axe rule.

---

1. 2.4.2 — Document title
   - Status: Covered by axe-core (no bespoke check required)
   - Feasibility: 100% — Fully automatable (axe level)
   - Why: axe-core's "document-title" rule deterministically checks for a non-empty <title>. The repository's rulesGuide includes the rule and the node service injects axe; very low false-positive risk.
   - Tech stack: axe-core (JS) + Puppeteer / Playwright (already in the project).

2. 1.4.3 — Contrast (Minimum) for text
   - Feasibility: 85% — Mostly automatable
   - Why: Color contrast ratio can be calculated programmatically for text and large-scale UI elements. Edge cases: complex text over images, CSS layering, dynamic text rendering (canvas or WebGL) require additional heuristics or manual review.
   - Tech stack: axe-core color-contrast checks (JS) + Puppeteer/Playwright; for visual render edge-cases, use headless browser screenshots + pixel inspection (Canvas API / Puppeteer screenshot) and OpenCV (Python/JS) if needed.

3. 1.4.11 — Non-text Contrast
   - Feasibility: 60% — Partially automatable
   - Why: Requires measuring contrast of graphical components like icons, controls, and focus indicators. Automation can detect many cases (static icons, backgrounds) but struggles with complex layered visuals and dynamic effects.
   - Tech stack: Puppeteer/Playwright screenshots, OpenCV (python/opencv-python) or node-canvas, custom heuristics to locate control boundaries; possibly EasyOCR for embedded text detection.

4. 1.3.1 — Info and Relationships
   - Feasibility: 40% — Partially automatable
   - Why: Some semantic relationships are inferable from DOM structure (heading order, lists, table headers). However, many relationships are conceptual (ARIA semantics, prose meaning) and need manual review.
   - Tech stack: axe-core + DOM heuristics (JS), HTML parsing (cheerio) or Playwright evaluate; optionally use NLP (Python transformers/spacy) to detect document structure anomalies for suspicious cases.

5. 2.1.1 — Keyboard (All functionality operable via keyboard)
   - Feasibility: 50% — Partially automatable
   - Why: Basic checks (tabindex misuse, focusable elements, presence of keyboard event handlers) can be automated. Full verification (every control reachable and usable) often needs interactive tests and human judgement for complex widgets.
   - Tech stack: Puppeteer/Playwright to simulate keyboard navigation, axe-core, custom interactive test scripts. For deeper coverage, script simulated user flows.

6. 2.2.1 — Timing Adjustable
   - Feasibility: 30% — Poorly/partially auditable
   - Why: Requires understanding whether user-adjustable controls exist for time-limited operations (e.g., adjustable timeouts, ability to request more time). Detecting UI controls is possible, but semantics and back-end timeouts are often opaque.
   - Tech stack: Playwright to explore forms and dialogs; heuristic detection of countdown timers, JavaScript timers; log and flag for manual review.

7. 2.4.4 — Link Purpose (In Context)
   - Feasibility: 60% — Partially automatable
   - Why: Tooling can detect ambiguous link text ("click here") and compare link text to nearby context, but full semantic intent often needs human judgement or language models to infer intention.
   - Tech stack: axe-core (some rules), DOM heuristics, NLP models (lightweight transformers or heuristics) to compare link text against page context. Playwright for DOM capture.

8. 1.3.5 — Identify Input Purpose
   - Feasibility: 70% — Partially to largely automatable
   - Why: HTML autocomplete attribute and input type hint purpose; detection is straightforward when attributes exist. When attribute is missing or custom widgets used, automation falls back to heuristics and may miss cases.
   - Tech stack: DOM inspection via Playwright/Puppeteer or server-side parsing (cheerio/bs4); pydantic for schema checks if crawling forms in Python.

9. 2.5.3 — Label in Name
   - Feasibility: 75% — Mostly automatable
   - Why: Tests whether the accessible name (computed via ARIA/alt/label) contains the visible label. Programmatically computable by injecting a script that computes Accessible Name and compares with visible text. Edge cases: complex widgets and localization.
   - Tech stack: axe-core + custom evaluate script in page (JS) to compute accessible name (using DOM APIs or axecore's accessibilityName computation) + Puppeteer/Playwright.

10. 1.2.4 — Captions (Live)
    - Feasibility: 25% — Poorly automatable
    - Why: Live captioning correctness and timeliness requires manual or speech-to-text evaluation against dynamic audio; automated detection can only check presence of captions for live streams but not quality.
    - Tech stack: detect captions DOM/subtitle tracks with Playwright; for deeper checks integrate speech recognition (faster-whisper) and alignment scoring (Python) — still limited.

11. 2.5.1 / 2.5.2 — Pointer Gestures & Pointer Cancellation
    - Feasibility: 65% — Partially automatable
    - Why: Detecting use of gesture libraries and presence of single-pointer alternatives can be automated (library fingerprinting, DOM patterns). Validating correct cancellation behaviour is harder and may require runtime interaction.
    - Tech stack: existing audits (wcag-2.5.1 and pointer-cancellation) are partially present — extend with Playwright gesture emulation and synthetic pointer events.

12. 4.1.2 — Name, Role, Value for Widgets (ARIA correctness)
    - Feasibility: 70% — Mostly automatable
    - Why: Tools can compute accessible name/role/value and find mismatches or missing attributes; some semantics still need manual verification for complex ARIA patterns.
    - Tech stack: axe-core, Playwright/Puppeteer page.evaluate, ARIA parsers.

---

Implementation notes & next steps
- Short wins (90%+): add explicit checks that wrap axe-core rules (Document title, many contrast checks, label-in-name) and expose them via existing AccessibilityController endpoints.
- Medium-effort (50–85%): implement Playwright-driven interactive checks (keyboard navigation, non-text contrast via screenshots + OpenCV, pointer gesture emulation). These require test harnesses that can run sequences and capture screenshots/DOM states.
- Hard cases (<50%): timing-adjustable, live captions quality — mark for manual review and provide instrumentation artifacts (logs, screenshots, transcripts) to speed manual auditing.
- Stack alignment: Node service already uses Puppeteer + axe-core — implement additional JS evaluate scripts and image-processing microservices (Python OpenCV or Node canvas) for non-text contrast / OCR.

If desired I can:
- Produce a prioritized implementation plan (todo list) and create tasks (with estimated complexity) to add the highest-value rules.
- Scaffold one or two of the "mostly automatable" rules (example: label-in-name and document-title) as PR-ready changes.

Generated on: 2026-04-30
