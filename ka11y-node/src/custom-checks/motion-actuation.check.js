'use strict';

const { auditMotionActuation } = require('../audits/wcag-2.5.4/index.js');
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

  // G213: when motion handlers exist, look for the required conventional-control
  // alternative (buttons) and a user setting to disable motion actuation.
  let g213 = { toggle: false, buttons: 0 };
  try {
    const probed = await page.evaluate(() => {
      const TOGGLE_RE = /motion|shake|tilt|gesture|device\s*orientation|accelerometer|動き|モーション|シェイク|傾け|ジェスチャー/i;
      const nameOf = (el) => [(el.textContent || ''), el.getAttribute('aria-label') || '', el.getAttribute('title') || '', (el.labels && el.labels[0] ? el.labels[0].textContent : '')].join(' ');
      const toggle = Array.from(document.querySelectorAll('input[type="checkbox"], [role="switch"], button, [role="button"], select, a[href]')).some(el => TOGGLE_RE.test(nameOf(el)) && /off|on|disable|enable|toggle|setting|無効|有効|設定|オフ|オン/i.test(nameOf(el) + ' ' + (el.getAttribute('role') || '') + ' ' + (el.type || '')));
      const buttons = document.querySelectorAll('button, [role="button"], input[type="button"], input[type="submit"]').length;
      return { toggle, buttons };
    });
    if (probed && typeof probed === 'object' && !Array.isArray(probed)) g213 = probed;
  } catch (_) { /* keep defaults */ }
  const missing = [];
  if (!g213.toggle) missing.push('no user setting to disable motion actuation');
  if (!g213.buttons) missing.push('no conventional control (button) alternative found');

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
      impact: missing.length === 2 ? 'serious' : 'moderate',
      status: missing.length === 2 ? 'fail' : 'incomplete',
      reason: missing.length
        ? _t(sharedContext, 'Motion-actuated functionality detected (devicemotion/orientation handlers) and {m} (G213). Provide button equivalents and a setting to turn motion actuation off.', '動きによる操作（devicemotion/orientation ハンドラー）が検出されましたが、{m}（G213）。ボタンによる代替と動き操作を無効にする設定を提供してください。', { m: missing.join('; ') })
        : _t(sharedContext, 'Motion-actuated functionality detected; a motion on/off setting and button controls exist (G213) — verify the buttons perform the same functions as the motion gestures.', '動きによる操作が検出されました。動きのオン/オフ設定とボタンによる操作があります（G213）。ボタンが動き操作と同じ機能を果たすか確認してください。'),
      elements,
      helpUrl: HELP_URL,
    }]
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
