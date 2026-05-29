'use strict';

const {
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '3.2.1';
const RULE_ID = 'custom-on-focus';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/on-focus';

const SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
  '[contenteditable="true"]',
  '[contenteditable=""]',
].join(', ');

// Compare only pathname + search (not hash) to avoid false positives on skip-links
// and hash-based anchor navigation (B7), while still catching real navigations (B10).
function urlPathAndSearch(url) {
  try { const u = new URL(url); return u.pathname + u.search; } catch { return url; }
}

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);
  const violations = [];
  let navigationDetected = false;
  function onNavigated() { navigationDetected = true; }
  page.on('framenavigated', onNavigated);

  // Technique #3: Use pre-discovered elements from context
  // Fallback to discovery if context is empty (e.g. in unit tests)
  let focusable = sharedContext.focusableElements;
  if (!focusable || focusable.length === 0) {
    const { discoverPageElements } = require('./sharedAssets');
    focusable = await discoverPageElements(page, SELECTOR);
  }

  try {
    // Inject SPA navigation detection: wrap history.pushState/replaceState (and
    // listen for popstate/hashchange) behind a per-page state object (__navChanges)
    // so we can count programmatic navigations and later restore the originals.
    await page.evaluate(() => {
      const stateKey = '__navChanges';
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

    for (let i = 0; i < focusable.length; i++) {
      const el = focusable[i];
      const urlBefore = page.url();

      // ── L-1: collapsed per-element round-trip ──
      // Focus element and wait for settlement browser-side.
      // Returns the SPA navigation count to detect context changes without extra RTs.
      const navStatus = await page.evaluate(({ idx, stableSel, settleMs }) => {
        const findEl = () =>
          stableSel
            ? (document.querySelector(stableSel) ||
               Array.from(document.querySelectorAll('*'))[idx])
            : Array.from(document.querySelectorAll('*'))[idx];

        const e = findEl();
        if (e) e.focus({ preventScroll: true });

        return new Promise((resolve) => {
          const wait = (cb) => {
            const cs = e ? window.getComputedStyle(e) : null;
            const hasTransition = cs && (cs.transitionDuration !== '0s' || cs.animationDuration !== '0s');
            if (!hasTransition) {
              requestAnimationFrame(() => requestAnimationFrame(cb));
            } else {
              setTimeout(cb, settleMs);
            }
          };

          wait(() => {
            const s = window.__navChanges;
            const spaNavChanged = !!(s && s.count > 0);
            if (s) s.count = 0; // Reset for next element
            resolve({ spaNavChanged });
          });
        });
      }, { idx: el.idx, stableSel: el.stableSel, settleMs: 100 });

      const currentUrl = page.url();
      // Only flag pathname/search changes — hash-only changes (skip-links, anchor navigation)
      // are not a WCAG 3.2.1 context change.
      if (navigationDetected || navStatus.spaNavChanged || urlPathAndSearch(currentUrl) !== urlPathAndSearch(urlBefore)) {
        violations.push(el);
        break; // page may have navigated; unsafe to continue testing other elements
      }
      navigationDetected = false; // Reset for next element
    }
  } finally {
    page.off('framenavigated', onNavigated);
    // Restore the original history methods and remove our listeners.
    await page.evaluate(() => {
      const stateKey = '__navChanges';
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
      rules: [{ ruleId: RULE_ID, description: 'Focusing an element must not trigger a context change', impact: null, status: 'pass', reason: _t(sharedContext, 'No unexpected context changes detected on focus.', 'フォーカス時に予期しないコンテキスト変更は検出されませんでした。'), helpUrl: HELP_URL }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Focusing an element must not trigger a context change',
      impact: 'serious',
      status: 'fail',
      reason: _t(sharedContext, 'Focusing {element} triggered an unexpected navigation or context change. Testing stopped at the first violation — additional elements may be affected. Review all focusable elements for focus-triggered navigation.', '{element} にフォーカスした際、予期しないナビゲーションまたはコンテキスト変更が発生しました。最初の違反でテストを停止しているため、他の要素にも影響がある可能性があります。フォーカスで遷移が起きないか、すべてのフォーカス可能要素を確認してください。', { element: `<${violations[0].tagName}${violations[0].id ? ` id="${violations[0].id}"` : ''}>` }),
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
