'use strict';

const { run, SC, RULE_ID, HELP_URL } = require('../../src/custom-checks/on-focus.check');

function makePage({ focusable = [], url = 'https://example.com', navigates = false, urlAfterFocus = null } = {}) {
  let navListener = null;
  let evaluateCallCount = 0;
  const page = {
    url: jest.fn().mockReturnValue(urlAfterFocus || url),
    evaluate: jest.fn().mockImplementation((fn) => {
      evaluateCallCount++;
      const src = String(fn);
      // installNavInstrumentation — returns undefined (void)
      if (src.includes('originalPush') && src.includes('count = 0')) return Promise.resolve(undefined);
      // readAndResetNavInstrumentation — returns false (no nav change)
      if (src.includes('count > 0')) return Promise.resolve(false);
      // uninstallNavInstrumentation
      if (src.includes('delete window[stateKey]')) return Promise.resolve(undefined);
      // focusable element query
      if (src.includes('results.push({')) return Promise.resolve(focusable);
      // focus on element
      if (src.includes('el.focus(')) return Promise.resolve(undefined);
      return Promise.resolve(undefined);
    }),
    on: jest.fn((event, cb) => { if (event === 'framenavigated') navListener = cb; }),
    off: jest.fn(),
  };
  if (navigates) {
    // Simulate navigation after first element is focused
    const origEvaluate = page.evaluate;
    let focused = false;
    page.evaluate = jest.fn().mockImplementation((fn, ...args) => {
      const src = String(fn);
      if (!focused && src.includes('el.focus(')) {
        focused = true;
        if (navListener) navListener(); // trigger framenavigated
      }
      return origEvaluate(fn, ...args);
    });
  }
  return page;
}

const { SELECTOR } = (() => {
  const src = require('fs').readFileSync(require('path').resolve(__dirname, '../../src/custom-checks/on-focus.check.js'), 'utf8');
  const match = src.match(/^const SELECTOR\s*=\s*([\s\S]*?)\.join\((.*?)\)/m);
  if (!match) return { SELECTOR: null };
  try {
    // eslint-disable-next-line no-new-func
    const SELECTOR = Function(`"use strict"; return (${match[1]}).join(${match[2]})`)();
    return { SELECTOR };
  } catch (_) { return { SELECTOR: null }; }
})();

describe('on-focus.check (WCAG 3.2.1)', () => {
  // ── Module exports ─────────────────────────────────────────────────────────
  test('exports SC as 3.2.1', () => { expect(SC).toBe('3.2.1'); });
  test('exports RULE_ID as custom-on-focus', () => { expect(RULE_ID).toBe('custom-on-focus'); });
  test('exports HELP_URL', () => { expect(HELP_URL).toContain('on-focus'); });

  // ── Pass paths ─────────────────────────────────────────────────────────────
  test('passes when no focusable elements exist', async () => {
    const page = makePage({ focusable: [] });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('3.2.1');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].ruleId).toBe('custom-on-focus');
    expect(result.rules[0].impact).toBeNull();
    expect(result.rules[0].helpUrl).toBe(HELP_URL);
  });

  test('passes when focusable elements exist but no navigation', async () => {
    const page = makePage({
      focusable: [
        { tagName: 'button', id: 'btn1', stableSel: '#btn1', html: '<button id="btn1">OK</button>' },
        { tagName: 'a',      id: 'lnk1', stableSel: '#lnk1', html: '<a id="lnk1" href="#">Link</a>' },
      ],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('No unexpected context changes');
  });

  test('always calls page.off to clean up listener', async () => {
    const page = makePage({ focusable: [] });
    await run(page);
    expect(page.off).toHaveBeenCalledWith('framenavigated', expect.any(Function));
  });

  test('cleans up listener even when focusable list is empty', async () => {
    const page = makePage({ focusable: [] });
    await run(page);
    expect(page.off).toHaveBeenCalled();
  });

  // ── Fail path: framenavigated event ──────────────────────────────────────
  test('fails when framenavigated fires during focus', async () => {
    const page = makePage({
      focusable: [{ tagName: 'button', id: 'nav-btn', stableSel: '#nav-btn', html: '<button id="nav-btn">Go</button>' }],
      navigates: true,
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].impact).toBe('serious');
    expect(result.rules[0].reason).toContain('button');
  });

  // ── Fail path: URL changed ─────────────────────────────────────────────────
  test('fails when URL path changes after focus', async () => {
    let callCount = 0;
    const page = {
      evaluate: jest.fn().mockImplementation((fn) => {
        const src = String(fn);
        if (src.includes('results.push({')) return Promise.resolve([
          { tagName: 'a', id: 'link1', stableSel: '#link1', html: '<a id="link1">Go</a>' },
        ]);
        if (src.includes('count > 0')) return Promise.resolve(false);
        return Promise.resolve(undefined);
      }),
      url: jest.fn().mockImplementation(() => {
        callCount++;
        // The check calls url() three times for one element: initialUrl (1),
        // urlBefore (2, inside loop), currentUrl (3, after focus). We need
        // urlBefore !== currentUrl, so flip the path on the 3rd call.
        return callCount <= 2 ? 'https://example.com/page1' : 'https://example.com/page2';
      }),
      on: jest.fn(),
      off: jest.fn(),
    };
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
  });

  // ── Fail reason format ────────────────────────────────────────────────────
  test('fail reason includes element tag name', async () => {
    const page = makePage({
      focusable: [{ tagName: 'select', id: 'sel1', stableSel: '#sel1', html: '<select id="sel1">' }],
      navigates: true,
    });
    const result = await run(page);
    expect(result.rules[0].reason).toContain('select');
  });

  test('fail reason includes element id when present', async () => {
    const page = makePage({
      focusable: [{ tagName: 'input', id: 'my-input', stableSel: '#my-input', html: '<input id="my-input">' }],
      navigates: true,
    });
    const result = await run(page);
    expect(result.rules[0].reason).toContain('my-input');
  });

  test('fail reason still works when element has no id', async () => {
    const page = makePage({
      focusable: [{ tagName: 'button', id: null, stableSel: null, html: '<button>Click</button>' }],
      navigates: true,
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('button');
  });

  // ── SELECTOR validation ────────────────────────────────────────────────────
  test('SELECTOR (N7 fix): does not start with a comma and is a valid CSS selector string', () => {
    expect(SELECTOR).not.toBeNull();
    expect(SELECTOR.trimStart()).not.toMatch(/^,/);
    const parts = SELECTOR.split(',').map(s => s.trim());
    expect(parts.every(p => p.length > 0)).toBe(true);
  });

  test('SELECTOR includes form controls', () => {
    expect(SELECTOR).toContain('input');
    expect(SELECTOR).toContain('select');
    expect(SELECTOR).toContain('textarea');
  });

  test('source contains SPA-navigation detection + cleanup logic', () => {
    const src = require('fs').readFileSync(
      require('path').resolve(__dirname, '../../src/custom-checks/on-focus.check.js'),
      'utf8'
    );
    // Current implementation detects SPA navigation via a pushState counter
    // (__navChanges) plus the framenavigated event, and cleans up the listener
    // with page.off('framenavigated', ...).
    expect(src).toContain('__navChanges');
    expect(src).toContain('framenavigated');
  });

  // ── urlPathAndSearch ───────────────────────────────────────────────────────
  test('hash-only navigation is NOT treated as a context change', async () => {
    let callCount = 0;
    const page = {
      evaluate: jest.fn().mockImplementation((fn) => {
        const src = String(fn);
        if (src.includes('results.push({')) return Promise.resolve([
          { tagName: 'a', id: 'anchor', stableSel: '#anchor', html: '<a id="anchor">#skip</a>' },
        ]);
        if (src.includes('count > 0')) return Promise.resolve(false);
        return Promise.resolve(undefined);
      }),
      url: jest.fn().mockImplementation(() => {
        callCount++;
        // Only hash changes — should NOT trigger a violation
        return callCount <= 1 ? 'https://example.com/page#section1' : 'https://example.com/page#section2';
      }),
      on: jest.fn(),
      off: jest.fn(),
    };
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
  });

  // ── SPA navigation detection ───────────────────────────────────────────────
  test('fails when SPA navigation is detected via instrumentation', async () => {
    let evaluationCount = 0;
    const page = {
      evaluate: jest.fn().mockImplementation((fn) => {
        evaluationCount++;
        const src = String(fn);
        if (src.includes('results.push({')) return Promise.resolve([
          { tagName: 'button', id: 'spa-btn', stableSel: '#spa-btn', html: '<button id="spa-btn">Nav</button>' },
        ]);
        // readAndResetNavInstrumentation returns true (SPA nav happened)
        if (src.includes('count > 0')) return Promise.resolve(true);
        return Promise.resolve(undefined);
      }),
      url: jest.fn().mockReturnValue('https://example.com/same'),
      on: jest.fn(),
      off: jest.fn(),
    };
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('button');
  });
});
