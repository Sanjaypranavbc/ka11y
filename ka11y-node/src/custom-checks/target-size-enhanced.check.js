'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '2.5.5';
const RULE_ID = 'custom-target-size-enhanced';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/target-size-enhanced';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Interactive targets must be at least 44×44 CSS pixels';

const MIN_PX = 44;

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

  const data = await page.evaluate((minPx) => {
    const TARGETS = 'button,a[href],input:not([type="hidden"]),select,textarea,[role="button"],[role="link"],[role="menuitem"],[role="option"],[role="tab"],[role="checkbox"],[role="radio"],[role="switch"]';
    const issues = [];
    let checkedCount = 0;

    for (const el of document.querySelectorAll(TARGETS)) {
      // Skip hidden elements
      if (el.offsetParent === null && el.tagName !== 'BODY') continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) continue;
      checkedCount++;

      if (r.width < minPx || r.height < minPx) {
        issues.push({
          target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
          snippet: el.outerHTML.slice(0, 150),
          detail: `${Math.round(r.width)}×${Math.round(r.height)}px (minimum: ${minPx}×${minPx}px)`,
          width: Math.round(r.width),
          height: Math.round(r.height),
        });
      }
      if (issues.length >= 30) break; // cap for performance
    }

    return { checkedCount, issues };
  }, MIN_PX);

  if (!data.checkedCount) {
    return _pass(ctx, _t(ctx, 'No interactive targets found to measure.', '測定できるインタラクティブターゲットが見つかりませんでした。'));
  }
  if (!data.issues.length) {
    return _pass(ctx, _t(ctx,
      'All {n} interactive target(s) checked meet the {min}×{min}px minimum size.',
      '確認した {n} 件のインタラクティブターゲットすべてが {min}×{min}px の最小サイズを満たしています。',
      { n: data.checkedCount, min: MIN_PX }));
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'serious',
      status: 'fail',
      reason: _t(ctx,
        '{i} of {n} interactive target(s) are smaller than {min}×{min}px.',
        '{n} 件中 {i} 件のインタラクティブターゲットが {min}×{min}px 未満です。',
        { i: data.issues.length, n: data.checkedCount, min: MIN_PX }),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
