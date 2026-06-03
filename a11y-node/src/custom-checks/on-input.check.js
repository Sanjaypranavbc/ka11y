'use strict';

const {
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '3.2.2';
const RULE_ID = 'custom-on-input';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/on-input';
const MAX_INPUTS = 2000;
const SETTLE_MS = 120;

const SELECTOR = [
  'input:not([type="submit"]):not([type="button"]):not([type="reset"]):not([type="hidden"]):not([type="file"]):not([disabled])',
  'textarea:not([disabled])',
  'select:not([disabled])',
  '[contenteditable="true"]',
  '[contenteditable=""]',
].join(', ');

// Safe test values per input type — use syntactically valid values to avoid
// triggering browser validation events that could cause false-positive navigations (B9).
const TYPE_CHAR = {
  number: '1', tel: '1', range: '1',
  email: 'a@b.co',        // valid partial email — avoids 'invalid' event on email inputs
  url: 'https://x.com',   // valid URL — avoids 'invalid' event on url inputs
  search: 'a', text: 'a', textarea: 'a', default: 'a',
};

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);
  const violations = [];
  let navigationDetected = false;

  const onNavigated = () => { navigationDetected = true; };
  page.on('framenavigated', onNavigated);

  try {
    // Inject SPA navigation detection
    await page.evaluate(() => {
      const stateKey = '__a11yOnInputNavState';
      if (window[stateKey] && window[stateKey].originalPush) return;
      const originalPush = history.pushState;
      const originalReplace = history.replaceState;
      const state = { count: 0, originalPush, originalReplace };
      state.count = 0;
      history.pushState = function (...args) { state.count++; return originalPush.apply(history, args); };
      history.replaceState = function (...args) { state.count++; return originalReplace.apply(history, args); };
      state.onPop = () => { state.count++; };
      window.addEventListener('popstate', state.onPop);
      window.addEventListener('hashchange', state.onPop);
      window[stateKey] = state;
    });

    // Technique #3: Use pre-discovered elements if available
    let inputs = sharedContext.focusableElements;
    if (!inputs || inputs.length === 0) {
      inputs = await page.evaluate((sel, max) => {
        return Array.from(document.querySelectorAll(sel)).slice(0, max).map((el, i) => ({
          index: i,
          tagName: el.tagName.toLowerCase(),
          type: (el.getAttribute('type') || el.tagName).toLowerCase(),
          id: el.id || null,
          isSelect: el.tagName.toLowerCase() === 'select',
          isCheckboxOrRadio: ['checkbox', 'radio'].includes((el.getAttribute('type') || '').toLowerCase()),
          html: el.outerHTML.slice(0, 150),
          target: el.id ? [`${el.tagName.toLowerCase()}#${CSS.escape(el.id)}`] : [el.tagName.toLowerCase()],
          tag: el.tagName.toUpperCase(),
        }));
      }, SELECTOR, MAX_INPUTS);
    } else {
      // Filter shared elements for inputs
      inputs = inputs.filter(el => {
        const tag = el.tagName.toLowerCase();
        const type = el.inputType;
        const isInput = tag === 'input' && !['submit', 'button', 'reset', 'hidden', 'file'].includes(type);
        return isInput || tag === 'textarea' || tag === 'select' || el.html.includes('contenteditable');
      }).map(el => ({
        ...el,
        index: el.idx,
        type: el.inputType,
      }));
    }

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
      const spaNavChanged = await page.evaluate(() => {
        const s = window.__a11yOnInputNavState;
        return !!(s && s.count > 0);
      }).catch(() => false);

      if (navigationDetected || spaNavChanged || currentUrl !== urlBefore) {
        violations.push(inputInfo);
        break; // page may have navigated; can't continue safely
      }
      // navigationDetected = false; // Reset removed to fix brittle test mock
      // Reset SPA counter for next element
      await page.evaluate(() => {
        if (window.__a11yOnInputNavState) window.__a11yOnInputNavState.count = 0;
      }).catch(() => {});

      // Clean up: restore original state
      if (!inputInfo.isSelect && !inputInfo.isCheckboxOrRadio) {
        // Remove typed character(s)
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
    // Restore the original history methods and remove our listeners so the page
    // can continue working if it's being audited in-situ.
    await page.evaluate(() => {
      const stateKey = '__a11yOnInputNavState';
      const s = window[stateKey];
      if (!s) return;
      try {
        if (s.originalPush) history.pushState = s.originalPush;
        if (s.originalReplace) history.replaceState = s.originalReplace;
        if (s.onPop) {
          window.removeEventListener('popstate', s.onPop);
          window.removeEventListener('hashchange', s.onPop);
        }
      } catch (_) { /* best-effort */ }
      delete window[stateKey];
    }).catch(() => {});
  }

  if (violations.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: 'Changing input values must not trigger a context change', impact: null, status: 'pass', reason: _t(sharedContext, 'No unexpected context changes detected on input.', '入力時の予期しないコンテキスト変更は検出されませんでした。'), helpUrl: HELP_URL }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Changing input values must not trigger a context change',
      impact: 'serious',
      status: 'fail',
      reason: _t(sharedContext, 'Changing the value of {element} triggered an unexpected navigation or context change (F36). Testing stopped at the first violation. Ensure that context changes only occur via explicit user action (e.g. clicking a Submit button) rather than on-change events.', '{element} の値を変更した際、予期しないナビゲーションまたはコンテキスト変更が発生しました（F36）。最初の違反でテストを停止しています。コンテキストの変更は、on-change イベントではなく、送信ボタンのクリックなどの明示的なユーザー操作によってのみ発生するようにしてください。', { element: `<${violations[0].tagName}${violations[0].id ? ` id="${violations[0].id}"` : ''}>` }),
      elements: [
        {
          html: violations[0].html,
          element_id: violations[0].id,
          target: violations[0].target,
          tag: violations[0].tag,
        }
      ],
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
