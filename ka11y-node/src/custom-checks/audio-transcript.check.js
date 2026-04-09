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
            return /transcript|caption|text\s+version|read|description|audio\s+text|文字起こし|書き起こし|トランスクリプト|字幕|キャプション|テキスト版|音声テキスト|説明文|音声解説|音声ガイド|代替テキスト/i.test(combined);
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
            return /transcript|caption|text\s+version|read|description|audio\s+text|文字起こし|書き起こし|トランスクリプト|字幕|キャプション|テキスト版|音声テキスト|音声解説|音声ガイド|代替テキスト/i.test(combined);
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
          id: audio.id || null,
          src: (audio.getAttribute('src') || audio.querySelector('source')?.getAttribute('src') || '').slice(0, 80),
        });
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

  const elementList = data.issues
    .slice(0, 3)
    .map(i => i.id ? `<audio id="${i.id}">` : (i.src ? `<audio src="${i.src}">` : i.html.slice(0, 60)))
    .join(', ');

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Audio-only prerecorded content must have a text alternative',
      impact: 'serious',
      status: 'incomplete',
      reason: `${data.issues.length} of ${data.audioCount} <audio> element(s) have no detectable text alternative (no <track>, no nearby transcript link, no <figcaption>, no aria-describedby). Provide a full text transcript adjacent to each: ${elementList}.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
