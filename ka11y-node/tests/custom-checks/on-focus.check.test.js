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
});