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
 *
 * tabElements:       sequence of activeElement infos returned during forward Tab presses.
 *                    Each entry: { key, html, tagName } or null (focus left page).
 * shiftTabElements:  sequence of activeElement infos returned during Shift+Tab presses.
 */
function makePage({ tabElements = [], shiftTabElements = [] } = {}) {
  let phase = 'tab'; // 'tab' or 'shift'
  let tabIdx = 0;
  let shiftIdx = 0;
  let tabEvalIdx = 0;
  let shiftEvalIdx = 0;

  // Each forward Tab press returns the next item from tabElements
  // Each Shift+Tab press returns the next item from shiftTabElements
  const page = {
    url: jest.fn().mockReturnValue('https://example.com'),
    evaluate: jest.fn().mockImplementation((fn) => {
      const src = String(fn);
      // Heuristic detection of which branch the check is running
      if (src.includes('document.body.focus')) return Promise.resolve(undefined);
      if (src.includes('dialog[open]') || src.includes('[role="dialog"]')) return Promise.resolve([]);
      if (src.includes('iframe')) return Promise.resolve([]);
      if (src.includes('script-key-suppression')) return Promise.resolve([]);

      if (phase === 'tab') {
        const val = tabElements[tabIdx];
        // After each evaluate(activeElement), advance index if it was a real query
        if (src.includes('document.activeElement')) {
          tabIdx++;
        }
        return Promise.resolve(val ? { ...val, insideWidget: false } : null);
      }
      // phase === 'shift'
      const val = shiftTabElements[shiftIdx];
      if (src.includes('document.activeElement')) {
        shiftIdx++;
      }
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
    // MERGED: focus widget + capture before arrows (Call 2 for tablist)
    { key: '10:DIV', insideWidget: true },
    '10:DIV',  // after ArrowDown -> trap
    '10:DIV',  // after ArrowUp -> trap
    { key: '10:DIV', insideWidget: true },  // after Tab -> trap
    [],        // radiogroup widgets
    [],        // treegrid
    [],        // composite
    [],        // dialogs
    [],        // non-modal
    [],        // f58
  ];
  let idx = 0;

  return {
    url: jest.fn().mockReturnValue('https://example.com'),
    evaluate: jest.fn().mockImplementation(() => Promise.resolve(responses[idx++] ?? null)),
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
  // ── Module exports ─────────────────────────────────────────────────────────
  test('exports SC as 2.1.2', () => { expect(SC).toBe('2.1.2'); });
  test('exports RULE_ID as custom-keyboard-trap', () => { expect(RULE_ID).toBe('custom-keyboard-trap'); });
  test('exports HELP_URL', () => { expect(HELP_URL).toContain('keyboard-trap'); });

  // ── Pass paths ─────────────────────────────────────────────────────────────
  test('passes when forward Tab focus moves freely', async () => {
    const page = makePage({
      tabElements: [
        { key: '1:A', html: '<a>A</a>', tagName: 'A' },
        { key: '2:BUTTON', html: '<button>B</button>', tagName: 'BUTTON' },
        null, // left page
      ]
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
  });

  test('ruleId is custom-keyboard-trap', async () => {
    const page = makePage({ tabElements: [null] });
    const result = await run(page);
    expect(result.rules[0].ruleId).toBe('custom-keyboard-trap');
  });

  test('passes when no elements are focused at all', async () => {
    const page = makePage({ tabElements: [null], shiftTabElements: [null] });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
  });

  test('passes reason mentions no traps detected', async () => {
    const page = makePage({ tabElements: [null], shiftTabElements: [null] });
    const result = await run(page);
    expect(result.rules[0].reason).toContain('No keyboard focus traps');
  });

  // ── Fail paths: Tabbing ────────────────────────────────────────────────────
  test('detects 1-element stuck trap: isStuck branch in source', async () => {
    const stuckKey = '1:BUTTON';
    const stuck = { key: stuckKey, html: '<button>X</button>', tagName: 'BUTTON' };
    const page = makePage({
      tabElements: [stuck, stuck, stuck, stuck], // 4x same element -> trap
      shiftTabElements: [stuck]
    });

    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
  });

  test('fail result has impact: critical and correct structure', async () => {
    const stuckKey = 'BUTTON:modal-close';
    const stuck = { key: stuckKey, html: '<button id="modal-close">Close</button>', tagName: 'button' };
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
      tabElements: [a, b, a, b], // A,B,A,B cycle
      shiftTabElements: [b, a]
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
  });

  test('FN fix: Shift+Tab loop is present in source (via keyboard.down/up)', async () => {
    const stuck = { key: '1:X', html: '<span>X</span>', tagName: 'span' };
    const page = makePage({
      tabElements: [null], // forward Tab passes
      shiftTabElements: [stuck, stuck, stuck, stuck] // backward Tab traps
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(page.keyboard.down).toHaveBeenCalledWith('Shift');
    expect(page.keyboard.up).toHaveBeenCalledWith('Shift');
  });

  // ── Verification paths: Escape ─────────────────────────────────────────────
  test('Escape key allows exit from component — no trap detected', async () => {
    const stuck = { key: '1:X', html: '<span>X</span>', tagName: 'span' };
    const page = makePage({
      tabElements: [stuck, stuck, stuck, stuck],
      shiftTabElements: [stuck]
    });

    // Mock: after Escape, Tab returns null (exits)
    let escaped = false;
    const origPress = page.keyboard.press;
    page.keyboard.press = jest.fn().mockImplementation((key) => {
      if (key === 'Escape') escaped = true;
      if (key === 'Tab' && escaped) {
        // Mock shiftIdx/tabIdx logic to return null
        return Promise.resolve(null);
      }
      return origPress(key);
    });

    // We need to re-mock evaluate to check escaped state
    const origEval = page.evaluate;
    page.evaluate = jest.fn().mockImplementation((fn) => {
      if (escaped && String(fn).includes('activeElement')) return Promise.resolve(null);
      return origEval(fn);
    });

    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
  });

  test('passes when no trap is found in either Tab or Shift+Tab direction', async () => {
    const a = { key: '1:A', html: '<a>A</a>', tagName: 'a' };
    const b = { key: '2:B', html: '<b>B</b>', tagName: 'b' };
    const page = makePage({
      tabElements: [a, b, null],
      shiftTabElements: [b, a, null]
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
  });

  // ── Incomplete paths: Widgets & Heuristics ─────────────────────────────────
  test('returns incomplete for arrow key traps in ARIA widgets', async () => {
    const page = makeArrowTrapPage();
    const result = await run(page);

    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('arrow-key trap');
    expect(result.rules[0].reason).toContain('[role="tablist"]');
  });

  test('result structure: fail has impact critical', async () => {
    const stuck = { key: '1:X', html: '<span>X</span>', tagName: 'span' };
    const page = makePage({
      tabElements: [stuck, stuck, stuck, stuck],
      shiftTabElements: [stuck]
    });
    const result = await run(page);
    expect(result.rules[0].impact).toBe('critical');
  });

  test('successCriteriaId is 2.1.2 in all outcomes', async () => {
    const page = makePage({ tabElements: [null] });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('2.1.2');
  });

  test('description is always set', async () => {
    const page = makePage({ tabElements: [null] });
    const result = await run(page);
    expect(result.rules[0].description).toBeDefined();
  });

  test('source has iframe trap detection code', () => {
    const src = require('fs').readFileSync(require('path').resolve(__dirname, '../../src/custom-checks/keyboard-trap.check.js'), 'utf8');
    expect(src).toContain('frames()');
    expect(src).toContain('mainFrame()');
  });

  test('passes gracefully when frames() returns empty array', async () => {
    const page = makePage({ tabElements: [null] });
    page.frames = jest.fn().mockReturnValue([]);
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
  });

  test('source shows "incomplete" status is used for arrow/iframe traps', () => {
    const src = require('fs').readFileSync(require('path').resolve(__dirname, '../../src/custom-checks/keyboard-trap.check.js'), 'utf8');
    expect(src).toContain('status: \'incomplete\'');
  });

  test('Japanese reason localizes arrow-trap details', async () => {
    const page = makeArrowTrapPage();
    const result = await run(page, { lang: 'ja' });
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('矢印キー操作');
    expect(result.rules[0].reason).toContain('[role="tablist"]');
    expect(result.rules[0].reason).not.toContain('arrow-key trap in');
  });

  test('reports scripted Tab/Escape suppression as incomplete (F58 heuristic)', async () => {
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
    };

    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('preventDefault');
  });
});
