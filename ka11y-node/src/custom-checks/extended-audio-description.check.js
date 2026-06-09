'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '1.2.7';
const RULE_ID = 'custom-extended-audio-description';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/extended-audio-description-prerecorded';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Prerecorded video must have extended audio description when foreground audio pauses are insufficient';

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

// Looks for labels/text indicating an extended description mechanism is present.
const EXT_DESC_RE = /extended\s*(?:audio\s*)?description|audiodescript(?:ion)?s?\s+extended|beschreibung\s+erweitert/i;

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  const data = await page.evaluate((extDescPattern) => {
    const re = new RegExp(extDescPattern, 'i');
    const videos = Array.from(document.querySelectorAll('video'));
    if (!videos.length) return { videoCount: 0, issues: [] };

    const issues = [];
    for (const v of videos) {
      if (v.muted) continue;

      // Check <track> labels for extended description indicator
      const tracks = Array.from(v.querySelectorAll('track'));
      const hasExtTrack = tracks.some(t =>
        (t.getAttribute('kind') || '').toLowerCase() === 'descriptions' &&
        re.test(t.getAttribute('label') || ''));

      // Check nearby container text for evidence of an extended description mechanism
      const container = v.closest('figure,article,section,main,[role="region"],[role="main"]') || v.parentElement;
      const hasNearbyText = container ? re.test(container.textContent || '') : false;

      if (!hasExtTrack && !hasNearbyText) {
        issues.push({
          target: v.id ? `video#${CSS.escape(v.id)}` : 'video',
          snippet: v.outerHTML.slice(0, 200),
        });
      }
    }
    return { videoCount: videos.length, issues };
  }, EXT_DESC_RE.source);

  if (!data.videoCount) {
    return _na(ctx, _t(ctx, 'No <video> elements found on this page.', 'このページに <video> 要素はありません。'));
  }
  if (!data.issues.length) {
    return _pass(ctx, _t(ctx,
      'Extended audio description indicators detected for all {n} <video> element(s). Manual verification recommended.',
      '{n} 件の <video> に拡張音声解説の指標が検出されました。手動確認を推奨します。',
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
        '{i} of {n} <video> element(s) show no evidence of an extended audio description mechanism. Manual review required.',
        '{n} 件中 {i} 件の <video> に拡張音声解説の仕組みが見当たりません。手動確認が必要です。',
        { i: data.issues.length, n: data.videoCount }),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
