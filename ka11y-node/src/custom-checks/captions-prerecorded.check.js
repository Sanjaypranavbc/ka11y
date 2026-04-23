'use strict';

const {
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '1.2.2';
const RULE_ID = 'custom-captions-prerecorded';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/captions-prerecorded';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Prerecorded video content must have captions';

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);

  const data = await page.evaluate(() => {
    const videos = Array.from(document.querySelectorAll('video'));
    if (videos.length === 0) {
      return { videoCount: 0, issues: [], liveHints: 0 };
    }

    const issues = [];
    let liveHints = 0;

    for (const video of videos) {
      // Heuristic: skip content that looks live (attribute or nearby keyword).
      const liveAttr = video.getAttribute('data-live') === 'true'
        || video.getAttribute('is-live') === 'true';
      const srcText = (video.currentSrc || '') + ' ' + (video.getAttribute('src') || '');
      const looksLive = /\blive\b|hls\.m3u8|stream/i.test(srcText);
      if (liveAttr || looksLive) {
        liveHints += 1;
        continue;
      }

      // Video element must have an audio track to require captions (video-only
      // content is audited under 1.2.1). We can't read "has audio" reliably
      // without playing, so treat <video> with no muted attribute + non-zero
      // duration as the candidate set. When unsure, still flag for review.
      const muted = video.muted === true;
      if (muted) continue;

      // 1. <track kind="captions" | "subtitles"> children
      const captionTracks = Array.from(
        video.querySelectorAll('track[kind="captions"], track[kind="subtitles"]')
      );
      const hasCaptionTrack = captionTracks.some(t => {
        const src = t.getAttribute('src');
        const label = (t.getAttribute('srclang') || '').trim();
        return !!src && !!label;
      });

      // 2. Embedded player hint: YouTube/Vimeo iframes use their own CC menu;
      // we cannot inspect cross-origin iframes, so flag as incomplete.
      const parentIframe = video.closest('iframe');

      if (!hasCaptionTrack && !parentIframe) {
        issues.push({
          html: video.outerHTML.slice(0, 200),
          element_id: video.id || null,
          target: video.id ? [`video#${CSS.escape(video.id)}`] : ['video'],
          tag: 'VIDEO',
        });
      }
    }

    // Also inspect YouTube/Vimeo iframes — CC menu is author-controlled and
    // not programmatically detectable. Emit incomplete.
    const iframes = Array.from(document.querySelectorAll(
      'iframe[src*="youtube.com/embed" i], iframe[src*="player.vimeo.com" i], iframe[src*="wistia" i]'
    ));
    for (const ifr of iframes) {
      issues.push({
        html: ifr.outerHTML.slice(0, 200),
        element_id: ifr.id || null,
        target: ifr.id ? [`iframe#${CSS.escape(ifr.id)}`] : ['iframe'],
        tag: 'IFRAME',
        reason: 'embedded-player',
      });
    }

    return { videoCount: videos.length, issues, liveHints, iframeCount: iframes.length };
  });

  if (data.videoCount === 0 && data.iframeCount === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: FALLBACK_DESCRIPTION,
        impact: null,
        status: 'pass',
        reason: _t(sharedContext, 'No <video> elements or known embedded video players found on this page.', 'このページには <video> 要素や既知の埋め込み動画プレイヤーはありません。'),
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
          '{count} <video> element(s) checked — all have caption tracks.',
          '{count} 件の <video> 要素を確認しました — すべてにキャプショントラックがあります。',
          { count: data.videoCount },
        ),
        helpUrl: HELP_URL,
      }],
    };
  }

  const embedded = data.issues.filter(i => i.reason === 'embedded-player').length;
  const missing = data.issues.length - embedded;
  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'serious',
      status: 'incomplete',
      reason: _t(
        sharedContext,
        '{missing} <video> element(s) have no <track kind="captions"> and {embedded} embedded player(s) require manual caption verification.',
        '{missing} 件の <video> にキャプショントラックがなく、{embedded} 件の埋め込み動画プレイヤーは手動でキャプションを確認する必要があります。',
        { missing, embedded },
      ),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
