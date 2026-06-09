'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '3.1.5';
const RULE_ID = 'custom-reading-level';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/reading-level';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Content should not require reading ability more advanced than lower secondary education';

// Flesch-Kincaid Grade Level threshold (US grade 9 ≈ end of lower secondary)
const FK_THRESHOLD = 9;
// Minimum words to run an analysis
const MIN_WORDS = 100;

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

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  const data = await page.evaluate((minWords) => {
    // Collect paragraph text, skipping nav/footer/aside
    const SKIP = new Set(['SCRIPT','STYLE','NAV','FOOTER','ASIDE','HEADER']);
    const textParts = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      if (!node.textContent.trim()) continue;
      let ancestor = node.parentElement;
      let skip = false;
      while (ancestor) {
        if (SKIP.has(ancestor.tagName)) { skip = true; break; }
        ancestor = ancestor.parentElement;
      }
      if (!skip) textParts.push(node.textContent.trim());
    }
    const text = textParts.join(' ').replace(/\s+/g, ' ').trim();

    // ── Flesch-Kincaid Grade Level ───────────────────────────────────────────
    function countSyllables(word) {
      word = word.toLowerCase().replace(/[^a-z]/g, '');
      if (!word) return 0;
      if (word.length <= 3) return 1;
      // Remove trailing silent e
      word = word.replace(/(?:[^laeiouy]|ed|[^laeiouy]e)$/, '');
      // Remove leading y
      word = word.replace(/^y/, '');
      const m = word.match(/[aeiouy]{1,2}/g);
      return m ? Math.max(1, m.length) : 1;
    }

    const sentences = text.split(/[.!?]+/).filter(s => s.trim().length > 5);
    const words = text.split(/\s+/).filter(w => /[a-zA-Z]/.test(w));

    if (words.length < minWords) return { wordCount: words.length, tooShort: true };

    const syllables = words.reduce((sum, w) => sum + countSyllables(w), 0);
    const sentenceCount = Math.max(1, sentences.length);
    const wordCount = words.length;

    // FK Grade Level = 0.39 * (words/sentences) + 11.8 * (syllables/words) - 15.59
    const grade = 0.39 * (wordCount / sentenceCount) + 11.8 * (syllables / wordCount) - 15.59;
    const gradeRounded = Math.round(grade * 10) / 10;

    return { wordCount, syllableCount: syllables, sentenceCount, grade: gradeRounded, tooShort: false };
  }, MIN_WORDS);

  if (data.tooShort || data.wordCount < MIN_WORDS) {
    return _na(ctx, _t(ctx,
      'Insufficient text ({n} words) to compute reading level (minimum {min} words required).',
      '読みやすさを計算するのに十分なテキストがありません（{n} 語、最低 {min} 語が必要）。',
      { n: data.wordCount || 0, min: MIN_WORDS }));
  }

  if (data.grade <= FK_THRESHOLD) {
    return _pass(ctx, _t(ctx,
      'Estimated reading level: grade {grade} (Flesch-Kincaid). Within the lower-secondary threshold of grade {threshold}.',
      '推定読みやすさレベル: {grade} 学年相当（Flesch-Kincaid）。中学校以下の閾値 {threshold} 学年以内です。',
      { grade: data.grade, threshold: FK_THRESHOLD }));
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'moderate',
      status: 'incomplete',
      reason: _t(ctx,
        'Estimated reading level: grade {grade} (Flesch-Kincaid, {words} words, {sentences} sentences). Exceeds the lower-secondary threshold of grade {threshold}. A supplemental version or summary may be needed.',
        '推定読みやすさ: {grade} 学年相当（{words} 語、{sentences} 文）。中学校以下の閾値 {threshold} 学年を超えています。補足版や要約が必要な場合があります。',
        { grade: data.grade, words: data.wordCount, sentences: data.sentenceCount, threshold: FK_THRESHOLD }),
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
