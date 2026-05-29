'use strict';

const { run, SC, RULE_ID, HELP_URL } = require('../../src/custom-checks/keyboard-trap.check');

jest.mock('../../src/custom-checks/sharedAssets', () => {
  const actual = jest.requireActual('../../src/custom-checks/sharedAssets');
  return {
    ...actual,
    settle: jest.fn().mockResolvedValue(undefined),
  };
});

/**
 * Creates a mock page for keyboard-trap tests.
 */
function makePage({ tabElements = [], shiftTabElements = [] } = {}) {
  let phase = 'tab'; // 'tab' or 'shift'
  let tabIdx = 0;
  let shiftIdx = 0;

  const page = {
    url: jest.fn().mockReturnValue('https://example.com'),
    evaluate: jest.fn().mockImplementation((fn) => {
      const src = String(fn);
      if (src.includes('document.body.focus')) return Promise.resolve(undefined);
      if (src.includes('dialog[open]') || src.includes('[role="dialog"]')) return Promise.resolve([]);
      if (src.includes('iframe')) return Promise.resolve([]);
      if (src.includes('script-key-suppression')) return Promise.resolve([]);

      const isVerification = src.includes('afterEscape') || src.includes('escaped');

      if (phase === 'tab') {
        // If it's a verification call, we should return the element that was JUST focused
        // to simulate a trap, or a different one to simulate a successful escape.
        // For the tests to fail (trap confirmed), we return the same element.
        if (isVerification) {
          const val = tabElements[tabIdx - 1];
          return Promise.resolve(val ? val.key : null);
        }
        const val = tabElements[tabIdx++];
        return Promise.resolve(val ? { ...val, insideWidget: false } : null);
      }
      // phase === 'shift'
      if (isVerification) {
        const val = shiftTabElements[shiftIdx - 1];
        return Promise.resolve(val ? val.key : null);
      }
      const val = shiftTabElements[shiftIdx++];
      return Promise.resolve(val ? { ...val, insideWidget: false } : null);
    }),
    keyboard: {
      press: jest.fn().mockResolvedValue(undefined),
      down: jest.fn().mockImplementation((key) => {
        if (key === 'Shift' && phase !== 'shift') phase = 'shift';
        return Promise.resolve();
      }),
      up: jest.fn().mockResolvedValue(undefined),
    },
    frames: jest.fn().mockReturnValue([]),
    mainFrame: jest.fn().mockReturnValue(null),
  };

  return page;
}

/**
 * Creates a page mock specifically for the arrow-trap/ARIA widget phase.
 */
function makeArrowTrapPage() {
  const responses = [
    undefined, // body.focus()
    null,      // forward Tab exits immediately
    null,      // Shift+Tab exits immediately
    [],        // tree widgets
    [],        // grid widgets
    [],        // listbox widgets
    [],        // menu widgets
    [{ id: 'tabs', html: '<div role="tablist">...</div>', selector: '#tabs', role: 'tablist' }],
    undefined, // focus widget
    { key: '10:DIV', insideWidget: true },  // before ArrowDown
    '10:DIV',  // after ArrowDown -> trap
    '10:DIV',  // after ArrowUp -> trap
    { key: '10:DIV', insideWidget: true },  // after Tab -> trap
    [],        // radiogroup widgets
    [],        // dialogs
    [],        // non-modal
    [],        // f58
  ];
  let idx = 0;

  return {
    url: jest.fn().mockReturnValue('https://example.com'),
    evaluate: jest.fn().mockImplementation((fn) => {
      const src = String(fn);
      if (src.includes('dialog[open]')) return Promise.resolve([]);
      // Heuristic: if it's the non-modal popup scan, return [] to avoid extra loops
      if (src.includes('.modal, .dialog')) return Promise.resolve([]);
      return Promise.resolve(responses[idx++] ?? null);
    }),
    keyboard: {
      press: jest.fn().mockResolvedValue(undefined),
      down: jest.fn().mockResolvedValue(undefined),
      up: jest.fn().mockResolvedValue(undefined),
    },
    frames: jest.fn().mockReturnValue([]),
    mainFrame: jest.fn().mockReturnValue(null),
  };
}

describe('keyboard-trap.check (WCAG 2.1.2)', () => {
  test('exports metadata', () => {
    expect(SC).toBe('2.1.2');
    expect(RULE_ID).toBe('custom-keyboard-trap');
    expect(HELP_URL).toContain('keyboard-trap');
  });

  test('passes when forward Tab focus moves freely', async () => {
    const page = makePage({
      tabElements: [
        { key: '1:A', html: '<a>A</a>', tagName: 'A' },
        { key: '2:BUTTON', html: '<button>B</button>', tagName: 'BUTTON' },
        null,
      ]
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
  });

  test('detects 1-element stuck trap', async () => {
    const stuck = { key: '1:X', html: '<button>X</button>', tagName: 'BUTTON' };
    const page = makePage({
      tabElements: [stuck, stuck, stuck, stuck], 
      shiftTabElements: [stuck]
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
  });

  test('fail result has impact: critical', async () => {
    const stuck = { key: 'BUTTON:modal-close', html: '<button id="modal-close">Close</button>', tagName: 'button' };
    const page = makePage({
      tabElements: [stuck, stuck, stuck, stuck],
      shiftTabElements: [stuck]
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].impact).toBe('critical');
    expect(result.rules[0].reason).toContain('modal-close');
  });

  test('detects two-element cycle trap', async () => {
    const a = { key: '1:A', html: '<a>A</a>', tagName: 'a' };
    const b = { key: '2:B', html: '<b>B</b>', tagName: 'b' };
    const page = makePage({
      tabElements: [a, b, a, b],
      shiftTabElements: [b, a]
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
  });

  test('Japanese reason localizes arrow-trap details', async () => {
    const page = makeArrowTrapPage();
    const result = await run(page, { lang: 'ja' });
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('矢印キー操作');
    expect(result.rules[0].reason).toContain('[role="tablist"]');
  });

  test('reports scripted Tab/Escape suppression as incomplete', async () => {
    const page = {
      evaluate: jest.fn().mockImplementation((fn) => {
        const str = fn.toString();
        if (str.includes('document.body.focus')) return Promise.resolve(undefined);
        if (str.includes('document.activeElement')) return Promise.resolve(null);
        if (str.includes('script-key-suppression')) {
          return Promise.resolve([{ type: 'script-key-suppression', keys: 'Tab', snippet: 'event.preventDefault()' }]);
        }
        return Promise.resolve([]);
      }),
      keyboard: {
        press: jest.fn().mockResolvedValue(undefined),
        down: jest.fn().mockResolvedValue(undefined),
        up: jest.fn().mockResolvedValue(undefined),
      },
      frames: jest.fn().mockReturnValue([]),
      mainFrame: jest.fn().mockReturnValue(null),
    };
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('preventDefault');
  });
});
