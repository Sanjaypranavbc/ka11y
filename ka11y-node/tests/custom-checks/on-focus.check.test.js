'use strict';

const { run } = require('../../src/custom-checks/on-focus.check');

function makePage({ focusable = [], url = 'https://example.com', navigates = false } = {}) {
  let navListener = null;
  const page = {
    url: jest.fn().mockReturnValue(url),
    evaluate: jest.fn(),
    on: jest.fn((event, cb) => { if (event === 'framenavigated') navListener = cb; }),
    off: jest.fn(),
  };

  // First evaluate call: get focusable elements list
  page.evaluate
    .mockResolvedValueOnce(focusable)
    .mockImplementation(() => {
      if (navigates && navListener) navListener();
      return Promise.resolve();
    });

  return page;
}

const { SELECTOR } = (() => {
  // Re-read the SELECTOR constant from source for validation
  const src = require('fs').readFileSync(require('path').resolve(__dirname, '../../src/custom-checks/on-focus.check.js'), 'utf8');
  const match = src.match(/^const SELECTOR\s*=\s*([\s\S]*?)\.join\((.*?)\)/m);
  if (!match) return { SELECTOR: null };
  try {
    // Safely evaluate the array literal and join call to get the final selector string
    // eslint-disable-next-line no-new-func
    const SELECTOR = Function(`"use strict"; return (${match[1]}).join(${match[2]})`)();
    return { SELECTOR };
  } catch (_) { return { SELECTOR: null }; }
})();

describe('on-focus.check (WCAG 3.2.1)', () => {
  test('passes when no context changes occur', async () => {
    const page = makePage({ focusable: [] });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('3.2.1');
    expect(result.rules[0].status).toBe('pass');
  });

  test('ruleId is custom-on-focus', async () => {
    const page = makePage({ focusable: [] });
    const result = await run(page);
    expect(result.rules[0].ruleId).toBe('custom-on-focus');
  });

  test('always calls page.off to clean up listener', async () => {
    const page = makePage({ focusable: [] });
    await run(page);
    expect(page.off).toHaveBeenCalledWith('framenavigated', expect.any(Function));
  });

  test('SELECTOR (N7 fix): does not start with a comma and is a valid CSS selector string', () => {
    // Regression test for the leading-comma bug where selector was `, button:not(...)` etc.
    expect(SELECTOR).not.toBeNull();
    expect(SELECTOR.trimStart()).not.toMatch(/^,/);
    // Each part must be non-empty when split by ', '
    const parts = SELECTOR.split(',').map(s => s.trim());
    expect(parts.every(p => p.length > 0)).toBe(true);
  });
});