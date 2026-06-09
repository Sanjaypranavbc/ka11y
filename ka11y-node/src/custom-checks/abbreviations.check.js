'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '3.1.4';
const RULE_ID = 'custom-abbreviations';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/abbreviations';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'A mechanism must be available for identifying the expanded form of abbreviations';

function _t(ctx, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, ctx, en);
}

function _pass(ctx, reason) {
  return {
    successCriteriaId: SC,
    rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'pass', reason, helpUrl: HELP_URL }],
  };
}
function _na(ctx, reason) {
  return {
    successCriteriaId: SC,
    rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'not_applicable', reason, helpUrl: HELP_URL }],
  };
}

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  const data = await page.evaluate(() => {
    const abbrs = Array.from(document.querySelectorAll('abbr'));
    if (!abbrs.length) return { abbrCount: 0, issues: [] };

    const issues = [];
    for (const abbr of abbrs) {
      const title = (abbr.getAttribute('title') || '').trim();
      if (!title) {
        issues.push({
          target: 'abbr',
          snippet: abbr.outerHTML.slice(0, 100),
          detail: `<abbr> "${abbr.textContent.trim()}" is missing a title attribute with its expanded form`,
        });
      }
    }
    return { abbrCount: abbrs.length, issues };
  });

  if (!data.abbrCount) {
    return _na(ctx, _t(ctx,
      'No <abbr> elements found — criterion not applicable.',
      'このページに <abbr> 要素はありません。略語の展開メカニズムは不要です。'));
  }

  if (!data.issues.length) {
    return _pass(ctx, _t(ctx,
      'All {n} <abbr> element(s) have a title attribute providing the expanded form.',
      '{n} 件の <abbr> 要素すべてに展開形を示す title 属性があります。',
      { n: data.abbrCount }));
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'minor',
      status: 'fail',
      reason: _t(ctx,
        '{i} of {n} <abbr> element(s) are missing a title attribute with the expanded form.',
        '{n} 件中 {i} 件の <abbr> 要素に展開形を示す title 属性がありません。',
        { i: data.issues.length, n: data.abbrCount }),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
