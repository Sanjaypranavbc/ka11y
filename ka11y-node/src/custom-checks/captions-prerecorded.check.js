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

  const data = await page.evaluate(async () => {
    const videos = Array.from(document.querySelectorAll('video'));
    if (videos.length === 0) {
      return { videoCount: 0, issues: [], liveHints: 0 };
    }

    const issues = [];
    let liveHints = 0;
    let videoOnly = 0;

    // G159: probe whether the video actually has an audio track (silent, click-to-play
    // videos are video-only and belong under 1.2.1, not captions). Muted playback for a
    // moment is allowed by autoplay policy; everything is restored afterwards.
    const probeHasAudio = async (v) => {
      try {
        if (typeof v.mozHasAudio === 'boolean') return v.mozHasAudio;
        if (v.audioTracks && typeof v.audioTracks.length === 'number' && v.readyState >= 1) return v.audioTracks.length > 0;
        if (typeof v.webkitAudioDecodedByteCount !== 'number') return null;
        if (!v.paused) return v.webkitAudioDecodedByteCount > 0 ? true : null;
        const wasMuted = v.muted, t0 = v.currentTime;
        v.muted = true;
        const p = v.play();
        if (p && p.catch) await p.catch(() => {});
        await new Promise(r => setTimeout(r, 700));
        const bytes = v.webkitAudioDecodedByteCount;
        v.pause();
        try { v.currentTime = t0; } catch (_) { /* ignore */ }
        v.muted = wasMuted;
        if (v.readyState < 2) return null; // never decoded — unknown
        return bytes > 0;
      } catch (_) { return null; }
    };
    const silent = new Set();
    for (const v of videos.slice(0, 6)) { if ((await probeHasAudio(v)) === false) { silent.add(v); videoOnly += 1; } }

    for (const video of videos) {
      if (silent.has(video)) continue;
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

      // 1b. textTracks populated by a JS player, or a CC/captions button in a custom
      //     player wrapper (G87 — JW Player, Video.js, Plyr, custom controls).
      let hasPlayerCaptions = false;
      try {
        for (let i = 0; i < (video.textTracks ? video.textTracks.length : 0); i++) {
          const tt = video.textTracks[i];
          if (tt && (tt.kind === 'captions' || tt.kind === 'subtitles')) { hasPlayerCaptions = true; break; }
        }
      } catch (_) { /* ignore */ }
      if (!hasPlayerCaptions) {
        const wrapper = video.closest('[class*="player" i], [class*="video" i], figure, [data-plyr], .jwplayer, .video-js') || video.parentElement;
        if (wrapper && wrapper.querySelector('button[aria-label*="caption" i], button[aria-label*="subtitle" i], [role="button"][aria-label*="caption" i], button[title*="caption" i], [class*="vjs-subs-caps"], [class*="captions-button" i], [class*="cc-button" i], [aria-label*="字幕"], [title*="字幕"], button[aria-label="CC"], .jw-icon-cc, [data-plyr="captions"]')) hasPlayerCaptions = true;
      }

      // 2. Embedded player hint: YouTube/Vimeo iframes use their own CC menu;
      // we cannot inspect cross-origin iframes, so flag as incomplete.
      const parentIframe = video.closest('iframe');

      if (!hasCaptionTrack && !hasPlayerCaptions && !parentIframe) {
        issues.push({
          html: video.outerHTML.slice(0, 200),
          element_id: video.id || null,
          target: video.id ? [`video#${CSS.escape(video.id)}`] : ['video'],
          tag: 'VIDEO',
        });
      }
    }

    // Third-party media embeds: video players, audio players, combined platforms.
    // CC menus are author-controlled in cross-origin iframes; flag for manual review.
    const EMBED_PATTERNS = [
      // video
      'youtube.com/embed', 'player.vimeo.com', 'wistia',
      'dailymotion.com/embed', 'rumble.com/embed', 'jwplayer',
      'brightcove', 'kaltura', 'bitchute.com/embed', 'loom.com/embed', 'videojs',
      // audio (no caption track possible — flag for transcript review)
      'open.spotify.com/embed', 'w.soundcloud.com/player',
      'bandcamp.com/track', 'bandcamp.com/album',
      'music.apple.com', 'podcasts.apple.com', 'anchor.fm/s',
      'castbox.fm', 'player.simplecast.com', 'buzzsprout.com',
      'podbean.com/media/player', 'audiomack.com/embed',
      // combined
      'facebook.com/plugins', 'twitter.com/i/videos', 'tiktok.com/embed', 'instagram.com/p',
    ];
    const iframeSel = EMBED_PATTERNS.map(p => `iframe[src*="${p}" i]`).join(', ');
    const iframes = Array.from(document.querySelectorAll(iframeSel));
    for (const ifr of iframes) {
      const src = (ifr.getAttribute('src') || '').toLowerCase();
      const isAudioOnly = [
        'spotify', 'soundcloud', 'bandcamp', 'apple.com', 'anchor.fm',
        'castbox', 'simplecast', 'buzzsprout', 'podbean', 'audiomack',
      ].some(p => src.includes(p));
      issues.push({
        html: ifr.outerHTML.slice(0, 200),
        element_id: ifr.id || null,
        target: ifr.id ? [`iframe#${CSS.escape(ifr.id)}`] : ['iframe'],
        tag: 'IFRAME',
        reason: isAudioOnly ? 'embedded-audio-player' : 'embedded-player',
      });
    }

    return { videoCount: videos.length, issues, liveHints, iframeCount: iframes.length, videoOnly };
  });

  if (data.videoCount === 0 && data.iframeCount === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: FALLBACK_DESCRIPTION,
        impact: null,
        status: 'not_applicable',
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
          '{count} <video> element(s) checked — all have caption tracks or a player captions control{vo}.',
          '{count} 件の <video> 要素を確認しました — すべてにキャプショントラックまたはプレイヤーの字幕機能があります{vo}。',
          { count: data.videoCount, vo: data.videoOnly ? _t(sharedContext, ` (${data.videoOnly} silent video-only element(s) skipped — judged under 1.2.1)`, `（無音の動画のみ ${data.videoOnly} 件は 1.2.1 で判定するためスキップ）`) : '' },
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
