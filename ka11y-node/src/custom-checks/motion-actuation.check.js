'use strict';

const { auditMotionActuation } = require('../../audits/wcag-2.5.4/index.js');
const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '2.5.4';
const RULE_ID = 'custom-motion-actuation';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/motion-actuation';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Motion-based functionality must have a UI alternative and be disableable';

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);
  const result = await auditMotionActuation(page, { pageUrl: page.url() });

  if (!result.motionDetected) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: FALLBACK_DESCRIPTION,
        impact: null,
        status: 'pass',
        reason: _t(sharedContext, 'No motion-actuated functionality detected.', '動きによる操作は検出されませんでした。'),
        helpUrl: HELP_URL,
      }]
    };
  }

  const elements = [...result.violations, ...result.warnings, ...result.manualReviewItems].map(v => ({
      html: v.outerHTML || null,
      target: v.selector ? [v.selector] : [],
      tag: v.tag || null,
      reason: v.message,
      severity: v.severity === 'violation' ? 'serious' : 'moderate'
  }));

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'moderate',
      status: 'incomplete', // Motion usually needs manual review
      reason: _t(sharedContext, 'Potential motion-actuated functionality detected. Manual verification required for UI alternatives and disable mechanisms.', '動きによる操作が検出されました。UI による代替手段と無効化メカニズムの手動確認が必要です。'),
      elements,
      helpUrl: HELP_URL,
    }]
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
