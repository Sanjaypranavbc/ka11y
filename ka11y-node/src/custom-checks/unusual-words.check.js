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

    // G70: a function to search an online dictionary
    const DICTIONARY_RE = /dictionary|thesaurus|wiktionary|merriam-webster|dictionary\.com|lexico|look\s*up\s+(?:a\s+)?(?:word|term)|辞書|辞典|用語検索/i;
    const hasDictionarySearch = Array.from(document.querySelectorAll('a[href], form, [role="search"]')).some(el =>
      DICTIONARY_RE.test(el.textContent || '') || DICTIONARY_RE.test(el.getAttribute('href') || el.getAttribute('action') || '') || DICTIONARY_RE.test(el.getAttribute('aria-label') || ''));

    const hasDefinitionMechanism = hasDfn || hasGlossaryLink || hasDefinitionList || hasDetailsDef || hasDictionarySearch;

    // G101 / G112: rare-word candidates and whether each is defined nearby. Without a
    // frequency corpus, rarity is approximated by word shape: long Latin/Greek-derived
    // words (≥12 letters or technical suffixes), CamelCase/technical tokens, and
    // kanji compounds of four or more characters. A candidate counts as defined when
    // it is followed by a parenthetical or an "is/means/refers to" clause (G112), is
    // wrapped in <dfn>/<abbr>/aria-describedby, or is linked (glossary link).
    const JARGON_RE = /\b[A-Za-z][a-z]{9,}\b/g;
    const RARE_RE = /\b(?:[A-Za-z][a-z]{11,}|[a-z]+(?:ization|isation|ological|ometric|omorphic|ectomy|itis|osis|aceous|ivorous|genesis|phoresis|plasty|tropic|philic|phobic)|[A-Z][a-z]+[A-Z][A-Za-z]+)\b/g;
    const KANJI_COMPOUND_RE = /[\u4e00-\u9fff]{4,}/g;
    const COMMON = new Set(['information', 'organization', 'organisation', 'international', 'communication', 'applications', 'accessibility', 'responsibility', 'administration', 'professional', 'requirements', 'environment', 'development', 'representative', 'understanding', 'relationship', 'opportunities', 'particularly', 'automatically', 'significantly', 'approximately', 'individuals', 'infrastructure', 'configuration', 'implementation', 'documentation', 'notification', 'notifications', 'subscription', 'authentication', 'authorization', 'transportation', 'manufacturing', 'entertainment', 'recommendation', 'recommendations', 'specifications', 'characteristics', 'unfortunately', 'availability', 'compatibility', 'functionality', 'establishment', 'considerations', 'participation']);
    let jargonCount = 0;
    const rare = new Map(); // word → { count, defined }
    const DEF_AFTER_RE = (w) => new RegExp(w + '\\s*(?:\\(|（|\\[|[-–—:]\\s|\\s(?:is|are|means|refers to|i\\.e\\.|that is|とは|、すなわち|（))', 'i');
    for (const el of document.querySelectorAll('p,li,td,dd')) {
      const text = (el.textContent || '').replace(/\s+/g, ' ');
      const matches = text.match(JARGON_RE);
      if (matches) jargonCount += matches.length;
      for (const m of [...(text.match(RARE_RE) || []), ...(text.match(KANJI_COMPOUND_RE) || [])]) {
        const w = m; const key = w.toLowerCase();
        if (COMMON.has(key) || key.length > 40) continue;
        const entry = rare.get(key) || { word: w, count: 0, defined: false };
        entry.count++;
        if (!entry.defined) {
          try {
            const inSemantic = Array.from(el.querySelectorAll('dfn, abbr[title], [aria-describedby], a[href], [title]')).some(x => (x.textContent || '').includes(w));
            entry.defined = inSemantic || DEF_AFTER_RE(w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).test(text);
          } catch (_) { /* ignore */ }
        }
        rare.set(key, entry);
      }
    }
    const rareWords = Array.from(rare.values()).filter(r => r.count >= 1).sort((a, b) => b.count - a.count).slice(0, 40);
    const rareUndefined = rareWords.filter(r => !r.defined).slice(0, 12).map(r => ({ word: r.word, count: r.count }));
    const rareDefined = rareWords.filter(r => r.defined).length;
    const hasComplexContent = jargonCount > 10 || rareWords.length >= 5;

    return { hasDfn, hasGlossaryLink, hasDefinitionList, hasDetailsDef, hasDictionarySearch, hasAriaDescribedBy, hasDefinitionMechanism, hasComplexContent, jargonCount, rareUndefined, rareDefined, rareTotal: rareWords.length };
  });

  const rareNote = (data.rareTotal || 0)
    ? _t(ctx, ' {t} unusual/technical word(s) detected; {d} are defined in place (G112){u}.', ' 専門的・珍しい語を {t} 件検出。うち {d} 件は文中で定義されています（G112）{u}。', { t: data.rareTotal, d: data.rareDefined || 0, u: (data.rareUndefined || []).length ? _t(ctx, `; undefined: ${data.rareUndefined.slice(0, 5).map(r => r.word).join(', ')}`, `。未定義: ${data.rareUndefined.slice(0, 5).map(r => r.word).join(', ')}`) : '' })
    : '';

  if (data.hasDefinitionMechanism) {
    const mechanisms = [
      data.hasDfn && '<dfn>',
      data.hasGlossaryLink && 'glossary link',
      data.hasDefinitionList && '<dl> definition list',
      data.hasDetailsDef && '<details> definition',
      data.hasDictionarySearch && 'dictionary search (G70)',
    ].filter(Boolean).join(', ');

    return _pass(ctx, _t(ctx,
      'Definition mechanisms detected ({mechanisms}). Manual check recommended to verify coverage of all unusual words.',
      '定義メカニズムが検出されました（{mechanisms}）。すべての専門用語をカバーしているか手動確認を推奨します。',
      { mechanisms }) + rareNote);
  }

  if (!data.hasComplexContent) {
    return _pass(ctx, _t(ctx,
      'No definition mechanism found, but page content appears simple (no unusual word density detected).',
      '定義メカニズムは見つかりませんでしたが、ページコンテンツはシンプルです（専門用語の密度は低い）。') + rareNote);
  }

  if ((data.rareTotal || 0) >= 3 && !(data.rareUndefined || []).length) {
    return _pass(ctx, _t(ctx,
      'No global definition mechanism, but every detected unusual word is defined in place (parenthetical/“means” clause, <dfn>, <abbr> or link) — G112.',
      '全体的な定義メカニズムはありませんが、検出された珍しい語はすべて文中で定義されています（括弧書き/「とは」、<dfn>、<abbr>、リンク）— G112。') + rareNote);
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
        '<dfn>、用語集リンク、定義リストが見つからず、ページに複雑な語彙が含まれる可能性があります。手動確認が必要です。') + rareNote,
      elements: (data.rareUndefined || []).map(r => ({ target: 'text', snippet: r.word, detail: `"${r.word}" (${r.count}×) is not defined in place — add a definition, <dfn> or glossary link (G101/G112)` })),
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
