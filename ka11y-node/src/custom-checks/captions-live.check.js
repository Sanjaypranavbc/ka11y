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
    // Helper to check for caption-like visible elements (commonly used by players)
    function hasVisibleCaptionElement() {
      const captionSelectors = [
        '[class*="caption"]',
        '[class*="captions"]',
        '[class*="cc"]',
        '[class*="subtitle"]',
        '[id*="caption"]',
        '[id*="captions"]',
        '[role="region"][aria-live]'
      ];
      for (const sel of captionSelectors) {
        const els = Array.from(document.querySelectorAll(sel));
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

    for (const video of videos) {
      const liveAttr = video.getAttribute('data-live') === 'true' || video.getAttribute('is-live') === 'true';
      const srcText = (video.currentSrc || '') + ' ' + (video.getAttribute('src') || '');
      const looksLive = /\blive\b|m3u8|\.m3u8|\.m3u8\?|playlist|stream/i.test(srcText);

      // Nearby textual hint (e.g., badge saying "Live")
      const container = video.closest('figure, article, section, [role="region"], [role="main"]') || video.parentElement;
      const nearbyText = container ? (container.textContent || '').slice(0, 400) : '';
      const hasLiveBadge = /\bLIVE\b|\blive\b|on air|now playing/i.test(nearbyText);

      const likelyLive = liveAttr || looksLive || hasLiveBadge;
      if (!likelyLive) continue;
      liveCount += 1;

      // 1. Check for <track kind="captions" | "subtitles"> children
      const captionTracks = Array.from(video.querySelectorAll('track[kind="captions"], track[kind="subtitles"]'));
      const hasCaptionTrack = captionTracks.some(t => {
        const src = t.getAttribute('src');
        const srclang = (t.getAttribute('srclang') || '').trim();
        return !!src && !!srclang;
      });

      // 2. Check for textTracks (may be populated by JS players)
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
        // ignore access errors
      }

      // 3. Visible captioning elements on page (player-rendered captions)
      const hasVisibleCaptions = hasVisibleCaptionElement();

      if (!hasCaptionTrack && !hasTextTracks && !hasVisibleCaptions) {
        issues.push({
          html: video.outerHTML.slice(0, 200),
          element_id: video.id || null,
          target: video.id ? [`video#${CSS.escape(video.id)}`] : ['video'],
          tag: 'VIDEO',
        });
      }
    }

    // Inspect iframes for known live embed patterns; cross-origin iframes need manual review
    // unless they have URL parameters explicitly forcing captions on.
    const iframes = Array.from(document.querySelectorAll('iframe'));
    for (const ifr of iframes) {
      const src = (ifr.getAttribute('src') || '').toLowerCase();
      if (!src) continue;
      
      const isLiveEmbed = LIVE_EMBED_PATTERNS.some(p => src.includes(p));
      if (!isLiveEmbed) continue;

      // Improvement: Check if the embed URL explicitly forces captions on
      const hasForcedCaptions = 
        (src.includes('youtube.com/embed') && /[?&]cc_load_policy=1/.test(src)) ||
        (src.includes('vimeo.com') && /[?&]texttrack=/.test(src));

      if (hasForcedCaptions) {
        continue; // Passing signal — player is configured to show captions
      }

      // Improvement: Look for a nearby ARIA-live region that might be a CART stream
      const container = ifr.closest('figure, article, section, [role="region"], [role="main"]') || ifr.parentElement;
      const hasCartStream = container && Array.from(container.querySelectorAll('[aria-live]')).some(el => {
         const txt = (el.textContent || '').toLowerCase();
         const label = (el.getAttribute('aria-label') || '').toLowerCase();
         return /caption|transcript|live text|字幕|文字起こし/i.test(label + ' ' + txt);
      });

      if (hasCartStream) {
        continue; // Passing signal — an external CART stream is provided next to the video
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

    return { liveCount, issues };
  });

  if (data.liveCount === 0 && data.issues.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: FALLBACK_DESCRIPTION,
        impact: null,
        status: 'pass',
        reason: _t(sharedContext, 'No live audio/video streams detected on this page.', 'このページではライブの音声/動画ストリームは検出されませんでした。'),
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