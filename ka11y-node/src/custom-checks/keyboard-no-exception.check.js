'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '2.1.3';
const RULE_ID = 'custom-keyboard-no-exception';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/keyboard-no-exception';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'All functionality must be operable via keyboard with no exception';

function _t(ctx, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, ctx, en);
}

function _pass(ctx, reason) {
  return {
    successCriteriaId: SC,
    rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'pass', reason, helpUrl: HELP_URL }],
  };
}

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  const data = await page.evaluate(() => {
    const issues = [];

    // ── Check 1: Natively interactive elements with tabindex="-1" ────────────
    // These are removed from the tab order and likely unreachable by keyboard.
    const NATIVE_INTERACTIVE = 'a[href],button,input:not([type="hidden"]),select,textarea,details>summary';
    for (const el of document.querySelectorAll(NATIVE_INTERACTIVE)) {
      if (el.getAttribute('tabindex') === '-1' && !el.disabled) {
        // Skip if part of a custom widget pattern (parent has a role with composite keyboard nav)
        const parent = el.closest('[role="listbox"],[role="grid"],[role="tree"],[role="tablist"],[role="menu"],[role="menubar"],[role="radiogroup"]');
        if (parent) continue;
        issues.push({
          type: 'tabindex-minus-one',
          target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
          snippet: el.outerHTML.slice(0, 150),
          detail: 'Natively interactive element has tabindex="-1" making it unreachable by keyboard',
        });
      }
    }

    // ── Check 2: Mouse-only handlers on non-interactive elements ────────────
    // Elements with only onclick (and no role/tabindex) are not keyboard-operable.
    const MOUSE_ONLY_SELECTOR = '[onclick]:not(a):not(button):not(input):not(select):not(textarea):not(summary)';
    for (const el of document.querySelectorAll(MOUSE_ONLY_SELECTOR)) {
      const role = el.getAttribute('role') || '';
      const tabindex = el.getAttribute('tabindex');
      const hasKeyboardRole = /^(button|link|menuitem|option|tab|checkbox|radio|switch|treeitem)$/.test(role);
      const isFocusable = tabindex !== null && tabindex !== '-1';

      if (!hasKeyboardRole && !isFocusable) {
        issues.push({
          type: 'mouse-only-handler',
          target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
          snippet: el.outerHTML.slice(0, 150),
          detail: 'Element has onclick but is not keyboard-operable (no role or tabindex)',
        });
      }
    }

    // ── Check 3: pointer-events: none on interactive elements ────────────────
    for (const el of document.querySelectorAll('a[href],button,[role="button"],[role="link"]')) {
      const cs = window.getComputedStyle(el);
      if (cs.pointerEvents === 'none') {
        issues.push({
          type: 'pointer-events-none',
          target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
          snippet: el.outerHTML.slice(0, 150),
          detail: 'Interactive element has pointer-events: none — may also be keyboard-blocked',
        });
      }
    }

    return { issues };
  });

  if (!data.issues.length) {
    return _pass(ctx, _t(ctx,
      'No keyboard-exception patterns detected (no tabindex=-1 on interactive elements, no mouse-only handlers).',
      'キーボード例外パターンは検出されませんでした（インタラクティブ要素の tabindex=-1 なし、マウス専用ハンドラーなし）。'));
  }

  const byType = {};
  for (const iss of data.issues) byType[iss.type] = (byType[iss.type] || 0) + 1;
  const summary = Object.entries(byType).map(([k, v]) => `${k}(${v})`).join(', ');

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'critical',
      status: 'incomplete',
      reason: _t(ctx,
        '{n} potential keyboard-only barrier(s) detected ({summary}). Manual verification required.',
        '{n} 件のキーボード専用の障壁が検出されました（{summary}）。手動確認が必要です。',
        { n: data.issues.length, summary }),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
