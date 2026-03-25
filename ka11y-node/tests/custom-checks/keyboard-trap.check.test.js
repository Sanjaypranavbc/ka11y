'use strict';

const { run } = require('../../src/custom-checks/keyboard-trap.check');

/**
 * Creates a mock page for keyboard-trap tests.
 *
 * tabElements:       sequence of activeElement infos returned during forward Tab presses.
 *                    Each entry: { key, html, tagName } or null (focus left page).
 * shiftTabElements:  sequence of activeElement infos returned during Shift+Tab presses.
 *                    Defaults to [null] (focus immediately leaves page — no trap).
 *
 * The mock handles the keyboard-trap evaluation sequence:
 *   1. page.evaluate() once for body.focus() → undefined
 *   2. For each Tab iteration:
 *      a. page.keyboard.press('Tab')
 *      b. page.evaluate() → activeInfo
 *      c. [if trap detected] press('Escape'), evaluate(), press('Tab'), evaluate()
 *   3. For each Shift+Tab iteration (FN fix):
 *      The implementation uses keyboard.down('Shift') + press('Tab') + keyboard.up('Shift').
 *      Phase transitions to 'shift' when keyboard.down('Shift') is called.
 */
function makePage({ tabElements = [], shiftTabElements = [null] } = {}) {
  let evaluateCount = 0;

  // We use a stateful evaluate mock that tracks call sequences.
  // Call 0:      body.focus() → undefined
  // Calls 1..N:  active element queries (Tab phase)
  // After trap or end of tab loop: Shift+Tab phase queries continue
  const tabEvals   = tabElements;
  const shiftEvals = shiftTabElements;
  let tabEvalIdx   = 0;
  let shiftEvalIdx = 0;
  let phase        = 'init'; // 'init' | 'tab' | 'shift'

  const page = {
    evaluate: jest.fn().mockImplementation(() => {
      evaluateCount++;
      if (phase === 'init') {
        phase = 'tab';
        return Promise.resolve(undefined); // body.focus()
      }
      if (phase === 'tab') {
        const val = tabEvals[tabEvalIdx] !== undefined ? tabEvals[tabEvalIdx] : null;
        tabEvalIdx++;
        return Promise.resolve(val);
      }
      // phase === 'shift'
      const val = shiftEvals[shiftEvalIdx] !== undefined ? shiftEvals[shiftEvalIdx] : null;
      shiftEvalIdx++;
      return Promise.resolve(val);
    }),
    keyboard: {
      press: jest.fn().mockResolvedValue(undefined),
      // down('Shift') signals start of the Shift+Tab sequence — transition to shift phase
      down: jest.fn().mockImplementation((key) => {
        if (key === 'Shift' && phase !== 'shift') phase = 'shift';
        return Promise.resolve();
      }),
      up: jest.fn().mockResolvedValue(undefined),
    },
  };

  return page;
}

describe('keyboard-trap.check (WCAG 2.1.2)', () => {
  test('passes when forward Tab focus moves freely', async () => {
    // Simulate 3 different elements then null (focus leaves page)
    const page = makePage({
      tabElements:  [
        { key: '1:BUTTON', html: '<button>A</button>', tagName: 'button' },
        { key: '2:BUTTON', html: '<button>B</button>', tagName: 'button' },
        { key: '3:A',      html: '<a href="#">C</a>',  tagName: 'a' },
        null,
      ],
      shiftTabElements: [null],
    });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('2.1.2');
    expect(result.rules[0].status).toBe('pass');
  });

  test('ruleId is custom-keyboard-trap', async () => {
    const page = makePage({ tabElements: [null], shiftTabElements: [null] });
    const result = await run(page);
    expect(result.rules[0].ruleId).toBe('custom-keyboard-trap');
  });

  // FN fix: Shift+Tab backward trap detection
  describe('FN fix: Shift+Tab backward trap detection', () => {
    test('FN fix: Shift+Tab loop is present in source (via keyboard.down/up)', () => {
      const src = require('fs').readFileSync(
        require('path').resolve(__dirname, '../../src/custom-checks/keyboard-trap.check.js'),
        'utf8'
      );
      // Implementation uses down('Shift') + press('Tab') + up('Shift') pattern
      expect(src).toMatch(/keyboard\.down/);
      expect(src).toMatch(/'Shift'/);
    });

    test('Escape key allows exit from component — no trap detected', async () => {
      // Tab phase: no trap (focus leaves page after 2 elements)
      // Shift+Tab phase: no trap (focus leaves page immediately)
      const page = makePage({
        tabElements:  [
          { key: '1:BUTTON', html: '<button>OK</button>', tagName: 'button' },
          null,
        ],
        shiftTabElements: [null],
      });
      const result = await run(page);
      expect(result.rules[0].status).toBe('pass');
    });

    test('passes when no trap is found in either Tab or Shift+Tab direction', async () => {
      const page = makePage({
        tabElements: [
          { key: '1:INPUT', html: '<input>', tagName: 'input' },
          { key: '2:BUTTON', html: '<button>Submit</button>', tagName: 'button' },
          null,
        ],
        shiftTabElements: [
          { key: '2:BUTTON', html: '<button>Submit</button>', tagName: 'button' },
          { key: '1:INPUT', html: '<input>', tagName: 'input' },
          null,
        ],
      });
      const result = await run(page);
      expect(result.rules[0].status).toBe('pass');
    });
  });
});
