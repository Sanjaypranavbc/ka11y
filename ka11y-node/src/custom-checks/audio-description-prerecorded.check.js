'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '1.2.5';
const RULE_ID = 'custom-audio-description-prerecorded';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/audio-description-prerecorded';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Prerecorded video must have an audio description track';

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
    const videos = Array.from(document.querySelectorAll('video'));
    if (!videos.length) return { videoCount: 0, issues: [] };

    const issues = [];
    for (const v of videos) {
      if (v.muted) continue;
      const hasDescTrack = Array.from(v.querySelectorAll('track'))
        .some(t => (t.getAttribute('kind') || '').toLowerCase() === 'descriptions' && t.getAttribute('src'));
      if (!hasDescTrack) {
        issues.push({
          target: v.id ? `video#${CSS.escape(v.id)}` : 'video',
          snippet: v.outerHTML.slice(0, 200),
        });
      }
    }
    return { videoCount: videos.length, issues };
  });

  if (!data.videoCount) {
    return _na(ctx, _t(ctx, 'No <video> elements found on this page.', 'このページに <video> 要素はありません。'));
  }
  if (!data.issues.length) {
    return _pass(ctx, _t(ctx,
      'All {n} <video> element(s) have a <track kind="descriptions"> audio description track.',
      '{n} 件の <video> すべてに <track kind="descriptions"> 音声解説トラックがあります。',
      { n: data.videoCount }));
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'serious',
      status: 'incomplete',
      reason: _t(ctx,
        '{i} of {n} <video> element(s) are missing a <track kind="descriptions"> audio description track.',
        '{n} 件中 {i} 件の <video> に <track kind="descriptions"> 音声解説トラックがありません。',
        { i: data.issues.length, n: data.videoCount }),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
