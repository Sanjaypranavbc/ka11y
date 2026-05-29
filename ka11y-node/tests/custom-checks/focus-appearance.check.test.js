'use strict';

const { run, SC, RULE_ID, HELP_URL } = require('../../src/custom-checks/focus-appearance.check');
const { RESULT_CACHE } = require('../../src/custom-checks/sharedAssets');

/**
 * Creates a mock page for focus-appearance tests.
 *
 * Each element now uses ONE evaluate returning both style snapshots.
 *
 * @param {Array} styleSeq   - Array of [unfocused, focused] style pairs, one per element.
 */
function makePage(styleSeq = []) {
  let evaluateIdx = 0;
  return {
    evaluate: jest.fn().mockImplementation(() => {
      const pair = styleSeq[evaluateIdx++];
      if (!pair) return Promise.resolve(null);
      return Promise.resolve({
        unfocused: pair[0],
        focused: pair[1],
      });
    }),
  };
}

/** Standard style objects for tests */
const STYLES = {
  noOutline: {
    outlineWidth: '0px', outlineStyle: 'none', outlineColor: 'transparent',
    boxShadow: 'none', backgroundColor: 'rgb(255,255,255)',
    borderColor: 'rgb(0,0,0)', borderWidth: '1px',
    bodyBg: 'rgb(255,255,255)',
  },
  outline2px: {
    outlineWidth: '2px', outlineStyle: 'solid', outlineColor: 'rgb(0,95,204)',
    boxShadow: 'none', backgroundColor: 'rgb(255,255,255)',
    borderColor: 'rgb(0,0,0)', borderWidth: '1px',
    bodyBg: 'rgb(255,255,255)',
  },
  outline1px: {
    outlineWidth: '1px', outlineStyle: 'solid', outlineColor: 'rgb(0,95,204)',
    boxShadow: 'none', backgroundColor: 'rgb(255,255,255)',
    borderColor: 'rgb(0,0,0)', borderWidth: '1px',
    bodyBg: 'rgb(255,255,255)',
  },
  // Low contrast: light gray outline on white background (contrast ratio < 3:1)
  outlineLowContrast: {
    outlineWidth: '2px', outlineStyle: 'solid', outlineColor: 'rgb(200,200,200)',
    boxShadow: 'none', backgroundColor: 'rgb(255,255,255)',
    borderColor: 'rgb(0,0,0)', borderWidth: '1px',
    bodyBg: 'rgb(255,255,255)',
  },
};

const SAMPLE_ELEMENTS = [
  { idx: 0, stableSel: '#btn', tag: 'button', id: 'btn', html: '<button id="btn">Click me</button>' },
];

/**
 * Helper: run() and advance fake timers concurrently.
 */
async function runWithTimers(page, elements = SAMPLE_ELEMENTS, context = {}) {
  const resultPromise = run(page, { ...context, focusableElements: elements });
  await jest.runAllTimersAsync();
  return resultPromise;
}

