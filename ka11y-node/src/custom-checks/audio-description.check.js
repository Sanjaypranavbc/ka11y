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

  const data = await page.evaluate(() => {
    const ALT_KEYWORDS = /transcript|text\s+version|full[- ]?text\s+alternative|audio[- ]?description|descriptive\s+transcript|書き起こし|文字起こし|音声解説|音声ガイド|代替テキスト/i;

    const videos = Array.from(document.querySelectorAll('video'));
    if (videos.length === 0) return { videoCount: 0, issues: [] };

    const issues = [];

    for (const video of videos) {
      const muted = video.muted === true;
      if (muted) continue;

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
      let hasTextAlternative = false;
      if (container) {
        const links = Array.from(container.querySelectorAll('a[href]'));
        hasTextAlternative = links.some(a => {
          const text = ((a.textContent || '') + ' ' + (a.getAttribute('aria-label') || '')).toLowerCase();
          return ALT_KEYWORDS.test(text);
        });
        if (!hasTextAlternative) {
          hasTextAlternative = Array.from(container.querySelectorAll('details')).some(det => {
            return ALT_KEYWORDS.test(det.textContent || '');
          });
        }
      }

      if (!hasDescTrack && !altAudio && !hasTextAlternative) {
        issues.push({
          html: video.outerHTML.slice(0, 200),
          element_id: video.id || null,
          target: video.id ? [`video#${CSS.escape(video.id)}`] : ['video'],
          tag: 'VIDEO',
        });
      }
    }

    return { videoCount: videos.length, issues };
  });

  if (data.videoCount === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: FALLBACK_DESCRIPTION,
        impact: null,
        status: 'pass',
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
          '{count} <video> element(s) checked — all have an audio description or text alternative.',
          '{count} 件の <video> を確認しました — すべてに音声解説または代替テキストがあります。',
          { count: data.videoCount },
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
