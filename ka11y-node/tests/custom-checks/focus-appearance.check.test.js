'use strict';

const { run } = require('../../src/custom-checks/focus-appearance.check');

/**
 * Creates a mock page for focus-appearance tests.
 *
 * The run() function does:
 *   1. page.evaluate(collectElements)  → array of element descriptors
 *   2. For each element:
 *      a. page.evaluate(captureUnfocused) → { outlineWidth, outlineStyle, ... }
 *      b. setTimeout (SETTLE_MS)
 *      c. page.evaluate(captureFocused)  → { outlineWidth, outlineStyle, ... }
 *      d. setTimeout (SETTLE_MS)
 *      e. page.evaluate(blurElement)     → void
 *
 * @param {Array} elements   - Array of element descriptors returned by the first evaluate call
 * @param {Array} styleSeq   - Array of [unfocused, focused] style pairs, one per element.
 */
function makePage(elements, styleSeq = []) {
  let evaluateIdx = 0;
  const responses = [];

  // First evaluate: return elements list
  responses.push(elements);

  // For each element: unfocused styles, focused styles, blur (undefined)
  for (const [unfocused, focused] of styleSeq) {
    responses.push(unfocused);   // captureUnfocused
    responses.push(focused);     // captureFocused
    responses.push(undefined);   // blur
  }

  return {
    evaluate: jest.fn().mockImplementation(() => {
      const val = responses[evaluateIdx] !== undefined ? responses[evaluateIdx] : null;
      evaluateIdx++;
      return Promise.resolve(val);
    }),
  };
}

/** Standard style objects for tests */
const STYLES = {
  noOutline: {
    outlineWidth: '0px', outlineStyle: 'none', outlineColor: 'transparent',
    boxShadow: 'none', backgroundColor: 'rgb(255,255,255)',
    borderColor: 'rgb(0,0,0)', borderWidth: '1px',
  },
  outline2px: {
    outlineWidth: '2px', outlineStyle: 'solid', outlineColor: 'rgb(0,95,204)',
    boxShadow: 'none', backgroundColor: 'rgb(255,255,255)',
    borderColor: 'rgb(0,0,0)', borderWidth: '1px',
  },
  outline1px: {
    outlineWidth: '1px', outlineStyle: 'solid', outlineColor: 'rgb(0,95,204)',
    boxShadow: 'none', backgroundColor: 'rgb(255,255,255)',
    borderColor: 'rgb(0,0,0)', borderWidth: '1px',
  },
  // Low contrast: light gray outline on white background (contrast ratio < 3:1)
  outlineLowContrast: {
    outlineWidth: '2px', outlineStyle: 'solid', outlineColor: 'rgb(200,200,200)',
    boxShadow: 'none', backgroundColor: 'rgb(255,255,255)',
    borderColor: 'rgb(0,0,0)', borderWidth: '1px',
  },
};

const SAMPLE_ELEMENTS = [
  { idx: 0, stableSel: '#btn', tag: 'button', id: 'btn', html: '<button id="btn">Click me</button>' },
];

/**
 * Helper: run() and advance fake timers concurrently.
 * run() awaits multiple setTimeouts internally; we use runAllTimersAsync() to
 * advance them without blocking the async flow.
 */
async function runWithTimers(page) {
  const resultPromise = run(page);
  await jest.runAllTimersAsync();
  return resultPromise;
}

describe('focus-appearance.check (WCAG 2.4.13)', () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  test('successCriteriaId is 2.4.13', async () => {
    const page = makePage([], []);
    const result = await runWithTimers(page);
    expect(result.successCriteriaId).toBe('2.4.13');
  });

  test('ruleId is custom-focus-appearance', async () => {
    const page = makePage([], []);
    const result = await runWithTimers(page);
    expect(result.rules[0].ruleId).toBe('custom-focus-appearance');
  });

  test('passes when no focusable elements are found', async () => {
    const page = makePage([], []);
    const result = await runWithTimers(page);
    expect(result.rules[0].status).toBe('pass');
  });

  test('element with 2px+ outline and sufficient contrast SHOULD pass', async () => {
    const page = makePage(
      SAMPLE_ELEMENTS,
      [[STYLES.noOutline, STYLES.outline2px]],
    );
    const result = await runWithTimers(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('1 focusable element(s) sampled');
  });

  test('element with 1px outline SHOULD fail (area requirement not met)', async () => {
    const page = makePage(
      SAMPLE_ELEMENTS,
      [[STYLES.noOutline, STYLES.outline1px]],
    );
    const result = await runWithTimers(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('outline-width');
    expect(result.rules[0].reason).toContain('1px');
  });

  test('element with no focus indicator at all SHOULD fail', async () => {
    // Unfocused and focused styles are identical (no change = no indicator)
    const page = makePage(
      SAMPLE_ELEMENTS,
      [[STYLES.noOutline, STYLES.noOutline]],
    );
    const result = await runWithTimers(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('focus indicator');
  });

  test('element with insufficient contrast (low-contrast outline) SHOULD fail', async () => {
    // Light gray (200,200,200) on white (255,255,255) has very low contrast ratio
    const page = makePage(
      SAMPLE_ELEMENTS,
      [[STYLES.noOutline, STYLES.outlineLowContrast]],
    );
    const result = await runWithTimers(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('contrast');
  });

  test('fail reason includes element tag and issue description', async () => {
    const page = makePage(
      SAMPLE_ELEMENTS,
      [[STYLES.noOutline, STYLES.outline1px]],
    );
    const result = await runWithTimers(page);
    expect(result.rules[0].reason).toMatch(/<button/);
  });

  test('fail result has impact: serious', async () => {
    const page = makePage(
      SAMPLE_ELEMENTS,
      [[STYLES.noOutline, STYLES.noOutline]],
    );
    const result = await runWithTimers(page);
    expect(result.rules[0].impact).toBe('serious');
  });

  test('element with box-shadow focus indicator is NOT reported as missing indicator', async () => {
    const focused = {
      ...STYLES.noOutline,
      // box-shadow added on focus — this IS a visible focus indicator
      boxShadow: '0 0 0 3px rgb(0,95,204)',
    };
    const page = makePage(
      SAMPLE_ELEMENTS,
      [[STYLES.noOutline, focused]],
    );
    const result = await runWithTimers(page);
    // box-shadow change is treated as a focus indicator; should NOT fail with "no-indicator"
    if (result.rules[0].status === 'fail') {
      expect(result.rules[0].reason).not.toContain('No visible focus indicator');
    }
  });
});
