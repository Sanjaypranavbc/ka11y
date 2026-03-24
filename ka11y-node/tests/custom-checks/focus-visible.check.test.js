'use strict';

const { run } = require('../../src/custom-checks/focus-visible.check');

function makePage(evalResult) {
  return { evaluate: jest.fn().mockResolvedValue(evalResult) };
}

describe('focus-visible.check (WCAG 2.4.7)', () => {
  test('passes when no elements lack focus indicators', async () => {
    const page = makePage([]);
    const result = await run(page);
    expect(result.successCriteriaId).toBe('2.4.7');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].impact).toBeNull();
  });

  test('fails when elements lack focus indicators', async () => {
    const page = makePage([
      { tagName: 'button', id: 'submit', html: '<button id="submit">Click</button>' },
      { tagName: 'a',      id: null,    html: '<a href="#">Link</a>' },
    ]);
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].impact).toBe('serious');
    expect(result.rules[0].reason).toMatch('2 focusable');
    expect(result.rules[0].reason).toMatch('<button');
  });

  test('reason names up to 3 violating elements', async () => {
    const page = makePage([
      { tagName: 'a',      id: null, html: '' },
      { tagName: 'button', id: null, html: '' },
      { tagName: 'input',  id: null, html: '' },
      { tagName: 'select', id: null, html: '' },
    ]);
    const result = await run(page);
    const reason = result.rules[0].reason;
    expect(reason).toMatch('4 focusable');
  });

  test('ruleId is custom-focus-visible', async () => {
    const page = makePage([]);
    const result = await run(page);
    expect(result.rules[0].ruleId).toBe('custom-focus-visible');
  });
});