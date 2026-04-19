'use strict';

const { run, SC, RULE_ID } = require('../../src/custom-checks/use-of-color.check');

function makePage(data) {
  return { evaluate: jest.fn().mockResolvedValue(data) };
}

describe('use-of-color.check (WCAG 1.4.1)', () => {
  test('successCriteriaId is 1.4.1', async () => {
    const page = makePage({ violations: [], checkedCount: 0 });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('1.4.1');
  });

  test('ruleId is custom-use-of-color', async () => {
    const page = makePage({ violations: [], checkedCount: 0 });
    const result = await run(page);
    expect(result.rules[0].ruleId).toBe('custom-use-of-color');
  });

  test('passes when no inline links are found to check', async () => {
    const page = makePage({ violations: [], checkedCount: 0 });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('No inline text links');
  });

  test('passes when all checked links have a non-color cue', async () => {
    const page = makePage({ violations: [], checkedCount: 5 });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('5 inline link(s) checked');
    expect(result.rules[0].reason).toContain('non-color visual cue');
  });

  test('link with only color difference (no underline/border/font-weight) SHOULD be flagged', async () => {
    // Simulate browser returning a violation for a link with no non-color cue
    const page = makePage({
      violations: [{ html: '<a href="/about">About us</a>', id: null, text: 'About us' }],
      checkedCount: 1,
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].impact).toBe('serious');
    expect(result.rules[0].reason).toContain('1 inline link(s)');
    expect(result.rules[0].reason).toContain('colour alone');
  });

  test('link with underline SHOULD NOT be flagged (no violations returned)', async () => {
    // Browser-side code detects text-decoration-line !== 'none' → not a violation
    const page = makePage({ violations: [], checkedCount: 1 });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
  });

  test('link with border-bottom SHOULD NOT be flagged', async () => {
    // Browser-side code detects borderBottomWidth > 0 → not a violation
    const page = makePage({ violations: [], checkedCount: 1 });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
  });

  test('link with font-weight change SHOULD NOT be flagged', async () => {
    // Browser-side code detects linkFontWeight >= ancestorFontWeight + 200 → not a violation
    const page = makePage({ violations: [], checkedCount: 1 });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
  });

  test('multiple violations are all reported with sample text', async () => {
    const page = makePage({
      violations: [
        { html: '<a href="/a">Home</a>', id: null, text: 'Home' },
        { html: '<a href="/b">About</a>', id: null, text: 'About' },
        { html: '<a href="/c">Contact</a>', id: null, text: 'Contact' },
        { html: '<a href="/d">Blog</a>', id: null, text: 'Blog' },
      ],
      checkedCount: 10,
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('4 inline link(s)');
  });

  test('reason message includes suggestion to add visual cue', async () => {
    const page = makePage({
      violations: [{ html: '<a href="/x">Click here</a>', id: null, text: 'Click here' }],
      checkedCount: 1,
    });
    const result = await run(page);
    expect(result.rules[0].reason).toMatch(/underline|border|non-color/i);
  });
});
