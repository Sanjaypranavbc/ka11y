'use strict';

const {
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '1.2.4';
const RULE_ID = 'custom-captions-live';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/captions-live';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Live audio or live video content must have real-time captions';

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);

  const data = await page.evaluate(async () => {
    // Container-scoped caption mechanism check.
    // Replaces the previous global selector sweep so that a generic ".caption"
    // class somewhere on the page no longer counts as a captions mechanism for
    // an unrelated <video>.
    function findCaptionMechanismInContainer(rootElement) {
      if (!rootElement) return false;

      // 1. ARIA-live caption/transcript region within the container — strongest CART signal
      const liveRegions = Array.from(rootElement.querySelectorAll('[aria-live]'));
      for (const el of liveRegions) {
        const label = (el.getAttribute('aria-label') || '').toLowerCase();
        const txt   = (el.textContent || '').toLowerCase();
        if (/caption|transcript|live text|字幕|文字起こし|リアルタイム/i.test(label + ' ' + txt)) {
          return true;
        }
      }

      // 2. Player-rendered caption elements scoped to the container
      const captionSelectors = [
        '[class*="caption"]',
        '[class*="captions"]',
        '[class*="cc"]',
        '[class*="subtitle"]',
        '[id*="caption"]',
        '[id*="captions"]',
      ];
      for (const sel of captionSelectors) {
        const els = Array.from(rootElement.querySelectorAll(sel));
        for (const el of els) {
          const txt = (el.textContent || '').trim();
          if (txt.length > 0) return true;
        }
      }
      return false;
    }

    // Known embed patterns that may host live streams (cross-origin)
    const LIVE_EMBED_PATTERNS = [
      'twitch.tv', 'youtube.com/embed', 'facebook.com/plugins', 'periscope.tv',
      'vimeo.com', 'instagram.com', 'mixcloud.com', 'streamable.com', 'ustream',
    ];

    const videos = Array.from(document.querySelectorAll('video'));
    const issues = [];
    let liveCount = 0;
    let unverifiedLiveCount = 0;

    const hasWebSocketPreconnect = !!document.querySelector('link[rel="preconnect"][href^="wss://"]');

    for (const video of videos) {
      // Explicit opt-in
      const liveOptIn = video.getAttribute('data-wcag-live-captions') === 'true';

      // Technical liveness signals from video source
      const srcText = (video.currentSrc || '') + ' ' + (video.getAttribute('src') || '');
      const isLiveUrl = /\.m3u8|\.mpd|\/live\//i.test(srcText);

      // MSE-driven sources surface as blob:/MediaSource — treat as live if also has the data-live attr
      const isMseDriven = (video.currentSrc || '').startsWith('blob:') &&
        (video.getAttribute('data-live') === 'true' || video.getAttribute('is-live') === 'true');

      // Container scoping for nearby textual hints + caption mechanism search
      const container = video.closest('figure, article, section, [role="region"], [role="main"]') || video.parentElement;
      const nearbyText = container ? (container.textContent || '').slice(0, 400) : '';

      // STRENGTHENED: Strong live evidence is now the only path to a pass.
      // Loose textual mentions of "live" on the page no longer constitute evidence.
      const hasLivenessEvidence =
        liveOptIn || isLiveUrl || isMseDriven || hasWebSocketPreconnect;

      // Broader heuristic for entering the per-video branch (so we still examine
      // ambiguous cases and report unverifiedLiveCount → needs_review).
      const looksLive = hasLivenessEvidence ||
                        /\blive\b|m3u8|playlist|stream/i.test(srcText) ||
                        /\bLIVE\b|on air|now playing/i.test(nearbyText) ||
                        video.getAttribute('data-live') === 'true' ||
                        video.getAttribute('is-live') === 'true';

      if (!looksLive) continue;

      liveCount += 1;
      if (!hasLivenessEvidence) unverifiedLiveCount += 1;

      // 1. <track kind="captions"|"subtitles"> children with src + srclang
      const captionTracks = Array.from(video.querySelectorAll('track[kind="captions"], track[kind="subtitles"]'));
      const hasCaptionTrack = captionTracks.some(t => {
        const src = t.getAttribute('src');
        const srclang = (t.getAttribute('srclang') || '').trim();
        return !!src && !!srclang;
      });

      // 2. textTracks populated by JS players
      let hasTextTracks = false;
      try {
        if (video.textTracks && video.textTracks.length > 0) {
          for (let i = 0; i < video.textTracks.length; i++) {
            const tt = video.textTracks[i];
            if (tt && (tt.kind === 'captions' || tt.kind === 'subtitles')) {
              hasTextTracks = true;
              break;
            }
          }
        }
      } catch (e) {
        // ignore cross-origin / access errors
      }

      // 3. Visible captioning elements scoped to the video's container
      const hasVisibleCaptions = findCaptionMechanismInContainer(container);

      if (!hasCaptionTrack && !hasTextTracks && !hasVisibleCaptions) {
        issues.push({
          html: video.outerHTML.slice(0, 200),
          element_id: video.id || null,
          target: video.id ? [`video#${CSS.escape(video.id)}`] : ['video'],
          tag: 'VIDEO',
        });
      }
    }

    // Bug fix: `iframes` was undefined in the original loop below.
    const iframes = Array.from(document.querySelectorAll('iframe'));

    // Inspect iframes for known live embed patterns
    for (const ifr of iframes) {
      const src = (ifr.getAttribute('src') || '').toLowerCase();
      if (!src) continue;

      const isLiveEmbedDomain = LIVE_EMBED_PATTERNS.some(p => src.includes(p));
      if (!isLiveEmbedDomain) continue;

      // STRENGTHENED: require a live-specific signal in the iframe URL,
      // not merely a matching domain. (twitch.tv channels are inherently live.)
      const isYouTubeLive = src.includes('youtube.com/embed') && /[?&]live=1/.test(src);
      const isVimeoLive   = src.includes('vimeo.com')        && (src.includes('/live/') || /[?&]is_live=1/.test(src));
      const isUrlLive     = /\.m3u8|\.mpd|\/live\//i.test(src);
      const isTwitch      = src.includes('twitch.tv'); // twitch embeds are live by default

      const hasIframeLivenessEvidence = isYouTubeLive || isVimeoLive || isUrlLive || isTwitch;
      if (!hasIframeLivenessEvidence) continue;

      // Embed URL forces captions on
      const hasForcedCaptions =
        (src.includes('youtube.com/embed') && /[?&]cc_load_policy=1/.test(src)) ||
        (src.includes('vimeo.com') && /[?&]texttrack=/.test(src));

      if (hasForcedCaptions) {
        liveCount += 1;
        continue;
      }

      // Nearby ARIA-live CART transcript pane labelled with caption/transcript/字幕
      const container = ifr.closest('figure, article, section, [role="region"], [role="main"]') || ifr.parentElement;
      const hasCartStream = container && Array.from(container.querySelectorAll('[aria-live]')).some(el => {
        const txt = (el.textContent || '').toLowerCase();
        const label = (el.getAttribute('aria-label') || '').toLowerCase();
        return /caption|transcript|live text|字幕|文字起こし|リアルタイム/i.test(label + ' ' + txt);
      });

      if (hasCartStream) {
        liveCount += 1;
        continue;
      }

      let crossOrigin = false;
      try {
        const _ = ifr.contentDocument && ifr.contentDocument.readyState;
      } catch (e) {
        crossOrigin = true;
      }
      issues.push({
        html: ifr.outerHTML.slice(0, 200),
        element_id: ifr.id || null,
        target: ifr.id ? [`iframe#${CSS.escape(ifr.id)}`] : ['iframe'],
        tag: 'IFRAME',
        reason: crossOrigin ? 'embedded-live-player' : 'embedded-live-player-same-origin',
      });
    }

    return { liveCount, unverifiedLiveCount, issues };
  });

  if (data.liveCount === 0 && data.issues.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: FALLBACK_DESCRIPTION,
        impact: null,
        status: 'not_applicable',
        reason: _t(sharedContext, 'No live audio/video streams detected on this page.', 'このページではライブの音声/動画ストリームは検出されませんでした。'),
        helpUrl: HELP_URL,
      }],
    };
  }

  if (data.issues.length === 0) {
    if (data.unverifiedLiveCount > 0) {
      return {
        successCriteriaId: SC,
        rules: [{
          ruleId: RULE_ID,
          description: FALLBACK_DESCRIPTION,
          impact: 'moderate',
          status: 'needs_review',
          reason: _t(sharedContext, 'cannot verify captions are live; appears prerecorded', 'キャプションがライブであることを確認できません。事前録画のように見えます。'),
          helpUrl: HELP_URL,
        }],
      };
    }
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: FALLBACK_DESCRIPTION,
        impact: null,
        status: 'pass',
        reason: _t(sharedContext, '{count} live media stream(s) checked — captions or subtitles detected.', '{count} 件のライブメディアを確認しました — キャプションまたは字幕が検出されました。', { count: data.liveCount }),
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
      status: 'incomplete',
      reason: _t(sharedContext, '{missing} live media stream(s) require real-time captions or manual verification for embedded players.', '{missing} 件のライブメディアがリアルタイムキャプションを必要とする、または埋め込みプレイヤーは手動確認が必要です。', { missing: data.issues.length }),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
