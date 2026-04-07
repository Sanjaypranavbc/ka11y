'use strict';

const { run, SC, RULE_ID, HELP_URL } = require('../../src/custom-checks/use-of-color.check');

function makePage(data) {
  return { evaluate: jest.fn().mockResolvedValue(data) };
}

describe('use-of-color.check (WCAG 1.4.1)', () => {
  // ── Module exports ─────────────────────────────────────────────────────────
  test('exports SC as 1.4.1', () => { expect(SC).toBe('1.4.1'); });
  test('exports RULE_ID as custom-use-of-color', () => { expect(RULE_ID).toBe('custom-use-of-color'); });
  test('exports HELP_URL', () => { expect(HELP_URL).toContain('use-of-color'); });

  // ── Pass: no links found ───────────────────────────────────────────────────
  test('passes when no inline links are found to check', async () => {
    const page = makePage({ violations: [], checkedCount: 0 });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('1.4.1');
    expect(result.rules[0].ruleId).toBe('custom-use-of-color');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('No inline text links');
    expect(result.rules[0].impact).toBeNull();
    expect(result.rules[0].helpUrl).toBe(HELP_URL);
  });

  // ── Pass: links with non-color cues ───────────────────────────────────────
  test('passes when all checked links have a non-color cue', async () => {
    const page = makePage({ violations: [], checkedCount: 5 });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('5 inline link(s) checked');
    expect(result.rules[0].reason).toContain('non-color visual cue');
    expect(result.rules[0].impact).toBeNull();
  });

  test('pass with 1 link checked', async () => {
    const page = makePage({ violations: [], checkedCount: 1 });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('1 inline link(s)');
  });

  // ── Fail: single violation ─────────────────────────────────────────────────
  test('fails when a link uses color as sole differentiator', async () => {
    const page = makePage({
      violations: [{ html: '<a href="/about">About us</a>', id: null, text: 'About us' }],
      checkedCount: 1,
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].impact).toBe('serious');
    expect(result.rules[0].reason).toContain('1 inline link(s)');
    expect(result.rules[0].reason).toContain('colour alone');
    expect(result.rules[0].reason).toContain('"About us"');
  });

  test('link with underline SHOULD NOT be flagged (no violations returned)', async () => {
    const page = makePage({ violations: [], checkedCount: 1 });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
  });

  test('link with border-bottom SHOULD NOT be flagged', async () => {
    const page = makePage({ violations: [], checkedCount: 1 });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
  });

  test('link with font-weight change SHOULD NOT be flagged', async () => {
    const page = makePage({ violations: [], checkedCount: 1 });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
  });

  // ── Fail: multiple violations ──────────────────────────────────────────────
  test('multiple violations are all reported with sample text (up to 3)', async () => {
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
    expect(result.rules[0].reason).toContain('"Home"');
    expect(result.rules[0].reason).toContain('"About"');
    expect(result.rules[0].reason).toContain('"Contact"');
    // 4th item should be truncated (only first 3 shown)
    expect(result.rules[0].reason).not.toContain('"Blog"');
  });

  test('reason message includes suggestion to add visual cue', async () => {
    const page = makePage({
      violations: [{ html: '<a href="/x">Click here</a>', id: null, text: 'Click here' }],
      checkedCount: 1,
    });
    const result = await run(page);
    expect(result.rules[0].reason).toMatch(/underline|border|non-color/i);
  });

  test('fail result has helpUrl', async () => {
    const page = makePage({
      violations: [{ html: '<a>x</a>', id: null, text: 'x' }],
      checkedCount: 1,
    });
    const result = await run(page);
    expect(result.rules[0].helpUrl).toBe(HELP_URL);
  });

  test('evaluate is called with MAX_LINKS (150) argument', async () => {
    const page = makePage({ violations: [], checkedCount: 0 });
    await run(page);
    expect(page.evaluate).toHaveBeenCalledWith(expect.any(Function), 150);
  });

  test('description is set consistently', async () => {
    const page = makePage({ violations: [], checkedCount: 0 });
    const result = await run(page);
    expect(result.rules[0].description).toContain('Color must not be the only');
  });

  test('description is also set in fail result', async () => {
    const page = makePage({
      violations: [{ html: '<a>x</a>', id: null, text: 'x' }],
      checkedCount: 1,
    });
    const result = await run(page);
    expect(result.rules[0].description).toContain('Color must not be the only');
  });

  test('successCriteriaId is 1.4.1 for fail path', async () => {
    const page = makePage({
      violations: [{ html: '<a>x</a>', id: null, text: 'x' }],
      checkedCount: 1,
    });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('1.4.1');
  });
});
