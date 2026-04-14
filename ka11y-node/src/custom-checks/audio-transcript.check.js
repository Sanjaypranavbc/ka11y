'use strict';

const {
  buildKeywordPattern,
  getKeywordList,
  getSharedRuleContext,
  renderReasonTemplate,
} = require('./sharedAssets');

const SC = '1.2.1';
const RULE_ID = 'custom-audio-transcript';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/audio-only-and-video-only-prerecorded';

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);
  const transcriptPattern = buildKeywordPattern(
    getKeywordList('audio_transcript', 'transcript_keywords', sharedContext)
  ) || 'transcript|caption|text\\s+version|description';

  const data = await page.evaluate((keywordPattern) => {
    const transcriptRe = new RegExp(keywordPattern, 'i');
    const audioEls = Array.from(document.querySelectorAll('audio'));
    if (audioEls.length === 0) return { audioCount: 0, issues: [] };

    const issues = [];

    for (const audio of audioEls) {
      // 1. <track> element inside <audio> (captions or descriptions)
      const hasTrack = !!audio.querySelector(
        'track[kind="captions"], track[kind="descriptions"], track[kind="subtitles"]'
      );

      // 2. Nearby transcript link — search within closest semantic container
      const container =
        audio.closest('figure, article, section, [role="region"], [role="main"]') ||
        audio.parentElement;
      const transcriptLinks = container
        ? Array.from(container.querySelectorAll('a[href]')).filter(a => {
            const combined = ((a.textContent || '') + ' ' + (a.getAttribute('aria-label') || '')).toLowerCase();
            return transcriptRe.test(combined);
          })
        : [];

      // 3. <figcaption> inside a parent <figure>
      const hasFigCaption = !!(audio.closest('figure') && audio.closest('figure').querySelector('figcaption'));

      // 3b. <details> element in container whose summary/text mentions transcript
      const hasDetailsTranscript = container
        ? Array.from(container.querySelectorAll('details')).some(det => {
            const text = (det.textContent || '').toLowerCase();
            const summary = (det.querySelector('summary') || {}).textContent || '';
            const combined = text + ' ' + summary.toLowerCase();
            return transcriptRe.test(combined);
          })
        : false;

      // 4. aria-describedby pointing to an existing element with text
      const describedByIds = (audio.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean);
      const hasAriaDescription = describedByIds.some(id => {
        const target = document.getElementById(id);
        return !!target && (target.textContent || '').trim().length > 0;
      });

      if (!hasTrack && transcriptLinks.length === 0 && !hasFigCaption && !hasDetailsTranscript && !hasAriaDescription) {
        issues.push({
          html: audio.outerHTML.slice(0, 150),
          element_id: audio.id || null,
          target: audio.id ? [`audio#${CSS.escape(audio.id)}`] : ['audio'],
          tag: 'AUDIO',
        });
      }
    }

    return { audioCount: audioEls.length, issues };
  }, transcriptPattern);

  if (data.audioCount === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Audio-only prerecorded content must have a text alternative',
        impact: null,
        status: 'pass',
        reason: renderReasonTemplate(
          'audio_transcript',
          'no_audio',
          {},
          sharedContext,
          'No <audio> elements found on this page.',
        ),
        helpUrl: HELP_URL,
      }],
    };
  }

  if (data.issues.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Audio-only prerecorded content must have a text alternative',
        impact: null,
        status: 'pass',
        reason: renderReasonTemplate(
          'audio_transcript',
          'pass_detected',
          { audio_count: data.audioCount },
          sharedContext,
          `${data.audioCount} <audio> element(s) checked — all appear to have a text alternative.`,
        ),
        helpUrl: HELP_URL,
      }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Audio-only prerecorded content must have a text alternative',
      impact: 'serious',
      status: 'incomplete',
      reason: renderReasonTemplate(
        'audio_transcript',
        'missing_transcript',
        {
          issue_count: data.issues.length,
          audio_count: data.audioCount,
          element_list: '',
        },
        sharedContext,
        `${data.issues.length} of ${data.audioCount} <audio> element(s) have no detectable text alternative.`,
      ),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
