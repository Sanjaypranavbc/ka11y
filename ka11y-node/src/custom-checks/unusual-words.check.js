'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '3.1.3';
const RULE_ID = 'custom-unusual-words';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/unusual-words';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'A mechanism must be available for identifying specific definitions of unusual words, jargon, and idioms';

function _t(ctx, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, ctx, en);
}

function _pass(ctx, reason) {
  return {
    successCriteriaId: SC,
    rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'pass', reason, helpUrl: HELP_URL }],
  };
}

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  const data = await page.evaluate(() => {
    // Positive signals: definition mechanisms present in the page
    const hasDfn = document.querySelectorAll('dfn').length > 0;

    // Glossary / definition links
    const GLOSSARY_RE = /glossary|definitions?|terminology|jargon|词汇表|用語集|glossaire/i;
    const hasGlossaryLink = Array.from(document.querySelectorAll('a[href]')).some(a =>
      GLOSSARY_RE.test(a.textContent || '') || GLOSSARY_RE.test(a.getAttribute('href') || '') || GLOSSARY_RE.test(a.getAttribute('aria-label') || ''));

    // Definition lists (dl/dt/dd)
    const hasDefinitionList = document.querySelector('dl > dt') !== null;

    // Details/summary used as inline definition toggle
    const hasDetailsDef = Array.from(document.querySelectorAll('details')).some(d => GLOSSARY_RE.test(d.textContent || ''));

    // aria-describedby on technical terms
    const hasAriaDescribedBy = Array.from(document.querySelectorAll('[aria-describedby]')).length > 0;

    const hasDefinitionMechanism = hasDfn || hasGlossaryLink || hasDefinitionList || hasDetailsDef;

    // Count jargon candidates: words longer than 10 characters in paragraph text
    // as a rough signal that the page has complex language
    const JARGON_RE = /\b[A-Za-z][a-z]{9,}\b/g;
    let jargonCount = 0;
    for (const el of document.querySelectorAll('p,li')) {
      const text = el.textContent || '';
      const matches = text.match(JARGON_RE);
      if (matches) jargonCount += matches.length;
    }
    const hasComplexContent = jargonCount > 10;

    return { hasDfn, hasGlossaryLink, hasDefinitionList, hasDetailsDef, hasAriaDescribedBy, hasDefinitionMechanism, hasComplexContent, jargonCount };
  });

  if (data.hasDefinitionMechanism) {
    const mechanisms = [
      data.hasDfn && '<dfn>',
      data.hasGlossaryLink && 'glossary link',
      data.hasDefinitionList && '<dl> definition list',
      data.hasDetailsDef && '<details> definition',
    ].filter(Boolean).join(', ');

    return _pass(ctx, _t(ctx,
      'Definition mechanisms detected ({mechanisms}). Manual check recommended to verify coverage of all unusual words.',
      '定義メカニズムが検出されました（{mechanisms}）。すべての専門用語をカバーしているか手動確認を推奨します。',
      { mechanisms }));
  }

  if (!data.hasComplexContent) {
    return _pass(ctx, _t(ctx,
      'No definition mechanism found, but page content appears simple (no unusual word density detected).',
      '定義メカニズムは見つかりませんでしたが、ページコンテンツはシンプルです（専門用語の密度は低い）。'));
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'moderate',
      status: 'incomplete',
      reason: _t(ctx,
        'No definition mechanism found (<dfn>, glossary link, or definition list) and the page contains potentially complex vocabulary. Manual review required.',
        '<dfn>、用語集リンク、定義リストが見つからず、ページに複雑な語彙が含まれる可能性があります。手動確認が必要です。'),
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
