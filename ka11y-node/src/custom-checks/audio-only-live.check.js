'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '1.2.9';
const RULE_ID = 'custom-audio-only-live';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/audio-only-live';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Live audio-only content must have a text alternative that presents equivalent information';

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

// Live stream URL patterns
const LIVE_SRC_RE = /\.m3u8|\.mpd|\/live\/|\/stream\/|shoutcast|icecast|radio/i;
// Known audio streaming embed domains
const LIVE_EMBED_DOMAINS = ['tunein.com', 'soundcloud.com', 'mixcloud.com', 'live.', 'radio.', 'stream.'];
// Text caption / transcript signals
const TRANSCRIPT_RE = /transcript|live\s+text|captions?|subtitles?|text\s+alternative|書き起こし|字幕|テキスト代替/i;

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  const data = await page.evaluate((liveSrcPat, embedDomains, transcriptPat) => {
    const liveRe = new RegExp(liveSrcPat, 'i');
    const transcriptRe = new RegExp(transcriptPat, 'i');

    const issues = [];
    let liveCount = 0;

    // ── <audio> elements ──────────────────────────────────────────────────────
    for (const audio of document.querySelectorAll('audio')) {
      const src = (audio.currentSrc || audio.getAttribute('src') || '');
      const sourcesSrc = Array.from(audio.querySelectorAll('source')).map(s => s.getAttribute('src') || '').join(' ');
      const allSrc = src + ' ' + sourcesSrc;

      const isLiveUrl = liveRe.test(allSrc);
      const isLiveAttr = audio.getAttribute('data-live') === 'true' || audio.getAttribute('is-live') === 'true';
      if (!isLiveUrl && !isLiveAttr) continue;

      liveCount++;
      const container = audio.closest('figure,article,section,[role="region"],[role="main"]') || audio.parentElement;

      // Check for adjacent live text alternative
      const hasLiveRegion = container && Array.from(container.querySelectorAll('[aria-live],[role="log"],[role="status"]')).some(el =>
        transcriptRe.test((el.getAttribute('aria-label') || '') + ' ' + (el.textContent || '')));
      const hasTranscriptLink = container && Array.from(container.querySelectorAll('a[href]')).some(a =>
        transcriptRe.test((a.textContent || '') + ' ' + (a.getAttribute('aria-label') || '')));

      if (!hasLiveRegion && !hasTranscriptLink) {
        issues.push({
          target: audio.id ? `audio#${CSS.escape(audio.id)}` : 'audio',
          snippet: audio.outerHTML.slice(0, 200),
          detail: 'Live audio stream with no detectable text alternative (aria-live region or transcript link)',
        });
      }
    }

    // ── iframes with known audio streaming domains ────────────────────────────
    for (const iframe of document.querySelectorAll('iframe[src]')) {
      const src = (iframe.getAttribute('src') || '').toLowerCase();
      if (!embedDomains.some(d => src.includes(d))) continue;

      liveCount++;
      const container = iframe.closest('figure,article,section,[role="region"],[role="main"]') || iframe.parentElement;
      const hasLiveRegion = container && Array.from(container.querySelectorAll('[aria-live],[role="log"]')).some(el =>
        transcriptRe.test((el.textContent || '') + ' ' + (el.getAttribute('aria-label') || '')));

      if (!hasLiveRegion) {
        issues.push({
          target: iframe.id ? `iframe#${CSS.escape(iframe.id)}` : 'iframe',
          snippet: iframe.outerHTML.slice(0, 200),
          detail: 'Embedded audio stream with no adjacent live text alternative detected',
        });
      }
    }

    return { liveCount, issues };
  }, LIVE_SRC_RE.source, LIVE_EMBED_DOMAINS, TRANSCRIPT_RE.source);

  if (!data.liveCount) {
    return _na(ctx, _t(ctx, 'No live audio-only streams detected on this page — criterion not applicable.', 'このページにライブ音声のみのストリームは検出されませんでした。'));
  }
  if (!data.issues.length) {
    return _pass(ctx, _t(ctx,
      '{n} live audio stream(s) detected — all have a text alternative or live transcript region.',
      '{n} 件のライブ音声ストリームが検出されました — すべてにテキスト代替またはライブ書き起こし領域があります。',
      { n: data.liveCount }));
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'serious',
      status: 'incomplete',
      reason: _t(ctx,
        '{i} of {n} live audio stream(s) have no detectable text alternative. Manual review required.',
        '{n} 件中 {i} 件のライブ音声ストリームにテキスト代替が見当たりません。手動確認が必要です。',
        { i: data.issues.length, n: data.liveCount }),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
