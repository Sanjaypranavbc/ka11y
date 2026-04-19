'use strict';

const { run } = require('../../src/custom-checks/meaningful-sequence.check');

function makePage(violations) {
  return { evaluate: jest.fn().mockResolvedValue(violations) };
}

describe('meaningful-sequence.check (WCAG 1.3.2)', () => {
  test('passes when no CSS reordering found', async () => {
    const page = makePage([]);
    const result = await run(page);
    expect(result.successCriteriaId).toBe('1.3.2');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].impact).toBeNull();
  });

  test('returns incomplete (not fail) when CSS order is detected', async () => {
    const page = makePage([
      { tagName: 'div', id: 'nav', display: 'flex', orders: [2, 1, 0], html: '<div>' },
    ]);
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].impact).toBe('moderate');
    expect(result.rules[0].reason).toMatch('1 flex/grid');
  });

  test('counts multiple violations', async () => {
    const page = makePage([
      { tagName: 'div', id: null, display: 'flex',   orders: [1, 0], html: '' },
      { tagName: 'div', id: null, display: 'grid',   orders: [2, 0], html: '' },
    ]);
    const result = await run(page);
    expect(result.rules[0].reason).toMatch('2 flex/grid');
  });

  test('ruleId is custom-meaningful-sequence', async () => {
    const page = makePage([]);
    const result = await run(page);
    expect(result.rules[0].ruleId).toBe('custom-meaningful-sequence');
  });

  test('Japanese reason localizes structured reorder details', async () => {
    const page = makePage([
      { tagName: 'div', id: null, display: 'flex', reasonCode: 'mixed-floats', html: '' },
    ]);
    const result = await run(page, { lang: 'ja' });
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('float 指定された兄弟要素');
    expect(result.rules[0].reason).not.toContain('Container has mixed floated');
  });
});
