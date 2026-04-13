'use strict';

const {
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '3.2.2';
const RULE_ID = 'custom-on-input';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/on-input';
const MAX_INPUTS = 30;
const SETTLE_MS = 120;

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

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);
  const violations = [];
  let navigationDetected = false;
  const initialUrl = page.url();

  const onNavigated = () => { navigationDetected = true; };
  page.on('framenavigated', onNavigated);

  try {
    // Inject SPA navigation detection via pushState/replaceState interception
    await page.evaluate(() => {
      window.__navChanges = 0;
      const orig = history.pushState.bind(history);
      history.pushState = function(...args) { window.__navChanges++; return orig(...args); };
      const origReplace = history.replaceState.bind(history);
      history.replaceState = function(...args) { window.__navChanges++; return origReplace(...args); };
    });

    const inputs = await page.evaluate((sel, max) => {
      return Array.from(document.querySelectorAll(sel)).slice(0, max).map((el, i) => ({
        index: i,
        tagName: el.tagName.toLowerCase(),
        type: (el.getAttribute('type') || el.tagName).toLowerCase(),
        id: el.id || null,
        isSelect: el.tagName.toLowerCase() === 'select',
        isCheckboxOrRadio: ['checkbox', 'radio'].includes((el.getAttribute('type') || '').toLowerCase()),
        html: el.outerHTML.slice(0, 150),
      }));
    }, SELECTOR, MAX_INPUTS);

    for (const inputInfo of (inputs || [])) {
      navigationDetected = false;
      const urlBefore = page.url();

      await page.evaluate((sel, idx) => {
        const el = document.querySelectorAll(sel)[idx];
        if (el) el.focus({ preventScroll: true });
      }, SELECTOR, inputInfo.index);

      if (inputInfo.isSelect) {
        // For selects: change selection value programmatically and fire change event
        await page.evaluate((sel, idx) => {
          const el = document.querySelectorAll(sel)[idx];
          if (!el || el.options.length < 2) return;
          el.selectedIndex = el.selectedIndex === 0 ? 1 : 0;
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }, SELECTOR, inputInfo.index);
      } else if (inputInfo.isCheckboxOrRadio) {
        // For checkbox/radio: click to toggle and fire change event (B8)
        await page.evaluate((sel, idx) => {
          const el = document.querySelectorAll(sel)[idx];
          if (el) el.click();
        }, SELECTOR, inputInfo.index);
      } else {
        const char = TYPE_CHAR[inputInfo.type] || TYPE_CHAR.default;
        await page.keyboard.type(char);
      }

      await new Promise(r => setTimeout(r, SETTLE_MS));

      const currentUrl = page.url();
      const spaNavChanged = await page.evaluate(() => window.__navChanges > 0).catch(() => false);
      if (spaNavChanged) {
        await page.evaluate(() => { window.__navChanges = 0; }).catch(() => {});
      }

      if (navigationDetected || spaNavChanged || currentUrl !== urlBefore) {
        violations.push(inputInfo);
        break; // page may have navigated; can't continue safely
      }
      // Reset SPA counter for next element
      await page.evaluate(() => { window.__navChanges = 0; }).catch(() => {});

      // Clean up: restore original state
      if (!inputInfo.isSelect && !inputInfo.isCheckboxOrRadio) {
        // Remove typed character(s) — length varies by type (url/email use multi-char values)
        const charLen = (TYPE_CHAR[inputInfo.type] || TYPE_CHAR.default).length;
        for (let b = 0; b < charLen; b++) await page.keyboard.press('Backspace');
      } else if (inputInfo.isCheckboxOrRadio) {
        // Toggle back to original state
        await page.evaluate((sel, idx) => {
          const el = document.querySelectorAll(sel)[idx];
          if (el) el.click();
        }, SELECTOR, inputInfo.index);
      }
    }
  } finally {
    page.off('framenavigated', onNavigated);
  }

  if (violations.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: 'Changing an input value must not trigger a context change', impact: null, status: 'pass', reason: _t(sharedContext, 'No unexpected context changes detected on input.', '入力値の変更による予期しないコンテキスト変更は検出されませんでした。'), helpUrl: HELP_URL }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Changing an input value must not trigger a context change',
      impact: 'serious',
      status: 'fail',
      reason: _t(sharedContext, 'Changing {element} triggered an unexpected navigation or context change.', '{element} の値を変更した際、予期しないナビゲーションまたはコンテキスト変更が発生しました。', { element: `<${violations[0].tagName}${violations[0].id ? ` id="${violations[0].id}"` : ''}>` }),
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
