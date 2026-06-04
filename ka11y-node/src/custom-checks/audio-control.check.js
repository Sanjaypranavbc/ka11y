'use strict';

const {
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '1.4.2';
const RULE_ID = 'custom-audio-control';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/audio-control';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Audio that plays automatically for more than 3 seconds must have a pause/stop/volume control';

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);

  const data = await page.evaluate(() => {
    // Inspect both <audio> and <video> (video with audio track triggers SC 1.4.2).
    const mediaEls = Array.from(document.querySelectorAll('audio, video'));
    if (mediaEls.length === 0) return { mediaCount: 0, issues: [] };

    const issues = [];

    for (const media of mediaEls) {
      const autoplay = media.hasAttribute('autoplay')
        || media.getAttribute('data-autoplay') === 'true'
        || media.autoplay === true;
      if (!autoplay) continue;

      const muted = media.muted === true || media.hasAttribute('muted');
      // Muted autoplay is exempt (no audible audio → 1.4.2 does not apply).
      if (muted) continue;

      const hasControls = media.hasAttribute('controls') || media.controls === true;

      // Duration: MediaElement.duration may be NaN until metadata loads.
      // Use attribute hints: data-duration, or assume > 3 s if not explicitly short.
      const durAttr = parseFloat(media.getAttribute('data-duration') || media.duration || '0');
      const durationKnown = Number.isFinite(durAttr) && durAttr > 0;
      const shortDuration = durationKnown && durAttr <= 3;
      if (shortDuration) continue;

      // Check for a nearby pause / volume / mute control outside the element.
      const container = media.closest('figure, article, section, [role="region"]')
        || media.parentElement;
      let hasExternalControl = false;
      if (container) {
        const controlText = /pause|stop|mute|volume|一時停止|停止|音量|消音/i;
        hasExternalControl = Array.from(
          container.querySelectorAll('button, [role="button"], a[role="button"]')
        ).some(btn => {
          const lbl = (btn.textContent || '')
            + ' ' + (btn.getAttribute('aria-label') || '')
            + ' ' + (btn.getAttribute('title') || '');
          return controlText.test(lbl);
        });
      }

      if (!hasControls && !hasExternalControl) {
        issues.push({
          html: media.outerHTML.slice(0, 200),
          element_id: media.id || null,
          target: media.id
            ? [`${media.tagName.toLowerCase()}#${CSS.escape(media.id)}`]
            : [media.tagName.toLowerCase()],
          tag: media.tagName,
        });
      }
    }

    return { mediaCount: mediaEls.length, issues };
  });

  if (data.mediaCount === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: FALLBACK_DESCRIPTION,
        impact: null,
        status: 'pass',
        reason: _t(sharedContext, 'No <audio> or <video> elements found on this page.', 'このページには <audio> または <video> 要素はありません。'),
        helpUrl: HELP_URL,
      }],
    };
  }

  if (data.issues.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: FALLBACK_DESCRIPTION,
        impact: null,
        status: 'pass',
        reason: _t(
          sharedContext,
          'No auto-playing unmuted media longer than 3 seconds was detected without controls.',
          '3 秒を超える自動再生のミュート解除メディアでコントロールのないものは検出されませんでした。',
        ),
        helpUrl: HELP_URL,
      }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'serious',
      status: 'fail',
      reason: _t(
        sharedContext,
        '{issueCount} auto-playing unmuted media element(s) have no pause/stop/volume control.',
        '{issueCount} 件の自動再生・ミュート解除メディアに一時停止／停止／音量コントロールがありません。',
        { issueCount: data.issues.length },
      ),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
