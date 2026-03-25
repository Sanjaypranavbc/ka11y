'use strict';

const { run } = require('../../src/custom-checks/on-input.check');

function makePage({ inputs = [], url = 'https://example.com' } = {}) {
  const page = {
    url: jest.fn().mockReturnValue(url),
    evaluate: jest.fn().mockResolvedValueOnce(inputs).mockResolvedValue(undefined),
    keyboard: { type: jest.fn().mockResolvedValue(), press: jest.fn().mockResolvedValue() },
    on:  jest.fn(),
    off: jest.fn(),
  };
  return page;
}

const { SELECTOR: INPUT_SELECTOR } = (() => {
  const src = require('fs').readFileSync(require('path').resolve(__dirname, '../../src/custom-checks/on-input.check.js'), 'utf8');
  const match = src.match(/^const SELECTOR\s*=\s*([\s\S]*?)\.join\((.*?)\)/m);
  if (!match) return { SELECTOR: null };
  try {
    // eslint-disable-next-line no-new-func
    const SELECTOR = Function(`"use strict"; return (${match[1]}).join(${match[2]})`)();
    return { SELECTOR };
  } catch (_) { return { SELECTOR: null }; }
})();

describe('on-input.check (WCAG 3.2.2)', () => {
  test('SELECTOR (N8 fix): is a valid flat CSS selector with no stray :not() fragments', () => {
    // Regression test: the old pattern split ':not(...)' across array lines joined with '',
    // producing 'input:not(...):not(...):not(...), textarea...' which worked but was fragile.
    expect(INPUT_SELECTOR).not.toBeNull();
    expect(INPUT_SELECTOR.trimStart()).not.toMatch(/^,/);
    // Each comma-separated part must start with a valid tag or selector character
    const parts = INPUT_SELECTOR.split(',').map(s => s.trim());
    parts.forEach(p => {
      expect(p).toMatch(/^[a-zA-Z\[.#]/);
    });
  });

  test('passes when no inputs exist', async () => {
    const page = makePage({ inputs: [] });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('3.2.2');
    expect(result.rules[0].status).toBe('pass');
  });

  test('passes when inputs do not trigger context change', async () => {
    const page = makePage({
      inputs: [{ index: 0, tagName: 'input', type: 'text', id: 'name', html: '<input>' }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
  });

  test('always cleans up framenavigated listener', async () => {
    const page = makePage({ inputs: [] });
    await run(page);
    expect(page.off).toHaveBeenCalledWith('framenavigated', expect.any(Function));
  });

  test('ruleId is custom-on-input', async () => {
    const page = makePage({ inputs: [] });
    const result = await run(page);
    expect(result.rules[0].ruleId).toBe('custom-on-input');
  });
});