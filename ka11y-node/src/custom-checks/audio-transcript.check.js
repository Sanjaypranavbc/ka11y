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

  const data = await page.evaluate(async (keywordPattern) => {
    const transcriptRe = new RegExp(keywordPattern, 'i');
    const FILENAME_RE = /^[\w.\- ]+\.(txt|pdf|doc|docx|rtf|vtt|srt|html?)$/i;

    function basenameFromHref(href) {
      if (!href) return '';
      try {
        const url = new URL(href, document.baseURI);
        const path = url.pathname || '';
        const base = path.split('/').pop() || '';
        return decodeURIComponent(base);
      } catch (_) {
        const path = href.split('?')[0].split('#')[0];
        const base = (path.split('/').pop() || '').trim();
        try {
          return decodeURIComponent(base);
        } catch (__) {
          return base;
        }
      }
    }

    function isFilenameOnlyLabel(textValue, hrefValue) {
      const text = (textValue || '').trim();
      const hrefBase = basenameFromHref(hrefValue);
      const normalizedText = text.replace(/[()]/g, ' ').trim();

      if (normalizedText && !FILENAME_RE.test(normalizedText)) return false;
      if (!normalizedText && !hrefBase) return false;

      const candidate = normalizedText || hrefBase;
      // Consider single-token filename-like labels (e.g., transcript.pdf, audio.vtt) as F30 risk.
      return FILENAME_RE.test(candidate);
    }

    const audioEls = Array.from(document.querySelectorAll('audio'));
    if (audioEls.length === 0) return { audioCount: 0, issues: [] };

    const issues = [];

    for (const audio of audioEls) {
      // 1. <track> element inside <audio> (captions or descriptions)
      const tracks = Array.from(audio.querySelectorAll('track[kind="captions"], track[kind="descriptions"], track[kind="subtitles"]'));
      let hasValidTrack = false;
      
      for (const track of tracks) {
         const src = track.getAttribute('src');
         if (src) {
             try {
                 const response = await fetch(src, { method: 'HEAD', cache: 'no-cache' });
                 if (response.ok) {
                     hasValidTrack = true;
                     break;
                 }
             } catch (e) {
                 // Fetch might fail due to CORS or bad URL, if so, the track is unreliable.
             }
         }
      }

      // 2. Nearby transcript link — search within closest semantic container
      const container =
        audio.closest('figure, article, section, [role="region"], [role="main"]') ||
        audio.parentElement;
      const transcriptLinks = container
        ? Array.from(container.querySelectorAll('a[href]')).filter(a => {
            const combined = ((a.textContent || '') + ' ' + (a.getAttribute('aria-label') || '')).toLowerCase();
            return transcriptRe.test(combined);
          }).map((a) => ({
            href: a.getAttribute('href') || '',
            text: (a.textContent || '').trim(),
            ariaLabel: (a.getAttribute('aria-label') || '').trim(),
          }))
        : [];
      const transcriptLinksWithReadableLabel = transcriptLinks.filter((link) => {
        const textValue = [link.text, link.ariaLabel].filter(Boolean).join(' ').trim();
        return !isFilenameOnlyLabel(textValue, link.href);
      });
      const hasFilenameOnlyTranscriptLinks = transcriptLinks.length > 0 && transcriptLinksWithReadableLabel.length === 0;

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

      if (!hasValidTrack && transcriptLinksWithReadableLabel.length === 0 && !hasFigCaption && !hasDetailsTranscript && !hasAriaDescription) {
        issues.push({
          html: audio.outerHTML.slice(0, 150),
          element_id: audio.id || null,
          target: audio.id ? [`audio#${CSS.escape(audio.id)}`] : ['audio'],
          tag: 'AUDIO',
          filename_only_transcript_link: hasFilenameOnlyTranscriptLinks,
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

  const filenameOnlyCount = data.issues.filter(issue => issue.filename_only_transcript_link).length;
  const elementListHint = filenameOnlyCount > 0
    ? `${filenameOnlyCount} item(s) appear to use filename-only transcript links (F30)`
    : '';

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
          filename_only_count: filenameOnlyCount,
          element_list: elementListHint,
        },
        sharedContext,
        `${data.issues.length} of ${data.audioCount} <audio> element(s) have no detectable text alternative.` +
        (filenameOnlyCount > 0 ? ` ${filenameOnlyCount} item(s) only expose filename-like transcript links (F30).` : ''),
      ),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
