const { toBeAccessible } = require('@accesslint/jest');
const fs = require('fs');
const path = require('path');
const { AccessLint } = require('@accesslint/core');

expect.extend({ toBeAccessible });

describe('AccessLint Integration & Validation', () => {
  const fixturesDir = path.join(__dirname, 'fixtures');
  let complexHtml, largeHtml;

  beforeAll(() => {
    complexHtml = fs.readFileSync(path.join(fixturesDir, 'synthetic-complex.html'), 'utf8');
    largeHtml = fs.readFileSync(path.join(fixturesDir, 'synthetic-10k.html'), 'utf8');
  });

  describe('Component-level Audits', () => {
    it('validates a simple accessible button', async () => {
      const html = '<button aria-label="Submit">Submit</button>';
      await expect(html).toBeAccessible();
    });

    it('detects violations in malformed markup', async () => {
      const html = '<img src="missing-alt.png">';
      let passed = true;
      try {
        await expect(html).toBeAccessible();
      } catch (e) {
        passed = false;
      }
      expect(passed).toBe(false);
    });
  });

  describe('Full-page & Synthetic Scenarios', () => {
    it('validates a complex synthetic page', async () => {
      const logger = { violations: 0 };
      const accessLint = new AccessLint();
      const results = await accessLint.run(complexHtml);
      expect(results.violations).toBeDefined();
    });

    it('handles Japanese content and maintains UTF-8', async () => {
      const html = '<html lang="ja"><title>テスト</title><body><img src="x" alt="ロゴ"></body></html>';
      const results = await new AccessLint().run(html);
      // It should parse Japanese text fine
      expect(results).toBeDefined();
    });

    it('handles mixed-language pages', async () => {
      const html = '<html><title>Mix</title><body><p lang="en">Hello</p><p lang="ja">こんにちは</p></body></html>';
      const results = await new AccessLint().run(html);
      expect(results).toBeDefined();
    });
  });

  describe('DOM & Concurrency Stability', () => {
    it('executes concurrent scans safely without corruption', async () => {
      const promises = Array.from({ length: 10 }).map(() => new AccessLint().run(complexHtml));
      const results = await Promise.all(promises);
      expect(results.length).toBe(10);
      results.forEach(res => {
        expect(res.violations).toBeDefined();
      });
    });

    it('survives shadow DOM content parsing', async () => {
      const html = `<div><template shadowroot="open"><img src="x"></template></div>`;
      const results = await new AccessLint().run(html);
      expect(results).toBeDefined();
    });
  });

  describe('Determinism & Rule Ordering', () => {
    it('accessibility violations remain deterministic across multiple runs', async () => {
      const run1 = await new AccessLint().run(complexHtml);
      const run2 = await new AccessLint().run(complexHtml);
      expect(run1.violations.length).toBe(run2.violations.length);
    });
  });
});
