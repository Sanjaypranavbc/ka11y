# Getting Started with ka11y-node

Welcome to the **ka11y-node** service! This guide will help you understand what this project is about, how it works internally, and how you can contribute as a Node.js developer.

---

## 1. What is this project?

**ka11y-node** is a high-performance accessibility auditing engine. It provides a REST API that:
1.  **Analyzes raw HTML**: Accepts a string of HTML and returns accessibility findings.
2.  **Crawls URLs**: Uses Puppeteer to visit live websites, injects `axe-core`, and runs custom accessibility checks.
3.  **Unified Results**: Merges standard `axe-core` findings with a suite of **32+ custom WCAG checks** specifically designed for edge cases that standard tools often miss (like focus traps, color-only links, and complex ARIA relationships).

It serves as the DOM-heavy "technical auditor" in the broader ka11y platform, complementing the visual/multimodal analysis performed by the Python engine.

---

## 2. Internal Architecture

The service is built with **Node.js**, **Express**, and **Puppeteer**.

### Request Flow
1.  **Controller (`src/controllers/`)**: Validates input and enforces **SSRF Guards** to prevent requests to private IP ranges.
2.  **Service (`src/services/accessibility.service.js`)**: 
    *   Launches a Puppeteer browser instance.
    *   Navigates to the target URL or sets the HTML content.
    *   **axe-core Injection**: Injects the `axe.min.js` bundle into the browser context.
    *   **Parallel Execution**: Runs `axe.run()` and all **Static Custom Checks** in parallel.
    *   **Sequential Execution**: Runs **Interactive Custom Checks** (which move focus or change input) one-by-one to avoid state collisions.
3.  **Mapper (`src/utils/axeResultMapper.js`)**: Normalizes findings from axe-core and custom checks into a unified JSON format mapped to WCAG Success Criteria.

---

## 3. How Crawling Works

When you use the `/analyse-url` or `/analyse-url-flat` endpoints, the service uses a **Breadth-First Search (BFS)** strategy:
-   **Universal Discovery**: If `max_depth > 0`, it follows internal links up to the specified depth.
-   **Resource Sharing**: A single browser instance is reused across all crawled pages to minimize overhead.
-   **SSRF Protection**: Redirect-time hops are intercepted to ensure the browser never touches private infrastructure.

---

## 4. WCAG Coverage

### What's Covered
-   **100+ Standard axe-core Rules**: Covering WCAG 2.0/2.1/2.2 Level A, AA, and some AAA.
-   **32 Custom Checks**: Specialized auditors for:
    *   **Focus Management**: `keyboard-trap`, `focus-visible`, `focus-appearance`.
    *   **Interactive Behavior**: `on-focus`, `on-input`.
    *   **Structural Heuristics**: `audio-transcript`, `images-of-text`, `use-of-color`.
    *   **Advanced WCAG 2.2**: `target-size`, `dragging-movements`.

### What's Missing / Next Steps
-   **Shadow DOM Piercing**: Some custom checks only scan the main document. Piercing closed shadow roots is a high-priority enhancement.
-   **Dynamic State Snapshots**: Currently, most checks run on the initial page load. capturing state changes *during* user interaction is limited to the specific interactive checks.

---

## 5. How to Integrate a New Audit Rule

Adding a new rule is straightforward:

1.  **Create the Check**: Add a new file in `src/custom-checks/your-rule.check.js`.
2.  **Implement the `run` Function**:
    ```javascript
    async function run(page, context) {
      const issues = await page.evaluate(() => {
        // Your browser-side detection logic here
        return document.querySelectorAll('.bad-element');
      });
      
      return {
        successCriteriaId: 'X.X.X',
        rules: [{
          ruleId: 'custom-your-rule',
          status: issues.length > 0 ? 'fail' : 'pass',
          elements: issues.map(el => ({ html: el.outerHTML }))
        }]
      };
    }
    module.exports = { run, SC: 'X.X.X', RULE_ID: 'custom-your-rule' };
    ```
3.  **Register**: Add your rule ID to `STATIC_ORDER` or `INTERACTIVE_ORDER` in `src/custom-checks/index.js`.
4.  **Test**: Add a unit test in `tests/custom-checks/your-rule.check.test.js`.

---

## 7. Next Steps
For a deeper technical dive into specific service methods, crawling logic, and SSRF security details, check out the [**Developer Guide**](./docs/DEVELOPMENT.md).


### Accessibility Linting (AccessLint)
We have integrated `jsx-a11y` rules into our ESLint configuration to ensure the code we write follows accessibility best practices.
```bash
# Run the linter
npm run lint

# Run accessibility-specific linting
npm run accesslint
```

### Self-Test
Run a comprehensive check of our rule coverage against an intentionally broken HTML fixture:
```bash
npm run selftest
```

### Tests
We use **Jest** for unit and integration testing. We have also integrated `@accesslint/jest` to allow for easy accessibility assertions within our test suite.
```bash
npm test
```

Example usage in a test:
```javascript
const { toBeAccessible } = require('@accesslint/jest');
expect.extend({ toBeAccessible });

test('it is accessible', async () => {
  await expect('<button>Click me</button>').toBeAccessible();
});
```

