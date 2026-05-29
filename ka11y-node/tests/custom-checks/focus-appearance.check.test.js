'use strict';

const { run, SC, RULE_ID, HELP_URL } = require('../../src/custom-checks/focus-appearance.check');
const { RESULT_CACHE } = require('../../src/custom-checks/sharedAssets');

jest.mock('../../src/custom-checks/sharedAssets', () => {
  const actual = jest.requireActual('../../src/custom-checks/sharedAssets');
  return {
    ...actual,
    settle: jest.fn().mockResolvedValue(undefined),
  };
});

/**
 * Creates a mock page for focus-appearance tests.
 */
function makePage(styleSeq = [], elements = []) {
  let elementCheckIdx = 0;
  return {
    evaluate: jest.fn().mockImplementation((fn) => {
      const src = String(fn);
      if (src.includes('results.push({')) return Promise.resolve(elements);
      if (src.includes('captureBox')) {
        const pair = styleSeq[elementCheckIdx++];
        if (!pair) return Promise.resolve(null);
        return Promise.resolve({
          unfocused: pair[0],
          focused: pair[1],
        });
      }
      return Promise.resolve(null);
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
  outlineLowContrast: {
    outlineWidth: '2px', outlineStyle: 'solid', outlineColor: 'rgb(200,200,200)',
    boxShadow: 'none', backgroundColor: 'rgb(255,255,255)',
    borderColor: 'rgb(0,0,0)', borderWidth: '1px',
    bodyBg: 'rgb(255,255,255)',
  },
};

const SAMPLE_ELEMENTS = [
  { idx: 0, stableSel: '#btn', tag: 'button', id: 'btn', html: '<button id="btn">Click me</button>', staticStyles: '' },
];

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

  test('exports metadata', () => {
    expect(SC).toBe('2.4.13');
    expect(RULE_ID).toBe('custom-focus-appearance');
    expect(HELP_URL).toContain('focus-appearance');
  });

  test('successCriteriaId is 2.4.13', async () => {
    const result = await runWithTimers(makePage([], []), []);
    expect(result.successCriteriaId).toBe('2.4.13');
  });

  test('passes when no focusable elements exist', async () => {
    const result = await runWithTimers(makePage([], []), []);
    expect(result.rules[0].status).toBe('pass');
  });

  test('element with 2px+ outline and sufficient contrast SHOULD pass', async () => {
    const page = makePage([[STYLES.noOutline, STYLES.outline2px]]);
    const result = await runWithTimers(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('1 focusable element(s) sampled');
  });

  test('pass reason includes min requirements', async () => {
    const page = makePage([[STYLES.noOutline, STYLES.outline2px]]);
    const result = await runWithTimers(page);
    expect(result.rules[0].reason).toContain('≥2px outline');
    expect(result.rules[0].reason).toContain('≥3:1');
  });

  test('element with no focus indicator SHOULD fail', async () => {
    const page = makePage([[STYLES.noOutline, STYLES.noOutline]]);
    const result = await runWithTimers(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('focus indicator');
  });

  test('element with 1px outline SHOULD fail (area requirement)', async () => {
    const page = makePage([[STYLES.noOutline, STYLES.outline1px]]);
    const result = await runWithTimers(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('outline-width');
    expect(result.rules[0].reason).toContain('1px');
  });

  test('element with low contrast SHOULD fail', async () => {
    const page = makePage([[STYLES.noOutline, STYLES.outlineLowContrast]]);
    const result = await runWithTimers(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('contrast');
  });

  test('Japanese reason localizes details', async () => {
    const page = makePage([[STYLES.noOutline, STYLES.outline1px]]);
    const result = await runWithTimers(page, SAMPLE_ELEMENTS, { lang: 'ja' });
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('アウトライン幅');
  });

  test('fail reason includes element tag', async () => {
    const page = makePage([[STYLES.noOutline, STYLES.noOutline]]);
    const result = await runWithTimers(page);
    expect(result.rules[0].reason).toMatch(/<button/);
  });

  test('fail impact is serious', async () => {
    const page = makePage([[STYLES.noOutline, STYLES.noOutline]]);
    const result = await runWithTimers(page);
    expect(result.rules[0].impact).toBe('serious');
  });

  test('box-shadow spread (2px+) pass', async () => {
    const focused = { ...STYLES.noOutline, boxShadow: '0 0 0 2px rgb(0,95,204)' };
    const result = await runWithTimers(makePage([[STYLES.noOutline, focused]]));
    expect(result.rules[0].status).toBe('pass');
  });

  test('box-shadow spread (1px) fail', async () => {
    const focused = { ...STYLES.noOutline, boxShadow: '0 0 0 1px rgb(0,95,204)' };
    const result = await runWithTimers(makePage([[STYLES.noOutline, focused]]));
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('area requirement');
  });

  test('border-width (2px+) pass', async () => {
    const unfocused = { ...STYLES.noOutline, borderWidth: '1px' };
    const focused = { ...STYLES.noOutline, borderWidth: '3px' };
    const result = await runWithTimers(makePage([[unfocused, focused]]));
    expect(result.rules[0].status).toBe('pass');
  });

  test('border-width unchanged fail', async () => {
    const unfocused = { ...STYLES.noOutline, borderWidth: '2px', borderColor: 'rgb(0,0,0)' };
    const focused = { ...STYLES.noOutline, borderWidth: '2px', borderColor: 'rgb(0,95,204)' };
    const result = await runWithTimers(makePage([[unfocused, focused]]));
    expect(result.rules[0].status).toBe('fail');
  });

  test('multiple elements: all pass', async () => {
    const elements = [
      { idx: 0, tag: 'button', html: '<button>A</button>', staticStyles: '' },
      { idx: 1, tag: 'a',      html: '<a>B</a>', staticStyles: '' },
    ];
    const page = makePage([[STYLES.noOutline, STYLES.outline2px], [STYLES.noOutline, STYLES.outline2px]]);
    const result = await runWithTimers(page, elements);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('2 focusable element(s)');
  });

  test('multiple elements: one fails', async () => {
    const elements = [
      { idx: 0, tag: 'button', html: '<button>Pass</button>', staticStyles: '' },
      { idx: 1, tag: 'button', html: '<button>Fail</button>', staticStyles: '' },
    ];
    const page = makePage([[STYLES.noOutline, STYLES.outline2px], [STYLES.noOutline, STYLES.noOutline]]);
    const result = await runWithTimers(page, elements);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('1 focusable');
  });

  test('skips elements that return null styles', async () => {
    const page = makePage([[null, STYLES.outline2px]]);
    const result = await runWithTimers(page);
    expect(result.rules[0].reason).toContain('0 focusable element(s) sampled');
  });

  test('transparent background uses body background fallback', async () => {
    const unfocused = { ...STYLES.noOutline, backgroundColor: 'rgba(0, 0, 0, 0)' };
    const focused = {
      ...STYLES.noOutline,
      outlineWidth: '2px',
      outlineStyle: 'solid',
      outlineColor: 'rgb(0,95,204)',
      backgroundColor: 'rgba(0, 0, 0, 0)',
      bodyBg: 'rgb(255,255,255)',
    };
    const result = await runWithTimers(makePage([[unfocused, focused]]));
    expect(result.rules[0].status).toBe('pass');
  });
});
