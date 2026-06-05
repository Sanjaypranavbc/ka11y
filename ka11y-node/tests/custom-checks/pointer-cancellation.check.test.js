'use strict';

const { run } = require('../../src/custom-checks/pointer-cancellation.check');

// The check's page.evaluate returns { results, totalChecked }
function makePage(results, totalChecked) {
  const data = {
    results: results || [],
    totalChecked: totalChecked !== undefined ? totalChecked : (results || []).length,
  };
  return { evaluate: jest.fn().mockResolvedValue(data) };
}

describe('pointer-cancellation.check (WCAG 2.5.2)', () => {
  test('passes when no problematic pointer-down handlers are found', async () => {
    const page = makePage([]);
    const result = await run(page);
    expect(result.successCriteriaId).toBe('2.5.2');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].ruleId).toBe('custom-pointer-cancellation');
  });

  test('returns incomplete when mousedown-only handler is found', async () => {
    const page = makePage([
      { tagName: 'div', id: 'trigger', html: '<div id="trigger" onmousedown="doAction()">Click</div>' },
    ]);
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].impact).toBe('serious');
    expect(result.rules[0].reason).toContain('1 element(s)');
  });

  test('lists element tag in reason', async () => {
    const page = makePage([
      { tagName: 'button', id: null, html: '<button onmousedown="go()">Go</button>' },
    ]);
    const result = await run(page);
    expect(result.rules[0].reason).toContain('<button>');
  });

  test('impact is null on pass', async () => {
    const page = makePage([]);
    const result = await run(page);
    expect(result.rules[0].impact).toBeNull();
  });
});