describe('focus-appearance.check (WCAG 2.4.13)', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    RESULT_CACHE.clear();
  });
  afterEach(() => jest.useRealTimers());

  // ── Module exports ─────────────────────────────────────────────────────────
  test('exports SC as 2.4.13', () => { expect(SC).toBe('2.4.13'); });
  test('exports RULE_ID as custom-focus-appearance', () => { expect(RULE_ID).toBe('custom-focus-appearance'); });
  test('exports HELP_URL', () => { expect(HELP_URL).toContain('focus-appearance'); });

  // ── Pass paths ─────────────────────────────────────────────────────────────
  test('successCriteriaId is 2.4.13', async () => {
    const page = makePage([]);
    const result = await runWithTimers(page, []);
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
    expect(result.rules[0].impact).toBeNull();
    expect(result.rules[0].helpUrl).toBe(HELP_URL);
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

  test('pass reason includes min outline and contrast requirements', async () => {
    const page = makePage(SAMPLE_ELEMENTS, [[STYLES.noOutline, STYLES.outline2px]]);
    const result = await runWithTimers(page);
    expect(result.rules[0].reason).toContain('2px');
    expect(result.rules[0].reason).toContain('3');
  });

  // ── Fail: no indicator ────────────────────────────────────────────────────
  test('element with no focus indicator at all SHOULD fail', async () => {
    const page = makePage(
      SAMPLE_ELEMENTS,
      [[STYLES.noOutline, STYLES.noOutline]],
    );
    const result = await runWithTimers(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('focus indicator');
    expect(result.rules[0].impact).toBe('serious');
  });

  // ── Fail: area requirement not met ────────────────────────────────────────
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

  // ── Fail: contrast not met ────────────────────────────────────────────────
  test('element with insufficient contrast (low-contrast outline) SHOULD fail', async () => {
    const page = makePage(
      SAMPLE_ELEMENTS,
      [[STYLES.noOutline, STYLES.outlineLowContrast]],
    );
    const result = await runWithTimers(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('contrast');
  });

  test('Japanese reason localizes focus issue details', async () => {
    const page = makePage(
      SAMPLE_ELEMENTS,
      [[STYLES.noOutline, STYLES.outline1px]],
    );
    const result = await runWithTimers(page, { lang: 'ja' });
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('アウトライン幅');
    expect(result.rules[0].reason).not.toContain('area requirement');
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

  // ── Box-shadow indicator ──────────────────────────────────────────────────
  test('element with box-shadow focus indicator passes (with sufficient spread)', async () => {
    const focused = {
      ...STYLES.noOutline,
      boxShadow: '0 0 0 3px rgb(0,95,204)',
    };
    const page = makePage(
      SAMPLE_ELEMENTS,
      [[STYLES.noOutline, focused]],
    );
    const result = await runWithTimers(page);
    expect(result.rules[0].status).toBe('pass');
  });

  test('element with small box-shadow spread (1px) may fail area requirement', async () => {
    const focused = {
      ...STYLES.noOutline,
      boxShadow: '0 0 0 1px rgb(0,95,204)',
    };
    const page = makePage(
      SAMPLE_ELEMENTS,
      [[STYLES.noOutline, focused]],
    );
    const result = await runWithTimers(page);
    // 1px spread < 2px minimum → fail area
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('area requirement');
  });

  // ── Border change indicator ────────────────────────────────────────────────
  test('element with border change (different color) is detected as indicator', async () => {
    const unfocused = { ...STYLES.noOutline };
    const focused = {
      ...STYLES.noOutline,
      borderColor: 'rgb(0,95,204)', // color changed
      borderWidth: '2px',           // width changed from 1px → 2px
    };
    const page = makePage(SAMPLE_ELEMENTS, [[unfocused, focused]]);
    const result = await runWithTimers(page);
    // Border changed → has indicator; width 2px ≥ 2px → area met
    // High contrast blue on white → passes
    expect(result.rules[0].status).toBe('pass');
  });

  test('border-only indicator with unchanged width fails area requirement', async () => {
    const unfocused = { ...STYLES.noOutline };
    const focused = {
      ...STYLES.noOutline,
      borderColor: 'rgb(0,95,204)', // only color changed, width unchanged
      // borderWidth stays '1px' (same as unfocused) → no area change
    };
    const page = makePage(SAMPLE_ELEMENTS, [[unfocused, focused]]);
    const result = await runWithTimers(page);
    // Border color changed but width unchanged → borderChangedForArea = false → area not met
    expect(result.rules[0].status).toBe('fail');
  });

  // ── Multiple elements ─────────────────────────────────────────────────────
  test('multiple elements: all pass when all have sufficient focus', async () => {
    const elements = [
      { idx: 0, stableSel: '#a', tag: 'button', id: 'a', html: '<button id="a">A</button>' },
      { idx: 1, stableSel: '#b', tag: 'a',      id: 'b', html: '<a id="b" href="#">B</a>' },
    ];
    const page = makePage(elements, [
      [STYLES.noOutline, STYLES.outline2px],
      [STYLES.noOutline, STYLES.outline2px],
    ]);
    const result = await runWithTimers(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('2 focusable element(s)');
  });

  test('multiple elements: one fails → overall fail with count', async () => {
    const elements = [
      { idx: 0, stableSel: '#a', tag: 'button', id: 'a', html: '<button id="a">A</button>' },
      { idx: 1, stableSel: '#b', tag: 'a',      id: 'b', html: '<a id="b" href="#">B</a>' },
    ];
    const page = makePage(elements, [
      [STYLES.noOutline, STYLES.outline2px],  // passes
      [STYLES.noOutline, STYLES.noOutline],   // fails
    ]);
    const result = await runWithTimers(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('1 focusable');
  });

  test('null unfocused styles: element is skipped', async () => {
    const page = makePage(SAMPLE_ELEMENTS, [[null, STYLES.outline2px]]);
    // When unfocused returns null, the element is skipped (continue)
    const result = await runWithTimers(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('0 focusable');
  });

  test('null focused styles: element is skipped', async () => {
    const page = makePage(SAMPLE_ELEMENTS, [[STYLES.noOutline, null]]);
    const result = await runWithTimers(page);
    expect(result.rules[0].status).toBe('pass');
  });

  // ── splitBoxShadowLayers is a Node-side exported function ─────────────────
  test('source exports splitBoxShadowLayers as module-level function', () => {
    const src = require('fs').readFileSync(
      require('path').resolve(__dirname, '../../src/custom-checks/focus-appearance.check.js'),
      'utf8'
    );
    expect(src).toContain('function splitBoxShadowLayers');
    expect(src).toContain('function extractBoxShadowMetrics');
    expect(src).toContain('function relativeLuminance');
    expect(src).toContain('function contrastRatio');
  });

  // ── transparent background fallback (B5) ──────────────────────────────────
  test('transparent element background falls back to body background for contrast', async () => {
    const unfocused = { ...STYLES.noOutline, backgroundColor: 'rgba(0, 0, 0, 0)' }; // transparent
    const focused = {
      ...STYLES.noOutline,
      outlineWidth: '2px',
      outlineStyle: 'solid',
      outlineColor: 'rgb(0,95,204)', // high contrast vs white body bg
      backgroundColor: 'rgba(0, 0, 0, 0)', // still transparent
      bodyBg: 'rgb(255,255,255)', // white body background
    };
    const page = makePage(SAMPLE_ELEMENTS, [[unfocused, focused]]);
    const result = await runWithTimers(page);
    // Should use bodyBg (white) for bg comparison → high contrast → pass
    expect(result.rules[0].status).toBe('pass');
  });

  // ── Box-shadow: multiple layers (best spread used) ────────────────────────
  test('box-shadow with multiple layers picks the best (largest) spread', async () => {
    const focused = {
      ...STYLES.noOutline,
      // Two layers: first has 1px spread, second has 3px spread → best is 3px
      boxShadow: '0 0 0 1px rgb(100,100,100), 0 0 0 3px rgb(0,95,204)',
    };
    const page = makePage(SAMPLE_ELEMENTS, [[STYLES.noOutline, focused]]);
    const result = await runWithTimers(page);
    expect(result.rules[0].status).toBe('pass');
  });
});
