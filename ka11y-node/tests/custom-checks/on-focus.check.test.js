'use strict';

const { run, SC, RULE_ID, HELP_URL } = require('../../src/custom-checks/on-focus.check');

jest.mock('../../src/custom-checks/sharedAssets', () => {
  const actual = jest.requireActual('../../src/custom-checks/sharedAssets');
  return {
    ...actual,
    settle: jest.fn().mockResolvedValue(undefined),
  };
});

function makePage({ focusable = [], url = 'https://example.com', navigates = false, urlAfterFocus = null } = {}) {
  let navListener = null;
  let focused = false;
  const page = {
    url: jest.fn().mockImplementation(() => focused ? (urlAfterFocus || url) : url),
    evaluate: jest.fn().mockImplementation((fn) => {
      const src = String(fn);
      if (src.includes('originalPush') && src.includes('count = 0')) return Promise.resolve(undefined);
      if (src.includes('count > 0') && !src.includes('spaNavChanged')) return Promise.resolve(false);
      if (src.includes('delete window[stateKey]')) return Promise.resolve(undefined);
      if (src.includes('results.push({')) return Promise.resolve(focusable);
      if (src.includes('spaNavChanged')) {
        if (src.includes('el.focus(')) {
           focused = true;
           if (navigates && navListener) navListener();
        }
        return Promise.resolve({ spaNavChanged: false });
      }
      if (src.includes('el.focus(')) {
        focused = true;
        if (navigates && navListener) navListener();
        return Promise.resolve(undefined);
      }
      return Promise.resolve(undefined);
    }),
    on: jest.fn((event, cb) => { if (event === 'framenavigated') navListener = cb; }),
    off: jest.fn(),
  };
  return page;
}

const { SELECTOR } = (() => {
  const src = require('fs').readFileSync(require('path').resolve(__dirname, '../../src/custom-checks/on-focus.check.js'), 'utf8');
  const match = src.match(/^const SELECTOR\s*=\s*([\s\S]*?)\.join\((.*?)\)/m);
  if (!match) return { SELECTOR: null };
  try {
    const SELECTOR = Function(`"use strict"; return (${match[1]}).join(${match[2]})`)();
    return { SELECTOR };
  } catch (_) { return { SELECTOR: null }; }
})();

describe('on-focus.check (WCAG 3.2.1)', () => {
  test('passes when no focusable elements exist', async () => {
    const page = makePage({ focusable: [] });
    const result = await run(page, { focusableElements: [] });
    expect(result.successCriteriaId).toBe('3.2.1');
    expect(result.rules[0].status).toBe('pass');
  });

  test('passes when focusable elements exist but no navigation', async () => {
    const el = { tagName: 'button', id: 'btn1', stableSel: '#btn1', html: '<button id="btn1">OK</button>', idx: 0, staticStyles: '', tag: 'BUTTON', target: ['#btn1'] };
    const page = makePage({ focusable: [el] });
    const result = await run(page, { focusableElements: [el] });
    expect(result.rules[0].status).toBe('pass');
  });

  test('fails when framenavigated fires during focus', async () => {
    const el = { tagName: 'button', id: 'nav-btn', stableSel: '#nav-btn', html: '<button id="nav-btn">Go</button>', idx: 0, staticStyles: '', tag: 'BUTTON', target: ['#nav-btn'] };
    const page = makePage({ focusable: [el], navigates: true });
    const result = await run(page, { focusableElements: [el] });
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('button');
  });

  test('fails when URL path changes after focus', async () => {
    let callCount = 0;
    const el = { tagName: 'a', id: 'link1', stableSel: '#link1', html: '<a id="link1">Go</a>', idx: 0, staticStyles: '', tag: 'A', target: ['#link1'] };
    const page = {
      evaluate: jest.fn().mockImplementation((fn) => {
        const src = String(fn);
        if (src.includes('spaNavChanged')) return Promise.resolve({ spaNavChanged: false });
        if (src.includes('count > 0')) return Promise.resolve(false);
        return Promise.resolve(undefined);
      }),
      url: jest.fn().mockImplementation(() => {
        callCount++;
        return callCount % 2 === 0 ? 'https://example.com/page2' : 'https://example.com/page1';
      }),
      on: jest.fn(),
      off: jest.fn(),
    };
    const result = await run(page, { focusableElements: [el] });
    expect(result.rules[0].status).toBe('fail');
  });

  test('fails when SPA navigation is detected via instrumentation', async () => {
    const el = { tagName: 'button', id: 'spa-btn', stableSel: '#spa-btn', html: '<button id="spa-btn">Nav</button>', idx: 0, staticStyles: '', tag: 'BUTTON', target: ['#spa-btn'] };
    const page = {
      evaluate: jest.fn().mockImplementation((fn) => {
        const src = String(fn);
        if (src.includes('spaNavChanged')) return Promise.resolve({ spaNavChanged: true });
        if (src.includes('count > 0')) return Promise.resolve(true);
        return Promise.resolve(undefined);
      }),
      url: jest.fn().mockReturnValue('https://example.com/same'),
      on: jest.fn(),
      off: jest.fn(),
    };
    const result = await run(page, { focusableElements: [el] });
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('button');
  });
});
