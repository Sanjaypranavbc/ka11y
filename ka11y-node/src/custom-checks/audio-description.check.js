'use strict';

const {
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '1.2.3';
const RULE_ID = 'custom-audio-description';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/audio-description-or-media-alternative-prerecorded';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Prerecorded synchronized media must have an audio description or full-text media alternative';

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);

  const data = await page.evaluate(async () => {
    const ALT_KEYWORDS = /transcript|text\s+version|full[- ]?text\s+alternative|audio[- ]?description|descriptive\s+transcript|書き起こし|文字起こし|音声解説|音声ガイド|代替テキスト/i;

    const videos = Array.from(document.querySelectorAll('video'));
    if (videos.length === 0) return { videoCount: 0, issues: [] };

    const issues = [];
    let videoOnly = 0;

    // G159: a video with no audio track is video-only (1.2.1), not synchronized media —
    // probe with a brief muted play and restore the element afterwards.
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
        if (v.readyState < 2) return null;
        return bytes > 0;
      } catch (_) { return null; }
    };
    const silent = new Set();
    for (const v of videos.slice(0, 6)) { if ((await probeHasAudio(v)) === false) { silent.add(v); videoOnly += 1; } }

    for (const video of videos) {
      const muted = video.muted === true;
      if (muted || silent.has(video)) continue;

      // Signal 1: <track kind="descriptions">
      const descTracks = Array.from(video.querySelectorAll('track[kind="descriptions"]'));
      const hasDescTrack = descTracks.some(t => {
        const src = t.getAttribute('src');
        return !!src && (t.getAttribute('srclang') || '').length > 0;
      });

      // Signal 2: second <audio> or <source> labeled as description
      const altAudio = video.parentElement
        && Array.from(video.parentElement.querySelectorAll('audio, source')).some(el => {
          const lbl = ((el.getAttribute('data-kind') || '') + ' ' + (el.getAttribute('title') || '')).toLowerCase();
          return /description|audio[- ]?desc/i.test(lbl);
        });

      // Signal 3: nearby full-text alternative (transcript link or details)
      const container = video.closest('figure, article, section, main, [role="region"], [role="main"]')
        || video.parentElement;
      // G58: the link/control may sit immediately before or after the media container.
      const scope = [container, container && container.nextElementSibling, container && container.previousElementSibling].filter(Boolean);
      let hasTextAlternative = false;
      let hasDescribedVersionControl = false;
      for (const root of scope) {
        const labelOf = (el) => ((el.textContent || '') + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('title') || '') + ' ' + (el.getAttribute('value') || '')).toLowerCase();
        if (Array.from(root.querySelectorAll('a[href]')).some(a => ALT_KEYWORDS.test(labelOf(a)))) hasTextAlternative = true;
        if (Array.from(root.querySelectorAll('details')).some(det => ALT_KEYWORDS.test(det.textContent || ''))) hasTextAlternative = true;
        // G173 / G78: a button, menu item or <select> option that switches to the described version
        if (Array.from(root.querySelectorAll('button, [role="button"], [role="menuitem"], option, summary, [role="menuitemradio"]')).some(el => /audio[- ]?desc|described|音声解説|音声ガイド/i.test(labelOf(el)))) hasDescribedVersionControl = true;
        if (hasTextAlternative || hasDescribedVersionControl) break;
      }
      // audioTracks API (G78): a second, user-selectable audio track labelled as description
      try {
        const tracks = video.audioTracks;
        if (tracks && tracks.length > 1) {
          for (let i = 0; i < tracks.length; i++) {
            if (/desc/i.test((tracks[i].kind || '') + ' ' + (tracks[i].label || ''))) hasDescribedVersionControl = true;
          }
        }
      } catch (_) { /* not supported */ }
      hasTextAlternative = hasTextAlternative || hasDescribedVersionControl;

      if (!hasDescTrack && !altAudio && !hasTextAlternative) {
        issues.push({
          html: video.outerHTML.slice(0, 200),
          element_id: video.id || null,
          target: video.id ? [`video#${CSS.escape(video.id)}`] : ['video'],
          tag: 'VIDEO',
        });
      }
    }

    return { videoCount: videos.length, issues, videoOnly };
  });

  if (data.videoCount === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: FALLBACK_DESCRIPTION,
        impact: null,
        status: 'not_applicable',
        reason: _t(sharedContext, 'No <video> elements found on this page.', 'このページには <video> 要素はありません。'),
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
          '{count} <video> element(s) checked — all have an audio description or text alternative{vo}.',
          '{count} 件の <video> を確認しました — すべてに音声解説または代替テキストがあります{vo}。',
          { count: data.videoCount, vo: data.videoOnly ? _t(sharedContext, ` (${data.videoOnly} silent video-only element(s) excluded — G159)`, `（無音の動画のみ ${data.videoOnly} 件は除外 — G159）`) : '' },
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
      status: 'incomplete',
      reason: _t(
        sharedContext,
        '{issueCount} of {videoCount} <video> element(s) have no detectable audio description or full-text alternative.',
        '{videoCount} 件中 {issueCount} 件の <video> に音声解説または代替テキストが見つかりませんでした。',
        { issueCount: data.issues.length, videoCount: data.videoCount },
      ),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
