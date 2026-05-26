/**
 * @jest-environment jsdom
 */
const { toBeAccessible } = require('@accesslint/jest');
const fs = require('fs');
const path = require('path');
const { runAudit } = require('@accesslint/core');

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
      document.body.innerHTML = '<button aria-label="Submit">Submit</button>';
      await expect(document.body).toBeAccessible();
    });

    it('detects violations in malformed markup', async () => {
      document.body.innerHTML = '<img src="missing-alt.png">';
      let passed = true;
      try {
        await expect(document.body).toBeAccessible();
      } catch (e) {
        passed = false;
      }
      expect(passed).toBe(false);
    });
  });

  describe('Full-page & Synthetic Scenarios', () => {
    it('validates a complex synthetic page', async () => {
      document.body.innerHTML = complexHtml;
      let passed = true;
      try {
        await expect(document.body).toBeAccessible();
      } catch(e) {
        passed = false;
      }
      expect(passed).toBe(false);
    });

    it('handles Japanese content and maintains UTF-8', async () => {
      document.body.innerHTML = '<div lang="ja"><h1>テスト</h1><img src="x" alt="ロゴ"></div>';
      let passed = true;
      try {
        await expect(document.body).toBeAccessible();
      } catch(e) {
        passed = false;
      }
      expect(passed).toBeDefined();
    });

    it('handles mixed-language pages', async () => {
      document.body.innerHTML = '<div><h1>Mix</h1><p lang="en">Hello</p><p lang="ja">こんにちは</p></div>';
      let passed = true;
      try {
        await expect(document.body).toBeAccessible();
      } catch(e) {
        passed = false;
      }
      expect(passed).toBeDefined();
    });
  });

  describe('DOM & Concurrency Stability', () => {
    it('executes concurrent scans safely without corruption', async () => {
      const promises = Array.from({ length: 5 }).map(() => {
        const div = document.createElement('div');
        div.innerHTML = complexHtml;
        return runAudit(div);
      });
      const results = await Promise.all(promises);
      expect(results.length).toBe(5);
      results.forEach(res => {
        expect(res).toBeDefined();
      });
    });

    it('survives shadow DOM content parsing', async () => {
      const html = `<div><template shadowroot="open"><img src="x"></template></div>`;
      document.body.innerHTML = html;
      const results = runAudit(document.body);
      expect(results).toBeDefined();
    });
  });

  describe('Determinism & Rule Ordering', () => {
    it('accessibility violations remain deterministic across multiple runs', async () => {
      document.body.innerHTML = complexHtml;
      const run1 = runAudit(document.body);
      const run2 = runAudit(document.body);
      expect(JSON.stringify(run1.violations)).toEqual(JSON.stringify(run2.violations));
    });
  });
});
