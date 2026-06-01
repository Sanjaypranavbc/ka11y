'use strict';

const { run } = require('../../src/custom-checks/focus-visible.check');
const { RESULT_CACHE } = require('../../src/custom-checks/sharedAssets');

// Base style object matching what getComputedStyle returns for a default unfocused element
const BASE_STYLES = {
  outlineWidth:    '0px',
  outlineStyle:    'none',
  outlineColor:    'rgba(0, 0, 0, 0)',
  boxShadow:       'none',
  borderColor:     'rgb(0, 0, 0)',
  borderWidth:     '1px',
  backgroundColor: 'rgba(0, 0, 0, 0)',
  color:           'rgb(0, 0, 0)',
  opacity:         '1',
};

// Focused style with a clearly visible outline
const FOCUSED_OUTLINE = {
  ...BASE_STYLES,
  outlineStyle:  'solid',
  outlineWidth:  '3px',
  outlineColor:  'rgb(0, 95, 204)',
};

// Focused style where outline changed to transparent (invisible — should still fail N9)
const FOCUSED_TRANSPARENT_OUTLINE = {
  ...BASE_STYLES,
  outlineStyle: 'solid',
  outlineWidth: '2px',
  outlineColor: 'rgba(0, 0, 0, 0)',  // transparent — not actually visible
};

/**
 * Build a mock page matching the L-1 collapsed evaluate pattern.
 * Uses src content to determine what to return.
 */
function makePage({ unfocusedStyles = BASE_STYLES, focusedStyles = BASE_STYLES, elements = [] } = {}) {
  return {
    evaluate: jest.fn().mockImplementation((fn) => {
      const src = String(fn);
      if (src.includes('results.push({')) return Promise.resolve(elements);
      if (src.includes('OUTLINE_RESET_RE')) return Promise.resolve([]); // cssFindings
      return Promise.resolve({
        unfocused: { ...unfocusedStyles },
        focused: { ...focusedStyles },
      });
    }),
  };
}

// Use fake timers
beforeEach(() => {
  jest.useFakeTimers();
  RESULT_CACHE.clear();
});
afterEach(() => {
  jest.runAllTimers();
  jest.useRealTimers();
});

jest.mock('../../src/custom-checks/sharedAssets', () => {
  const actual = jest.requireActual('../../src/custom-checks/sharedAssets');
  return {
    ...actual,
    settle: jest.fn().mockResolvedValue(undefined),
  };
});

async function runWithTimers(page, elements = null) {
  const resultPromise = run(page, elements ? { focusableElements: elements } : {});
  await jest.runAllTimersAsync();
  return resultPromise;
}

describe('focus-visible.check (WCAG 2.4.7)', () => {
  test('passes when no focusable elements exist', async () => {
    const result = await runWithTimers(makePage({ elements: [] }), []);
    expect(result.successCriteriaId).toBe('2.4.7');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].impact).toBeNull();
  });

  test('passes when all elements have a visible outline on focus', async () => {
    const elements = [{ idx: 0, tagName: 'button', id: 'submit', html: '<button id="submit">Save</button>', staticStyles: '' }];
    const result = await runWithTimers(makePage({ unfocusedStyles: BASE_STYLES, focusedStyles: FOCUSED_OUTLINE }), elements);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].impact).toBeNull();
  });

  test('fails when element has no style change between unfocused and focused', async () => {
    const elements = [{ idx: 0, tagName: 'button', id: 'submit', html: '<button id="submit">Save</button>', staticStyles: '' }];
    const result = await runWithTimers(makePage({ unfocusedStyles: BASE_STYLES, focusedStyles: BASE_STYLES }), elements);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].impact).toBe('serious');
    expect(result.rules[0].reason).toMatch('<button');
  });

  test('fails when focused outline color is transparent (N9 fix)', async () => {
    const elements = [{ idx: 0, tagName: 'a', id: null, html: '<a href="#">link</a>', staticStyles: '' }];
    const result = await runWithTimers(makePage({ unfocusedStyles: BASE_STYLES, focusedStyles: FOCUSED_TRANSPARENT_OUTLINE }), elements);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toMatch('<a');
  });
});
