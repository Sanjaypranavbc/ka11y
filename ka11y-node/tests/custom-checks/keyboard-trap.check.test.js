'use strict';

const { run } = require('../../src/custom-checks/keyboard-trap.check');

function makePage({ activeElements = [] } = {}) {
  let tabCount = 0;
  const page = {
    evaluate: jest.fn()
      .mockResolvedValueOnce(undefined) // body.focus()
      .mockImplementation(() => {
        const info = activeElements[tabCount % activeElements.length] || null;
        return Promise.resolve(info);
      }),
    keyboard: { press: jest.fn().mockResolvedValue() },
  };
  // Each press('Tab') increments tabCount
  page.keyboard.press.mockImplementation(() => {
    tabCount++;
    return Promise.resolve();
  });
  return page;
}

describe('keyboard-trap.check (WCAG 2.1.2)', () => {
  test('passes when focus moves freely', async () => {
    // Simulate 5 different elements rotating
    const elements = [
      { key: 'a|BUTTON|', html: '<button>A</button>', tagName: 'button' },
      { key: 'b|BUTTON|', html: '<button>B</button>', tagName: 'button' },
      { key: 'c|A|',      html: '<a>C</a>',           tagName: 'a' },
      null,
    ];
    const page = makePage({ activeElements: elements });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('2.1.2');
    expect(result.rules[0].status).toBe('pass');
  });

  test('ruleId is custom-keyboard-trap', async () => {
    const page = makePage({ activeElements: [null] });
    const result = await run(page);
    expect(result.rules[0].ruleId).toBe('custom-keyboard-trap');
  });
});