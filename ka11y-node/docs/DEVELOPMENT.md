# Developer Guide for ka11y-node

This document provides technical details for developers working on the **ka11y-node** service.

## Core Stack
- **Framework**: Express.js
- **Automation**: Puppeteer (Headless Chromium)
- **Audit Engine**: axe-core
- **Custom Logic**: Plain JavaScript (running in-browser via `page.evaluate`)

---

## 1. Deep Dive: AccessibilityService
The heart of the application is `src/services/accessibility.service.js`. This class manages the Puppeteer browser lifecycle and coordinates the execution of axe-core and our custom checks.

### Key Methods
- `analyseUrl(url, criteriaId, lang)`: The primary entry point for single-page audits. It handles SSRF protection, browser launch, axe injection, and check execution.
- `analyseUrlFlat(url, level, lang, options)`: Used for multi-page audits. It performs a **Bounded BFS** traversal.
- `_injectAxe(page)`: Injects the `axe.min.js` bundle into the page. We use a local copy to ensure stability and performance.

---

## 2. Rule Integration Strategy
We categorize rules into three types:

### Standard axe-core Rules
If a rule is already covered by axe-core, we simply ensure its tag is included in our configuration (`src/config/app.config.js`). We map axe results to our unified schema in `src/utils/axeResultMapper.js`.

### Static Custom Checks
These are rules that can be evaluated by inspecting the DOM at a specific point in time without user interaction.
- **Location**: `src/custom-checks/*.check.js`
- **Execution**: They run in parallel using `Promise.allSettled`.
- **Constraint**: Must not mutate the page state.

### Interactive Custom Checks
These rules require simulating user actions (focus, typing, clicking).
- **Location**: `src/custom-checks/` (identified by `MODE = 'interactive'`)
- **Execution**: They run **sequentially** to prevent focus/interaction collisions.
- **Patterns**: Used for keyboard trap detection and focus visibility.

---

## 3. Crawling Mechanics
Our crawler (`src/utils/crawl.js`) implements a Breadth-First Search:
1.  **Discovery**: Extracts all `<a>` tags from the current page.
2.  **Filtering**: Only follows internal links (same origin) and respects `max_depth`.
3.  **Efficiency**: Reuses the same browser instance across all pages in a job.
4.  **Budgeting**: Enforces `flatCrawlBudgetMs` to prevent runaway audits on very large sites.

---

## 4. Documentation Registry
For more details on specific rules, see these internal documents:
- [**Rule Analysis**](./RULE_ANALYSIS.md): Detailed breakdown of every custom check's logic and flow.
- [**Axe-core Manual Guide**](./axe_core_manual_guide.md): Reference for standard axe rules.
- [**Manual Intervention**](./WCAG%20_Criteria%20Requiring%20_Manual%20Intervention.md): Guidelines for rules that automation cannot fully confirm.

---

## 5. Security (SSRF Guard)
We take SSRF seriously. Every URL is validated against a blacklist of private IP ranges (`_PRIVATE_IP_RE` in `AccessibilityService.js`) at two stages:
1.  **DNS Resolution**: Before Puppeteer even starts.
2.  **Request Interception**: Puppeteer intercepts every outgoing request (including redirects) and aborts if it targets a private IP.
