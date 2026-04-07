'use strict';

const { run, SC, RULE_ID, HELP_URL } = require('../../src/custom-checks/meaningful-sequence.check');

function makePage(violations) {
  return { evaluate: jest.fn().mockResolvedValue(violations) };
}

describe('meaningful-sequence.check (WCAG 1.3.2)', () => {
  // ── Module exports ─────────────────────────────────────────────────────────
  test('exports SC as 1.3.2', () => { expect(SC).toBe('1.3.2'); });
  test('exports RULE_ID as custom-meaningful-sequence', () => { expect(RULE_ID).toBe('custom-meaningful-sequence'); });
  test('exports HELP_URL', () => { expect(HELP_URL).toContain('meaningful-sequence'); });

  // ── Pass path ──────────────────────────────────────────────────────────────
  test('passes when no CSS reordering found', async () => {
    const page = makePage([]);
    const result = await run(page);
    expect(result.successCriteriaId).toBe('1.3.2');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].impact).toBeNull();
  });

  test('pass reason mentions how many containers were inspected', async () => {
    const page = makePage([]);
    const result = await run(page);
    expect(result.rules[0].reason).toContain('500');
    expect(result.rules[0].reason).toContain('flex/grid');
  });

  test('ruleId is custom-meaningful-sequence', async () => {
    const page = makePage([]);
    const result = await run(page);
    expect(result.rules[0].ruleId).toBe('custom-meaningful-sequence');
  });

  test('helpUrl is set in pass result', async () => {
    const page = makePage([]);
    const result = await run(page);
    expect(result.rules[0].helpUrl).toBe(HELP_URL);
  });

  // ── Violation path ─────────────────────────────────────────────────────────
  test('returns incomplete (not fail) when CSS order is detected', async () => {
    const page = makePage([
      { tagName: 'div', id: 'nav', display: 'flex', orders: [2, 1, 0], html: '<div>', reason: 'CSS order property reorders' },
    ]);
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].impact).toBe('moderate');
    expect(result.rules[0].reason).toMatch('1 flex/grid');
  });

  test('reason includes violation sample text (up to 3)', async () => {
    const page = makePage([
      { tagName: 'div', id: null, display: 'flex', orders: [1, 0], html: '', reason: 'flex-direction: row-reverse reverses DOM order' },
      { tagName: 'div', id: null, display: 'grid', orders: [2, 0], html: '', reason: 'CSS order property reorders' },
      { tagName: 'section', id: null, display: 'flex', orders: [3, 0, 1], html: '', reason: 'flex-direction: column-reverse reverses DOM order' },
      { tagName: 'article', id: null, display: 'flex', orders: [4, 0], html: '', reason: 'another reorder' },
    ]);
    const result = await run(page);
    expect(result.rules[0].reason).toContain('4 flex/grid');
    // Should contain up to 3 sample reasons
    expect(result.rules[0].reason).toContain('flex-direction');
  });

  test('counts multiple violations', async () => {
    const page = makePage([
      { tagName: 'div', id: null, display: 'flex',   orders: [1, 0], html: '', reason: 'row-reverse' },
      { tagName: 'div', id: null, display: 'grid',   orders: [2, 0], html: '', reason: 'grid reorder' },
    ]);
    const result = await run(page);
    expect(result.rules[0].reason).toMatch('2 flex/grid');
  });

  test('incomplete result has helpUrl', async () => {
    const page = makePage([
      { tagName: 'div', id: null, display: 'flex', orders: [1, 0], html: '', reason: 'reversed' },
    ]);
    const result = await run(page);
    expect(result.rules[0].helpUrl).toBe(HELP_URL);
  });

  test('description is set in both pass and incomplete', async () => {
    const passPage = makePage([]);
    const passResult = await run(passPage);
    expect(passResult.rules[0].description).toContain('programmatically determinable');

    const failPage = makePage([{ tagName: 'div', id: null, display: 'flex', orders: [1,0], html: '', reason: 'reversed' }]);
    const failResult = await run(failPage);
    expect(failResult.rules[0].description).toContain('programmatically determinable');
  });

  test('evaluate is called with MAX_CONTAINERS (500) argument', async () => {
    const page = makePage([]);
    await run(page);
    expect(page.evaluate).toHaveBeenCalledWith(expect.any(Function), 500);
  });

  test('successCriteriaId is always 1.3.2', async () => {
    const pass = await run(makePage([]));
    expect(pass.successCriteriaId).toBe('1.3.2');

    const incomplete = await run(makePage([{ tagName: 'div', id: null, display: 'flex', orders: [1,0], html: '', reason: 'x' }]));
    expect(incomplete.successCriteriaId).toBe('1.3.2');
  });

  test('single violation still produces rules array with one rule', async () => {
    const page = makePage([
      { tagName: 'nav', id: 'main-nav', display: 'flex', flexDir: 'row-reverse', orders: null, reason: 'row-reverse reverses DOM', html: '<nav>' },
    ]);
    const result = await run(page);
    expect(result.rules).toHaveLength(1);
    expect(result.rules[0].status).toBe('incomplete');
  });
});
