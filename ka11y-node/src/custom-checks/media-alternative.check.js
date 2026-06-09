'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '1.2.8';
const RULE_ID = 'custom-media-alternative';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/media-alternative-prerecorded';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Prerecorded synchronized media must have a full-text media alternative';

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

// Keywords indicating a full-text transcript or media alternative is present.
const ALT_RE = /transcript|text\s+version|full[- ]?text|media\s+alternative|text\s+alternative|書き起こし|文字起こし|テキスト版/i;

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  const data = await page.evaluate((altPattern) => {
    const re = new RegExp(altPattern, 'i');
    const media = [
      ...Array.from(document.querySelectorAll('video')),
      ...Array.from(document.querySelectorAll('audio')),
    ].filter(el => !el.muted);

    if (!media.length) return { mediaCount: 0, issues: [] };

    const issues = [];
    for (const el of media) {
      const container = el.closest('figure,article,section,main,[role="region"],[role="main"]') || el.parentElement;
      if (!container) { issues.push({ target: el.tagName.toLowerCase(), snippet: el.outerHTML.slice(0, 200) }); continue; }

      // Look for a transcript link or inline transcript block
      const hasTranscriptLink = Array.from(container.querySelectorAll('a[href]')).some(a =>
        re.test((a.textContent || '') + ' ' + (a.getAttribute('aria-label') || '')));

      const hasInlineTranscript = Array.from(container.querySelectorAll('details,p,div')).some(block =>
        block !== el && re.test(block.getAttribute('aria-label') || block.getAttribute('title') || '') &&
        (block.textContent || '').trim().length > 100);

      if (!hasTranscriptLink && !hasInlineTranscript) {
        issues.push({ target: `${el.tagName.toLowerCase()}${el.id ? '#' + CSS.escape(el.id) : ''}`, snippet: el.outerHTML.slice(0, 200) });
      }
    }
    return { mediaCount: media.length, issues };
  }, ALT_RE.source);

  if (!data.mediaCount) {
    return _na(ctx, _t(ctx, 'No prerecorded <video> or <audio> elements found.', '録画済みの <video> または <audio> 要素はありません。'));
  }
  if (!data.issues.length) {
    return _pass(ctx, _t(ctx,
      'All {n} media element(s) have a detectable full-text alternative or transcript link.',
      '{n} 件のメディア要素すべてに代替テキストまたは書き起こしリンクが検出されました。',
      { n: data.mediaCount }));
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'serious',
      status: 'incomplete',
      reason: _t(ctx,
        '{i} of {n} media element(s) have no detectable full-text alternative or transcript. Manual review required.',
        '{n} 件中 {i} 件のメディア要素に代替テキストまたは書き起こしが見当たりません。手動確認が必要です。',
        { i: data.issues.length, n: data.mediaCount }),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
