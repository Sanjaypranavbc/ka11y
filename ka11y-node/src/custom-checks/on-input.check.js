'use strict';

const SC = '3.2.2';
const RULE_ID = 'custom-on-input';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/on-input';
const MAX_INPUTS = 30;
const SETTLE_MS = 120;
const NAV_STATE_KEY = '__ka11yOnInputNavState';

// Safe test values per input type — use syntactically valid values to avoid
// triggering browser validation events that could cause false-positive navigations (B9).
const TYPE_CHAR = {
  number: '1', tel: '1', range: '1',
  email: 'a@b.co',        // valid partial email — avoids 'invalid' event on email inputs
  url: 'https://x.com',   // valid URL — avoids 'invalid' event on url inputs
  search: 'a', text: 'a', textarea: 'a', default: 'a',
};

// Selector now includes checkbox and radio — toggling these is a common source of
// on-input context changes (B8: they were previously excluded from testing).
// Also includes contenteditable elements which can receive user input.
const SELECTOR = [
  'input:not([type="submit"]):not([type="button"]):not([type="reset"]):not([type="hidden"]):not([type="file"]):not([disabled])',
  'textarea:not([disabled])',
  'select:not([disabled])',
  '[contenteditable="true"]',
  '[contenteditable=""]',
].join(', ');

function urlPathAndSearch(url) {
  try { const u = new URL(url); return u.pathname + u.search; } catch { return url; }
}

async function installNavInstrumentation(page) {
  await page.evaluate((stateKey) => {
    const existing = window[stateKey];
    if (existing && existing.originalPush && existing.originalReplace) {
      existing.count = 0;
      return;
    }

    const originalPush = history.pushState.bind(history);
    const originalReplace = history.replaceState.bind(history);
    window[stateKey] = {
      count: 0,
      originalPush,
      originalReplace,
    };

    history.pushState = function(...args) {
      window[stateKey].count++;
      return originalPush(...args);
    };
    history.replaceState = function(...args) {
      window[stateKey].count++;
      return originalReplace(...args);
    };
  }, NAV_STATE_KEY);
}

async function readAndResetNavInstrumentation(page) {
  return page.evaluate((stateKey) => {
    const state = window[stateKey];
    const changed = !!(state && state.count > 0);
    if (state) state.count = 0;
    return changed;
  }, NAV_STATE_KEY).catch(() => false);
}

async function uninstallNavInstrumentation(page) {
  await page.evaluate((stateKey) => {
    const state = window[stateKey];
    if (!state) return;
    if (state.originalPush) history.pushState = state.originalPush;
    if (state.originalReplace) history.replaceState = state.originalReplace;
    delete window[stateKey];
  }, NAV_STATE_KEY).catch(() => {});
}

async function run(page) {
  const violations = [];
  let navigationDetected = false;

  const onNavigated = () => { navigationDetected = true; };
  page.on('framenavigated', onNavigated);

  try {
    await installNavInstrumentation(page);

    const inputs = await page.evaluate((sel, max) => {
      const idCounts = {};
      for (const el of document.querySelectorAll('[id]')) {
        idCounts[el.id] = (idCounts[el.id] || 0) + 1;
      }
      return Array.from(document.querySelectorAll(sel)).slice(0, max).map((el, i) => ({
        index: i,
        tagName: el.tagName.toLowerCase(),
        type: (el.getAttribute('type') || el.tagName).toLowerCase(),
        id: el.id || null,
        stableSel: el.id && idCounts[el.id] === 1 ? `#${CSS.escape(el.id)}` : null,
        isSelect: el.tagName.toLowerCase() === 'select',
        isCheckboxOrRadio: ['checkbox', 'radio'].includes((el.getAttribute('type') || '').toLowerCase()),
        html: el.outerHTML.slice(0, 150),
      }));
    }, SELECTOR, MAX_INPUTS);

    for (const inputInfo of (inputs || [])) {
      navigationDetected = false;
      const urlBefore = page.url();

      await page.evaluate((sel, idx, stableSel) => {
        const all = Array.from(document.querySelectorAll(sel));
        const el = stableSel
          ? (document.querySelector(stableSel) || all[idx])
          : all[idx];
        if (el) el.focus({ preventScroll: true });
      }, SELECTOR, inputInfo.index, inputInfo.stableSel || null);

      if (inputInfo.isSelect) {
        // For selects: change selection value programmatically and fire change event
        await page.evaluate((sel, idx, stableSel) => {
          const all = Array.from(document.querySelectorAll(sel));
          const el = stableSel
            ? (document.querySelector(stableSel) || all[idx])
            : all[idx];
          if (!el || el.options.length < 2) return;
          el.selectedIndex = el.selectedIndex === 0 ? 1 : 0;
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }, SELECTOR, inputInfo.index, inputInfo.stableSel || null);
      } else if (inputInfo.isCheckboxOrRadio) {
        // For checkbox/radio: click to toggle and fire change event (B8)
        await page.evaluate((sel, idx, stableSel) => {
          const all = Array.from(document.querySelectorAll(sel));
          const el = stableSel
            ? (document.querySelector(stableSel) || all[idx])
            : all[idx];
          if (el) el.click();
        }, SELECTOR, inputInfo.index, inputInfo.stableSel || null);
      } else {
        const char = TYPE_CHAR[inputInfo.type] || TYPE_CHAR.default;
        await page.keyboard.type(char);
      }

      await new Promise(r => setTimeout(r, SETTLE_MS));

      const currentUrl = page.url();
      const spaNavChanged = await readAndResetNavInstrumentation(page);

      if (navigationDetected || spaNavChanged || urlPathAndSearch(currentUrl) !== urlPathAndSearch(urlBefore)) {
        violations.push(inputInfo);
        break; // page may have navigated; can't continue safely
      }

      // Clean up: restore original state
      if (!inputInfo.isSelect && !inputInfo.isCheckboxOrRadio) {
        // Remove typed character(s) — length varies by type (url/email use multi-char values)
        const charLen = (TYPE_CHAR[inputInfo.type] || TYPE_CHAR.default).length;
        for (let b = 0; b < charLen; b++) await page.keyboard.press('Backspace');
      } else if (inputInfo.isCheckboxOrRadio) {
        // Toggle back to original state
        await page.evaluate((sel, idx, stableSel) => {
          const all = Array.from(document.querySelectorAll(sel));
          const el = stableSel
            ? (document.querySelector(stableSel) || all[idx])
            : all[idx];
          if (el) el.click();
        }, SELECTOR, inputInfo.index, inputInfo.stableSel || null);
      }
    }
  } finally {
    page.off('framenavigated', onNavigated);
    await uninstallNavInstrumentation(page);
  }

  if (violations.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: 'Changing an input value must not trigger a context change', impact: null, status: 'pass', reason: 'No unexpected context changes detected on input.', helpUrl: HELP_URL }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Changing an input value must not trigger a context change',
      impact: 'serious',
      status: 'fail',
      reason: `Changing <${violations[0].tagName}${violations[0].id ? ` id="${violations[0].id}"` : ''}> triggered an unexpected navigation or context change.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
