'use strict';

const {
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '3.2.2';
const RULE_ID = 'custom-on-input';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/on-input';

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
      const stateKey = '__ka11yOnInputNavState';
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

    // Technique #3: Use pre-discovered elements, filtered for inputs
    const inputs = (sharedContext.focusableElements || []).filter(el => {
      const tag = el.tagName.toLowerCase();
      const type = el.inputType;
      const isInput = tag === 'input' && !['submit', 'button', 'reset', 'hidden', 'file'].includes(type);
      return isInput || tag === 'textarea' || tag === 'select' || el.html.includes('contenteditable');
    });

    for (const inputInfo of inputs) {
      navigationDetected = false;
      const urlBefore = page.url();

      // For selects and checkboxes, we can collapse the interaction.
      // For text inputs, we still use keyboard.type for realism.
      if (inputInfo.isSelect || inputInfo.isCheckboxOrRadio) {
        const navStatus = await page.evaluate(({ idx, stableSel, isSelect, settleMs }) => {
          const findEl = () =>
            stableSel
              ? (document.querySelector(stableSel) ||
                 Array.from(document.querySelectorAll('*'))[idx])
              : Array.from(document.querySelectorAll('*'))[idx];

          const el = findEl();
          if (!el) return { spaNavChanged: false };
          
          el.focus({ preventScroll: true });
          if (isSelect) {
            if (el.options && el.options.length >= 2) {
              el.selectedIndex = el.selectedIndex === 0 ? 1 : 0;
              el.dispatchEvent(new Event('change', { bubbles: true }));
            }
          } else {
            el.click();
          }

          return new Promise((resolve) => {
            setTimeout(() => {
              const s = window.__ka11yOnInputNavState;
              const spaNavChanged = !!(s && s.count > 0);
              if (s) s.count = 0;
              resolve({ spaNavChanged });
            }, settleMs);
          });
        }, { 
          idx: inputInfo.idx, 
          stableSel: inputInfo.stableSel, 
          isSelect: inputInfo.isSelect, 
          settleMs: 120 
        });

        const currentUrl = page.url();
        if (navigationDetected || navStatus.spaNavChanged || currentUrl !== urlBefore) {
          violations.push(inputInfo);
          break;
        }

        // Clean up select/checkbox
        if (inputInfo.isCheckboxOrRadio) {
           await page.evaluate(({ idx, stableSel }) => {
             const findEl = () =>
               stableSel
                 ? (document.querySelector(stableSel) ||
                    Array.from(document.querySelectorAll('*'))[idx])
                 : Array.from(document.querySelectorAll('*'))[idx];
             const el = findEl();
             if (el) el.click();
           }, { idx: inputInfo.idx, stableSel: inputInfo.stableSel });
        }
      } else {
        // Text inputs: focus, type, wait, check
        await page.evaluate(({ idx, stableSel }) => {
          const findEl = () =>
            stableSel
              ? (document.querySelector(stableSel) ||
                 Array.from(document.querySelectorAll('*'))[idx])
              : Array.from(document.querySelectorAll('*'))[idx];
          const el = findEl();
          if (el) el.focus({ preventScroll: true });
        }, { idx: inputInfo.idx, stableSel: inputInfo.stableSel });

        const char = TYPE_CHAR[inputInfo.inputType] || TYPE_CHAR.default;
        await page.keyboard.type(char);
        await new Promise(r => setTimeout(r, 120));

        const currentUrl = page.url();
        const spaNavChanged = await page.evaluate(() => {
          const s = window.__ka11yOnInputNavState;
          const changed = !!(s && s.count > 0);
          if (s) s.count = 0;
          return changed;
        }).catch(() => false);

        if (navigationDetected || spaNavChanged || currentUrl !== urlBefore) {
          violations.push(inputInfo);
          break;
        }

        // Clean up text input
        const charLen = char.length;
        for (let b = 0; b < charLen; b++) await page.keyboard.press('Backspace');
      }
    }
  } finally {
    page.off('framenavigated', onNavigated);
    // Restore the original history methods and remove our listeners so the page
    // is left exactly as we found it (no leaked instrumentation between checks).
    await page.evaluate(() => {
      const stateKey = '__ka11yOnInputNavState';
      const s = window[stateKey];
      if (!s) return;
      try {
        if (s.originalPush) history.pushState = s.originalPush;
        if (s.originalReplace) history.replaceState = s.originalReplace;
        if (s.onPop) {
          window.removeEventListener('popstate', s.onPop);
          window.removeEventListener('hashchange', s.onPop);
        }
      } catch (_) { /* best-effort restore */ }
      delete window[stateKey];
    }).catch(() => {});
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
