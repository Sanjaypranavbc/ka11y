'use strict';

const SC = '1.2.1';
const RULE_ID = 'custom-audio-transcript';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/audio-only-and-video-only-prerecorded';

async function run(page) {
  const data = await page.evaluate(() => {
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
            return /transcript|caption|text\s+version|read|description|audio\s+text/i.test(combined);
          })
        : [];

      // 3. <figcaption> inside a parent <figure>
      const hasFigCaption = !!(audio.closest('figure') && audio.closest('figure').querySelector('figcaption'));

      // 4. aria-describedby pointing to an existing element with text
      const describedById = audio.getAttribute('aria-describedby');
      const hasAriaDescription = describedById
        ? !!document.getElementById(describedById)
        : false;

      if (!hasTrack && transcriptLinks.length === 0 && !hasFigCaption && !hasAriaDescription) {
        issues.push({ html: audio.outerHTML.slice(0, 150) });
      }
    }

    return { audioCount: audioEls.length, issues };
  });

  if (data.audioCount === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Audio-only prerecorded content must have a text alternative',
        impact: null,
        status: 'pass',
        reason: 'No <audio> elements found on this page.',
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
        reason: `${data.audioCount} <audio> element(s) checked — all appear to have a text alternative (track element, nearby transcript link, figcaption, or aria-describedby).`,
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
      reason: `${data.issues.length} of ${data.audioCount} <audio> element(s) have no detectable text alternative (no <track>, no nearby transcript link, no <figcaption>, no aria-describedby). Verify a full text transcript is available adjacent to each audio element.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };