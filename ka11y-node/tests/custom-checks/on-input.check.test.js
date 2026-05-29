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

const { SELECTOR: INPUT_SELECTOR } = (() => {
  const src = require('fs').readFileSync(require('path').resolve(__dirname, '../../src/custom-checks/on-input.check.js'), 'utf8');
  const match = src.match(/^const SELECTOR\s*=\s*([\s\S]*?)\.join\((.*?)\)/m);
  if (!match) return { SELECTOR: null };
  try {
    // eslint-disable-next-line no-new-func
    const SELECTOR = Function(`"use strict"; return (${match[1]}).join(${match[2]})`)();
    return { SELECTOR };
  } catch (_) { return { SELECTOR: null }; }
})();

describe('on-input.check (WCAG 3.2.2)', () => {
  // ── Module exports ─────────────────────────────────────────────────────────
  test('exports SC as 3.2.2', () => { expect(SC).toBe('3.2.2'); });
  test('exports RULE_ID as custom-on-input', () => { expect(RULE_ID).toBe('custom-on-input'); });
  test('exports HELP_URL', () => { expect(HELP_URL).toContain('on-input'); });

  // ── SELECTOR validation ────────────────────────────────────────────────────
  test('SELECTOR (N8 fix): is a valid flat CSS selector with no stray :not() fragments', () => {
    expect(INPUT_SELECTOR).not.toBeNull();
    expect(INPUT_SELECTOR.trimStart()).not.toMatch(/^,/);
    const parts = INPUT_SELECTOR.split(',').map(s => s.trim());
    parts.forEach(p => {
      expect(p).toMatch(/^[a-zA-Z\[.#]/);
    });
  });

  test('SELECTOR includes textarea and select', () => {
    expect(INPUT_SELECTOR).toContain('textarea');
    expect(INPUT_SELECTOR).toContain('select');
  });

  test('SELECTOR includes contenteditable', () => {
    expect(INPUT_SELECTOR).toContain('contenteditable');
  });

  // ── Pass paths ─────────────────────────────────────────────────────────────
  test('passes when no inputs exist', async () => {
    const page = makePage({ inputs: [] });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('3.2.2');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].ruleId).toBe('custom-on-input');
    expect(result.rules[0].impact).toBeNull();
    expect(result.rules[0].helpUrl).toBe(HELP_URL);
  });

  test('passes when inputs do not trigger context change', async () => {
    const page = makePage({
      inputs: [{ index: 0, tagName: 'input', type: 'text', id: 'name', stableSel: '#name', html: '<input id="name">', isSelect: false, isCheckboxOrRadio: false }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('No unexpected context changes');
  });

  test('passes with select input that does not navigate', async () => {
    const page = makePage({
      inputs: [{ index: 0, tagName: 'select', type: 'select', id: 'country', stableSel: '#country', html: '<select id="country">', isSelect: true, isCheckboxOrRadio: false }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
  });

  test('passes with checkbox input that does not navigate', async () => {
    const page = makePage({
      inputs: [{ index: 0, tagName: 'input', type: 'checkbox', id: 'agree', stableSel: '#agree', html: '<input type="checkbox" id="agree">', isSelect: false, isCheckboxOrRadio: true }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
  });

  test('passes with multiple input types that do not navigate', async () => {
    const page = makePage({
      inputs: [
        { index: 0, tagName: 'input',    type: 'text',     id: 'q1', stableSel: '#q1', html: '<input type="text">',     isSelect: false, isCheckboxOrRadio: false },
        { index: 1, tagName: 'select',   type: 'select',   id: 'q2', stableSel: '#q2', html: '<select>',               isSelect: true,  isCheckboxOrRadio: false },
        { index: 2, tagName: 'input',    type: 'radio',    id: 'q3', stableSel: '#q3', html: '<input type="radio">',   isSelect: false, isCheckboxOrRadio: true  },
        { index: 3, tagName: 'textarea', type: 'textarea', id: 'q4', stableSel: '#q4', html: '<textarea>',             isSelect: false, isCheckboxOrRadio: false },
      ],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
  });

  // ── Fail: URL change ──────────────────────────────────────────────────────
  test('fails when URL path changes after input', async () => {
    let callCount = 0;
    const page = {
      evaluate: jest.fn().mockImplementation((fn) => {
        const src = String(fn);
        if (src.includes('isCheckboxOrRadio')) return Promise.resolve([
          { index: 0, tagName: 'select', type: 'select', id: 'lang', stableSel: '#lang', html: '<select id="lang">', isSelect: true, isCheckboxOrRadio: false },
        ]);
        if (src.includes('count > 0')) return Promise.resolve(false);
        return Promise.resolve(undefined);
      }),
      url: jest.fn().mockImplementation(() => {
        callCount++;
        return callCount <= 1 ? 'https://example.com/en' : 'https://example.com/fr';
      }),
      keyboard: { type: jest.fn().mockResolvedValue(undefined), press: jest.fn().mockResolvedValue(undefined) },
      on: jest.fn(),
      off: jest.fn(),
    };
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].impact).toBe('serious');
    expect(result.rules[0].reason).toContain('select');
  });

  // ── Fail: SPA navigation ──────────────────────────────────────────────────
  test('fails when SPA navigation is detected via instrumentation', async () => {
    const page = {
      evaluate: jest.fn().mockImplementation((fn) => {
        const src = String(fn);
        if (src.includes('isCheckboxOrRadio')) return Promise.resolve([
          { index: 0, tagName: 'input', type: 'text', id: 'search', stableSel: '#search', html: '<input id="search">', isSelect: false, isCheckboxOrRadio: false },
        ]);
        if (src.includes('count > 0')) return Promise.resolve(true); // SPA nav happened
        return Promise.resolve(undefined);
      }),
      url: jest.fn().mockReturnValue('https://example.com/same'),
      keyboard: { type: jest.fn().mockResolvedValue(undefined), press: jest.fn().mockResolvedValue(undefined) },
      on: jest.fn(),
      off: jest.fn(),
    };
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
  });

  // ── Fail: framenavigated ──────────────────────────────────────────────────
  test('fails when framenavigated fires during input interaction', async () => {
    let navListener = null;
    let focusCalled = false;
    const page = {
      evaluate: jest.fn().mockImplementation((fn) => {
        const src = String(fn);
        if (src.includes('isCheckboxOrRadio')) return Promise.resolve([
          { index: 0, tagName: 'input', type: 'text', id: 'q', stableSel: '#q', html: '<input id="q">', isSelect: false, isCheckboxOrRadio: false },
        ]);
        if (src.includes('count > 0')) return Promise.resolve(false);
        // Trigger nav when focus is set
        if (!focusCalled && src.includes('el.focus(')) {
          focusCalled = true;
          if (navListener) navListener();
        }
        return Promise.resolve(undefined);
      }),
      url: jest.fn().mockReturnValue('https://example.com/same'),
      keyboard: { type: jest.fn().mockResolvedValue(undefined), press: jest.fn().mockResolvedValue(undefined) },
      on: jest.fn((event, cb) => { if (event === 'framenavigated') navListener = cb; }),
      off: jest.fn(),
    };
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
  });

  // ── Cleanup ───────────────────────────────────────────────────────────────
  test('always cleans up framenavigated listener', async () => {
    const page = makePage({ inputs: [] });
    await run(page);
    expect(page.off).toHaveBeenCalledWith('framenavigated', expect.any(Function));
  });

  test('cleans up listener even when there are violations', async () => {
    let callCount = 0;
    const page = {
      evaluate: jest.fn().mockImplementation((fn) => {
        const src = String(fn);
        if (src.includes('isCheckboxOrRadio')) return Promise.resolve([
          { index: 0, tagName: 'select', type: 'select', id: 's', stableSel: '#s', html: '<select id="s">', isSelect: true, isCheckboxOrRadio: false },
        ]);
        if (src.includes('count > 0')) return Promise.resolve(false);
        return Promise.resolve(undefined);
      }),
      url: jest.fn().mockImplementation(() => {
        callCount++;
        return callCount <= 1 ? 'https://example.com/a' : 'https://example.com/b';
      }),
      keyboard: { type: jest.fn(), press: jest.fn() },
      on: jest.fn(),
      off: jest.fn(),
    };
    await run(page);
    expect(page.off).toHaveBeenCalledWith('framenavigated', expect.any(Function));
  });

  // ── Fail reason format ────────────────────────────────────────────────────
  test('fail reason includes element tagName and id', async () => {
    let callCount = 0;
    const page = {
      evaluate: jest.fn().mockImplementation((fn) => {
        const src = String(fn);
        if (src.includes('isCheckboxOrRadio')) return Promise.resolve([
          { index: 0, tagName: 'select', type: 'select', id: 'my-sel', stableSel: '#my-sel', html: '<select id="my-sel">', isSelect: true, isCheckboxOrRadio: false },
        ]);
        if (src.includes('count > 0')) return Promise.resolve(false);
        return Promise.resolve(undefined);
      }),
      url: jest.fn().mockImplementation(() => {
        callCount++;
        return callCount <= 1 ? 'https://example.com/p1' : 'https://example.com/p2';
      }),
      keyboard: { type: jest.fn(), press: jest.fn() },
      on: jest.fn(),
      off: jest.fn(),
    };
    const result = await run(page);
    expect(result.rules[0].reason).toContain('select');
    expect(result.rules[0].reason).toContain('my-sel');
  });

  test('fail reason without id still mentions tag', async () => {
    let callCount = 0;
    const page = {
      evaluate: jest.fn().mockImplementation((fn) => {
        const src = String(fn);
        if (src.includes('isCheckboxOrRadio')) return Promise.resolve([
          { index: 0, tagName: 'input', type: 'text', id: null, stableSel: null, html: '<input>', isSelect: false, isCheckboxOrRadio: false },
        ]);
        if (src.includes('count > 0')) return Promise.resolve(false);
        return Promise.resolve(undefined);
      }),
      url: jest.fn().mockImplementation(() => {
        callCount++;
        return callCount <= 1 ? 'https://example.com/a' : 'https://example.com/b';
      }),
      keyboard: { type: jest.fn(), press: jest.fn() },
      on: jest.fn(),
      off: jest.fn(),
    };
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('input');
  });

  // ── TYPE_CHAR: different input types use correct test values ──────────────
  test('uses keyboard.type for text inputs', async () => {
    const page = makePage({
      inputs: [{ index: 0, tagName: 'input', type: 'text', id: 't', stableSel: '#t', html: '<input type="text" id="t">', isSelect: false, isCheckboxOrRadio: false }],
    });
    await run(page);
    expect(page.keyboard.type).toHaveBeenCalled();
  });

  test('uses keyboard.type for textarea', async () => {
    const page = makePage({
      inputs: [{ index: 0, tagName: 'textarea', type: 'textarea', id: 'ta', stableSel: '#ta', html: '<textarea id="ta">', isSelect: false, isCheckboxOrRadio: false }],
    });
    await run(page);
    expect(page.keyboard.type).toHaveBeenCalled();
  });

  test('does not call keyboard.type for select inputs', async () => {
    const page = makePage({
      inputs: [{ index: 0, tagName: 'select', type: 'select', id: 'sel', stableSel: '#sel', html: '<select id="sel">', isSelect: true, isCheckboxOrRadio: false }],
    });
    await run(page);
    expect(page.keyboard.type).not.toHaveBeenCalled();
  });

  // ── Source validation ─────────────────────────────────────────────────────
  test('restores history instrumentation in source cleanup path', () => {
    const src = require('fs').readFileSync(
      require('path').resolve(__dirname, '../../src/custom-checks/on-input.check.js'),
      'utf8'
    );
    expect(src).toContain('originalPush');
    expect(src).toContain('delete window[stateKey]');
  });
});
