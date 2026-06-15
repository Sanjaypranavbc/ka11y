'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '2.4.3';
const RULE_ID = 'custom-focus-order';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/focus-order';
const MODE = 'interactive';
const FALLBACK_DESCRIPTION = 'Navigation order must preserve meaning — focusable elements must follow a logical sequence';

const MAX_TABS = 15;
const SETTLE_MS = 40;

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

  // ── Check 1: positive tabindex values (primary WCAG failure indicator) ──
  const positiveTabindex = await page.evaluate(() => {
    const issues = [];
    for (const el of document.querySelectorAll('[tabindex]')) {
      const val = parseInt(el.getAttribute('tabindex'), 10);
      if (val > 0) {
        issues.push({
          target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
          snippet: el.outerHTML.slice(0, 120),
          tabindex: val,
          detail: `tabindex="${val}" overrides natural DOM focus order — use tabindex="0" instead`,
        });
        if (issues.length >= 20) break;
      }
    }
    return issues;
  });

  // ── Check 2: tab sequence vs DOM order divergence ──────────────────────
  // Collect (domIndex, tabSequenceIndex) pairs then compare
  const domOrder = await page.evaluate(() => {
    const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]):not([type="hidden"]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
    const all = Array.from(document.querySelectorAll('*'));
    return Array.from(document.querySelectorAll(FOCUSABLE)).map(el => ({
      domIndex: all.indexOf(el),
      id: el.id || null,
      tag: el.tagName.toLowerCase(),
      snippet: el.outerHTML.slice(0, 80),
    }));
  });

  const tabSequence = [];
  for (let i = 0; i < Math.min(MAX_TABS, domOrder.length); i++) {
    await page.keyboard.press('Tab');
    await new Promise(r => setTimeout(r, SETTLE_MS));
    const info = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body || el === document.documentElement) return null;
      const all = Array.from(document.querySelectorAll('*'));
      return { domIndex: all.indexOf(el), id: el.id || null, tag: el.tagName.toLowerCase(), snippet: el.outerHTML.slice(0, 80) };
    });
    if (!info) break;
    tabSequence.push(info);
  }

  // Detect order inversions: if tab sequence dom indices are not monotonically
  // increasing we have a focus order problem
  const orderViolations = [];
  for (let i = 1; i < tabSequence.length; i++) {
    const prev = tabSequence[i - 1];
    const curr = tabSequence[i];
    // Allow small backwards jumps (skip links, landmarks) but flag big inversions
    if (curr.domIndex < prev.domIndex - 5) {
      orderViolations.push({
        target: curr.tag + (curr.id ? `#${curr.id}` : ''),
        snippet: curr.snippet,
        detail: `Tab step ${i + 1} jumps from DOM position ${prev.domIndex} back to ${curr.domIndex} — focus order may not match visual reading order`,
      });
      if (orderViolations.length >= 5) break;
    }
  }

  // Combine findings
  const allViolations = [
    ...positiveTabindex.map(v => ({ ...v, type: 'positive-tabindex' })),
    ...orderViolations.map(v => ({ ...v, type: 'order-inversion' })),
  ];

  if (!allViolations.length) {
    return _pass(ctx, _t(ctx,
      'No positive tabindex values or focus order inversions detected across {n} focusable elements.',
      'フォーカス可能要素 {n} 件でポジティブ tabindex やフォーカス順の逆転は検出されませんでした。',
      { n: tabSequence.length }));
  }

  const hasPositive = positiveTabindex.length > 0;
  const status = hasPositive ? 'fail' : 'incomplete';

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: hasPositive ? 'serious' : 'moderate',
      status,
      reason: _t(ctx,
        '{pos} element(s) use positive tabindex (disrupts natural order); {inv} focus order inversion(s) detected.',
        '{pos} 件の要素がポジティブ tabindex を使用しています（自然な順序を乱す）; {inv} 件のフォーカス順の逆転が検出されました。',
        { pos: positiveTabindex.length, inv: orderViolations.length }),
      elements: allViolations,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
