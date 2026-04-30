'use strict';

const { auditPointerGestures } = require('../audits/wcag-2.5.1/index.js');
const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '2.5.1';
const RULE_ID = 'custom-pointer-gestures';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/pointer-gestures';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Complex gestures must have a single-pointer alternative';

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);
  const result = await auditPointerGestures(page, { pageUrl: page.url() });

  const rules = [];

  if (result.summary.total === 0) {
    rules.push({
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: null,
      status: 'pass',
      reason: _t(sharedContext, 'No complex pointer gestures detected on this page.', 'このページでは複雑なポインタージェスチャーは検出されませんでした。'),
      helpUrl: HELP_URL,
    });
  } else {
    // Combine violations and warnings into a single SC report
    const elements = [...result.violations, ...result.warnings].map(v => ({
        html: v.outerHTML || null,
        target: v.selector ? [v.selector] : [],
        tag: v.tag || null,
        reason: v.message,
        severity: v.severity === 'violation' ? 'serious' : 'moderate'
    }));

    const status = result.violations.length > 0 ? 'fail' : 'incomplete';
    const impact = result.violations.length > 0 ? 'serious' : 'moderate';

    rules.push({
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact,
      status,
      reason: _t(sharedContext, '{count} complex gesture(s) detected. Ensure single-pointer alternatives are provided.', '{count} 件の複雑なジェスチャーが検出されました。単一ポインターによる代替手段が提供されていることを確認してください。', { count: result.summary.total }),
      elements,
      helpUrl: HELP_URL,
    });
  }

  return {
    successCriteriaId: SC,
    rules
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
