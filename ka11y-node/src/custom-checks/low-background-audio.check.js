'use strict';

const {
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '1.4.7';
const RULE_ID = 'custom-low-background-audio';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/low-or-no-background-audio';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'For pre-recorded audio that contains primarily speech, background sounds are at least 20 dB lower than the foreground speech';

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);

  const data = await page.evaluate(() => {
    const audioElements = Array.from(document.querySelectorAll('audio, video'));
    if (audioElements.length === 0) return { audioCount: 0, issues: [] };

    const issues = [];

    for (const el of audioElements) {
      const hasSrc = !!el.getAttribute('src');
      const hasTracks = el.querySelectorAll('track').length > 0;
      if (!hasSrc && !hasTracks) continue;

      // Check for autoplay
      const autoplay = el.hasAttribute('autoplay') || el.getAttribute('autoplay') === '';
      const muted = el.hasAttribute('muted') || el.getAttribute('muted') === '';
      const loop = el.hasAttribute('loop') || el.getAttribute('loop') === '';
      const controls = el.hasAttribute('controls') || el.getAttribute('controls') === '';

      // Check for background audio indicators
      const altText = (el.getAttribute('alt') || '').toLowerCase();
      const ariaLabel = (el.getAttribute('aria-label') || '').toLowerCase();
      const title = (el.getAttribute('title') || '').toLowerCase();
      const contextText = (altText + ' ' + ariaLabel + ' ' + title);

      const isBackground = /background|bg[- ]?music|ambient|bgm|soundscape|noise|loop|mood/i.test(contextText);
      const isSpeech = /speech|narration|voice|talk|podcast|lecture|audiobook|story|news|interview/i.test(contextText);

      // If it's background audio playing alongside speech, flag for manual review
      if (isBackground && isSpeech) {
        issues.push({
          html: el.outerHTML.slice(0, 200),
          element_id: el.id || null,
          target: el.id ? [`${el.tagName.toLowerCase()}#${CSS.escape(el.id)}`] : [el.tagName.toLowerCase()],
          tag: el.tagName.toUpperCase(),
          hasAutoplay: autoplay,
          hasMuted: muted,
          hasLoop: loop,
          hasControls: controls,
          isBackground: true,
          isSpeech: true,
        });
      } else if (autoplay && !muted && !controls) {
        // Auto-playing audio without controls or mute — likely needs attention
        issues.push({
          html: el.outerHTML.slice(0, 200),
          element_id: el.id || null,
          target: el.id ? [`${el.tagName.toLowerCase()}#${CSS.escape(el.id)}`] : [el.tagName.toLowerCase()],
          tag: el.tagName.toUpperCase(),
          hasAutoplay: autoplay,
          hasMuted: muted,
          hasLoop: loop,
          hasControls: controls,
          isBackground: false,
          isSpeech: false,
        });
      }
    }

    return { audioCount: audioElements.length, issues };
  });

  if (data.audioCount === 0) {
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
          '{count} <audio>/<video> element(s) checked — no background audio playing alongside speech detected.',
          '{count} 件の <audio>/<video> を確認しました — 音声alongside背景音声は検出されませんでした。',
          { count: data.audioCount },
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
      impact: 'moderate',
      status: 'needs_review',
      reason: _t(
        sharedContext,
        '{issueCount} of {audioCount} <audio>/<video> element(s) may have background audio playing alongside speech. Background audio must be at least 20 dB lower than foreground speech. Automated dB measurement is not possible — manual audio analysis required.',
        '{audioCount} 件中 {issueCount} 件の <audio>/<video> で、音声alongside背景音声がplaying的可能性があります。背景音声は前景音声より至少20dB低くある必要があります。自動dB測定は不可能です — 手動の音声分析が必要です。',
        { issueCount: data.issues.length, audioCount: data.audioCount },
      ),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };