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

describe('on-input.check (WCAG 3.2.2)', () => {
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