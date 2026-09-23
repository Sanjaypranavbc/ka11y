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

    // G171: script-initiated play() without user activation, recorded by the runtime hook.
    const R = window.__ka11yRuntime;
    const scriptPlays = (R && Array.isArray(R.mediaPlay)) ? R.mediaPlay.filter(p => !p.userActivated && !p.muted) : [];
    const playedSrcs = new Set(scriptPlays.map(p => p.src));

    const CONTROL_RE = /pause|stop|mute|volume|sound\s*(?:on|off)?|audio\s*(?:on|off)|一時停止|停止|音量|消音|ミュート/i;
    const labelOf = (btn) => [
      btn.textContent || '',
      btn.getAttribute('aria-label') || '',
      btn.getAttribute('title') || '',
      ...Array.from(btn.querySelectorAll('svg title, img[alt]')).map(x => x.getAttribute('alt') || x.textContent || ''),
    ].join(' ');
    const CONTROL_SEL = 'button, [role="button"], a[role="button"], input[type="button"], [aria-pressed]';

    for (const media of mediaEls) {
      const mediaSrc = media.currentSrc || media.getAttribute('src') || '';
      const autoplay = media.hasAttribute('autoplay')
        || media.getAttribute('data-autoplay') === 'true'
        || media.autoplay === true
        || playedSrcs.has(mediaSrc)
        || (mediaEls.length === 1 && scriptPlays.length > 0);
      if (!autoplay) continue;

      const muted = media.muted === true || media.hasAttribute('muted');
      // Muted autoplay is exempt (no audible audio → 1.4.2 does not apply).
      if (muted) continue;

      const hasControls = media.hasAttribute('controls') || media.controls === true;

      // Duration: MediaElement.duration may be NaN until metadata loads.
      // Use attribute hints: data-duration, or assume > 3 s if not explicitly short.
      // Prefer the real media duration when metadata has loaded (G60: ≤ 3 s is exempt).
      const durAttr = (Number.isFinite(media.duration) && media.duration > 0)
        ? media.duration
        : parseFloat(media.getAttribute('data-duration') || '0');
      const durationKnown = Number.isFinite(durAttr) && durAttr > 0;
      const shortDuration = durationKnown && durAttr <= 3;
      if (shortDuration) continue;

      // Check for a nearby pause / volume / mute control outside the element.
      const container = media.closest('figure, article, section, [role="region"]')
        || media.parentElement;
      let hasExternalControl = false;
      if (container) {
        hasExternalControl = Array.from(container.querySelectorAll(CONTROL_SEL)).some(btn => CONTROL_RE.test(labelOf(btn)));
      }
      // G170: a control near the beginning of the page (site-wide sound toggle) counts,
      // but we cannot prove it controls THIS element → report for review instead of fail.
      const hasPageLevelControl = !hasControls && !hasExternalControl
        && Array.from(document.querySelectorAll(CONTROL_SEL)).some(btn => CONTROL_RE.test(labelOf(btn)));

      if (!hasControls && !hasExternalControl) {
        issues.push({
          html: media.outerHTML.slice(0, 200),
          element_id: media.id || null,
          target: media.id
            ? [`${media.tagName.toLowerCase()}#${CSS.escape(media.id)}`]
            : [media.tagName.toLowerCase()],
          tag: media.tagName,
          scriptAutoplay: !media.hasAttribute('autoplay') && media.autoplay !== true,
          pageLevelControl: hasPageLevelControl,
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
        status: 'not_applicable',
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

  const allHavePageControl = data.issues.every(i => i.pageLevelControl);
  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: allHavePageControl ? 'moderate' : 'serious',
      status: allHavePageControl ? 'incomplete' : 'fail',
      reason: allHavePageControl
        ? _t(
          sharedContext,
          '{issueCount} auto-playing unmuted media element(s) have no control of their own, but a page-level sound/pause control exists (G170). Verify it stops this audio.',
          '{issueCount} 件の自動再生・ミュート解除メディアに固有のコントロールはありませんが、ページ全体の音声／一時停止コントロールがあります（G170）。この音声を停止できるか確認してください。',
          { issueCount: data.issues.length },
        )
        : _t(
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
