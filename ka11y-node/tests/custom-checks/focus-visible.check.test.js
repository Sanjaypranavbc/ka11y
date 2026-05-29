'use strict';

const { run } = require('../../src/custom-checks/focus-visible.check');

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
 * Build a mock page matching the L-1 collapsed evaluate pattern:
 *  - First evaluate() call returns `elements` (element list)
 *  - Second evaluate() call returns `cssFindings` (static CSS scan)
 *  - One evaluate() per element returns `{ unfocused, focused }`
 *
 * All elements share the same unfocusedStyles / focusedStyles for simplicity.
 */
function makePage({ elements = [], unfocusedStyles = BASE_STYLES, focusedStyles = BASE_STYLES } = {}) {
  let callNum = 0;
  return {
    evaluate: jest.fn().mockImplementation(() => {
      callNum++;
      if (callNum === 1) return Promise.resolve(elements);
      if (callNum === 2) return Promise.resolve([]); // cssFindings
      // Each element now uses ONE evaluate returning both style snapshots.
      return Promise.resolve({
        unfocused: { ...unfocusedStyles },
        focused: { ...focusedStyles },
      });
    }),
  };
}

// Use fake timers so SETTLE_MS delays don't slow the test suite
beforeEach(() => jest.useFakeTimers());
afterEach(() => {
  jest.runAllTimers();
  jest.useRealTimers();
});

async function runWithTimers(page) {
  const resultPromise = run(page);
  await jest.runAllTimersAsync();
  return resultPromise;
}

describe('focus-visible.check (WCAG 2.4.7)', () => {
  test('passes when no focusable elements exist', async () => {
    const result = await runWithTimers(makePage({ elements: [] }));
    expect(result.successCriteriaId).toBe('2.4.7');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].impact).toBeNull();
  });

  test('passes when all elements have a visible outline on focus', async () => {
    const elements = [{ idx: 0, tagName: 'button', id: 'submit', html: '<button id="submit">Save</button>' }];
    const result = await runWithTimers(makePage({ elements, unfocusedStyles: BASE_STYLES, focusedStyles: FOCUSED_OUTLINE }));
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].impact).toBeNull();
  });

  test('fails when element has no style change between unfocused and focused', async () => {
    const elements = [{ idx: 0, tagName: 'button', id: 'submit', html: '<button id="submit">Save</button>' }];
    // unfocused === focused → no visible change → violation
    const result = await runWithTimers(makePage({ elements, unfocusedStyles: BASE_STYLES, focusedStyles: BASE_STYLES }));
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].impact).toBe('serious');
    expect(result.rules[0].reason).toMatch('<button');
  });

  test('fails when focused outline color is transparent (N9 fix)', async () => {
    const elements = [{ idx: 0, tagName: 'a', id: null, html: '<a href="#">link</a>' }];
    // Outline style/width changed but color is transparent → not actually visible
    const result = await runWithTimers(makePage({ elements, unfocusedStyles: BASE_STYLES, focusedStyles: FOCUSED_TRANSPARENT_OUTLINE }));
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toMatch('<a');
  });

  test('reports count of multiple violating elements', async () => {
    const elements = [
      { idx: 0, tagName: 'button', id: 'a', html: '<button id="a">A</button>' },
      { idx: 1, tagName: 'a',      id: null, html: '<a href="#">link</a>' },
    ];
    const result = await runWithTimers(makePage({ elements, unfocusedStyles: BASE_STYLES, focusedStyles: BASE_STYLES }));
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toMatch('2 focusable');
  });

  test('passes when focus indicator is box-shadow change', async () => {
    const focusedWithShadow = { ...BASE_STYLES, boxShadow: '0 0 0 3px rgb(0, 95, 204)' };
    const elements = [{ idx: 0, tagName: 'input', id: 'email', html: '<input id="email">' }];
    const result = await runWithTimers(makePage({ elements, unfocusedStyles: BASE_STYLES, focusedStyles: focusedWithShadow }));
    expect(result.rules[0].status).toBe('pass');
  });

  test('ruleId is custom-focus-visible', async () => {
    const result = await runWithTimers(makePage({ elements: [] }));
    expect(result.rules[0].ruleId).toBe('custom-focus-visible');
  });
});