'use strict';

const { run, SC, RULE_ID, HELP_URL } = require('../../src/custom-checks/on-input.check');

jest.mock('../../src/custom-checks/sharedAssets', () => {
  const actual = jest.requireActual('../../src/custom-checks/sharedAssets');
  return {
    ...actual,
    settle: jest.fn().mockResolvedValue(undefined),
  };
});

function makePage({ inputs = [], url = 'https://example.com', urlAfterFocus = null, spaNav = false } = {}) {
  const page = {
    url: jest.fn().mockReturnValue(urlAfterFocus || url),
    evaluate: jest.fn().mockImplementation((fn) => {
      const src = String(fn);
      if (src.includes('isCheckboxOrRadio') || src.includes('results.push({')) return Promise.resolve(inputs);
      if (src.includes('spaNavChanged')) return Promise.resolve({ spaNavChanged: spaNav && src.includes('count > 0') });
      if (src.includes('__ka11yOnInputNavState') && src.includes('count > 0')) return Promise.resolve(spaNav);
      return Promise.resolve(undefined);
    }),
    keyboard: { type: jest.fn().mockResolvedValue(undefined), press: jest.fn().mockResolvedValue(undefined) },
    on:  jest.fn(),
    off: jest.fn(),
  };
  return page;
}

const { SELECTOR } = (() => {
  const src = require('fs').readFileSync(require('path').resolve(__dirname, '../../src/custom-checks/on-input.check.js'), 'utf8');
  const match = src.match(/^const SELECTOR\s*=\s*([\s\S]*?)\.join\((.*?)\)/m);
  if (!match) return { SELECTOR: null };
  try {
    const SELECTOR = Function(`"use strict"; return (${match[1]}).join(${match[2]})`)();
    return { SELECTOR };
  } catch (_) { return { SELECTOR: null }; }
})();

describe('on-input.check (WCAG 3.2.2)', () => {
  test('exports metadata', () => {
    expect(SC).toBe('3.2.2');
    expect(RULE_ID).toBe('custom-on-input');
    expect(HELP_URL).toContain('on-input');
  });

  test('passes when no inputs exist', async () => {
    const page = makePage({ inputs: [] });
    const result = await run(page, { focusableElements: [] });
    expect(result.successCriteriaId).toBe('3.2.2');
    expect(result.rules[0].status).toBe('pass');
  });

  test('fails when URL changed after input (SPA)', async () => {
    const input = { tagName: 'input', type: 'text', html: '<input type="text">', idx: 0, staticStyles: '', tag: 'INPUT', target: ['input'], inputType: 'text' };
    const page = makePage({ inputs: [input], spaNav: true });
    const result = await run(page, { focusableElements: [input] });
    expect(result.rules[0].status).toBe('fail');
  });

  test('fails when framenavigated fires during input', async () => {
    const input = { tagName: 'input', type: 'text', html: '<input type="text">', idx: 0, staticStyles: '', tag: 'INPUT', target: ['input'], inputType: 'text' };
    let navListener = null;
    const page = makePage({ inputs: [input] });
    page.on = jest.fn((event, cb) => { if (event === 'framenavigated') navListener = cb; });
    
    // Override evaluate to trigger navigation
    const origEval = page.evaluate;
    page.evaluate = jest.fn().mockImplementation((fn) => {
      const src = String(fn);
      if (src.includes('spaNavChanged')) {
        if (navListener) navListener();
        return Promise.resolve({ spaNavChanged: false });
      }
      return origEval(fn);
    });

    const result = await run(page, { focusableElements: [input] });
    expect(result.rules[0].status).toBe('fail');
  });
});
