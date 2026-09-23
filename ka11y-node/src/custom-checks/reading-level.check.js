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

    // G86: a summary / abstract section; G79: a spoken (audio) version of the text.
    const SUMMARY_RE = /^(summary|abstract|overview|key\s+points|in\s+brief|at\s+a\s+glance|tl;?dr|要約|概要|まとめ|要点|ポイント|サマリー)/i;
    const hasSummary = Array.from(document.querySelectorAll('h1, h2, h3, h4, summary, [role="heading"], [class*="summary" i], [class*="abstract" i], [id*="summary" i]')).some(el => SUMMARY_RE.test((el.textContent || '').trim()));
    const SPOKEN_RE = /listen|read\s+aloud|play\s+audio|audio\s+version|text[-\s]to[-\s]speech|読み上げ|音声で(?:聞く|読む)|音声版|聞く/i;
    const hasSpoken = !!document.querySelector('main audio, article audio, [role="main"] audio') || Array.from(document.querySelectorAll('button, a[href], [role="button"]')).some(el => SPOKEN_RE.test((el.textContent || '') + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('title') || '')));

    // Japanese text: Flesch-Kincaid does not apply. Use sentence length and kanji density,
    // the two strongest predictors in jReadability (Lee & Hasebe), as a proxy.
    const kana = (text.match(/[\u3040-\u30ff]/g) || []).length;
    const kanji = (text.match(/[\u3400-\u9fff]/g) || []).length;
    const cjkTotal = kana + kanji;
    const latinWords = text.split(/\s+/).filter(w => /[a-zA-Z]/.test(w));
    if (cjkTotal >= 300 && kana > 50 && cjkTotal > latinWords.length * 4) {
      const jaSentences = text.split(/[。！？!?]+/).map(s => s.trim()).filter(s => s.length > 3);
      const avgLen = jaSentences.length ? jaSentences.reduce((a, s) => a + s.length, 0) / jaSentences.length : 0;
      const kanjiRatio = cjkTotal ? kanji / cjkTotal : 0;
      return { mode: 'ja', charCount: cjkTotal, sentenceCount: jaSentences.length, avgSentenceLength: Math.round(avgLen), kanjiRatio: Math.round(kanjiRatio * 100) / 100, hasSummary, hasSpoken, tooShort: false, wordCount: latinWords.length };
    }

    const sentences = text.split(/[.!?]+/).filter(s => s.trim().length > 5);
    const words = latinWords;

    if (words.length < minWords) return { wordCount: words.length, tooShort: true, hasSummary, hasSpoken };

    const syllables = words.reduce((sum, w) => sum + countSyllables(w), 0);
    const sentenceCount = Math.max(1, sentences.length);
    const wordCount = words.length;

    // FK Grade Level = 0.39 * (words/sentences) + 11.8 * (syllables/words) - 15.59
    const grade = 0.39 * (wordCount / sentenceCount) + 11.8 * (syllables / wordCount) - 15.59;
    const gradeRounded = Math.round(grade * 10) / 10;

    return { wordCount, syllableCount: syllables, sentenceCount, grade: gradeRounded, tooShort: false, hasSummary, hasSpoken };
  }, MIN_WORDS);

  const supplements = [];
  if (data && data.hasSummary) supplements.push(_t(ctx, 'a summary/overview section is present (G86)', '要約/概要セクションがあります（G86）'));
  if (data && data.hasSpoken) supplements.push(_t(ctx, 'a spoken/audio version is offered (G79)', '音声版/読み上げが提供されています（G79）'));
  const suppNote = supplements.length ? ' ' + supplements.join('; ') + '.' : '';

  if (data && data.mode === 'ja') {
    const ok = data.avgSentenceLength <= 50 && data.kanjiRatio <= 0.35;
    if (ok) {
      return _pass(ctx, _t(ctx,
        'Japanese text ({chars} characters, {s} sentences): average sentence length {avg} characters and kanji ratio {kr}% are within lower-secondary readability limits (≤ 50 chars, ≤ 35% kanji — jReadability proxy).{supp}',
        '日本語テキスト（{chars} 文字、{s} 文）: 平均文長 {avg} 文字、漢字率 {kr}% は中学校レベルの読みやすさの範囲内です（50 文字以下、漢字率 35% 以下 — jReadability 近似）。{supp}',
        { chars: data.charCount, s: data.sentenceCount, avg: data.avgSentenceLength, kr: Math.round(data.kanjiRatio * 100), supp: suppNote }));
    }
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: 'moderate', status: 'incomplete', reason: _t(ctx,
        'Japanese text ({chars} characters, {s} sentences): average sentence length {avg} characters and kanji ratio {kr}% suggest a reading level above lower secondary (limits ≈ 50 chars, 35% kanji — jReadability proxy).{supp}{need}',
        '日本語テキスト（{chars} 文字、{s} 文）: 平均文長 {avg} 文字、漢字率 {kr}% は中学校レベルを超える読みやすさを示唆します（目安: 50 文字、漢字率 35% — jReadability 近似）。{supp}{need}',
        { chars: data.charCount, s: data.sentenceCount, avg: data.avgSentenceLength, kr: Math.round(data.kanjiRatio * 100), supp: suppNote, need: supplements.length ? '' : _t(ctx, ' Provide a summary or a simpler version.', ' 要約または平易な版を提供してください。') }), helpUrl: HELP_URL }],
    };
  }

  if (data.tooShort || data.wordCount < MIN_WORDS) {
    return _na(ctx, _t(ctx,
      'Insufficient text ({n} words) to compute reading level (minimum {min} words required).',
      '読みやすさを計算するのに十分なテキストがありません（{n} 語、最低 {min} 語が必要）。',
      { n: data.wordCount || 0, min: MIN_WORDS }));
  }

  if (data.grade <= FK_THRESHOLD) {
    return _pass(ctx, _t(ctx,
      'Estimated reading level: grade {grade} (Flesch-Kincaid). Within the lower-secondary threshold of grade {threshold}.{supp}',
      '推定読みやすさレベル: {grade} 学年相当（Flesch-Kincaid）。中学校以下の閾値 {threshold} 学年以内です。{supp}',
      { grade: data.grade, threshold: FK_THRESHOLD, supp: suppNote }));
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'moderate',
      status: 'incomplete',
      reason: _t(ctx,
        'Estimated reading level: grade {grade} (Flesch-Kincaid, {words} words, {sentences} sentences). Exceeds the lower-secondary threshold of grade {threshold}.{supp}{need}',
        '推定読みやすさ: {grade} 学年相当（{words} 語、{sentences} 文）。中学校以下の閾値 {threshold} 学年を超えています。{supp}{need}',
        { grade: data.grade, words: data.wordCount, sentences: data.sentenceCount, threshold: FK_THRESHOLD, supp: suppNote, need: supplements.length ? _t(ctx, ' Verify the supplement covers the content (G86/G79).', ' 補足がコンテンツを網羅しているか確認してください（G86/G79）。') : _t(ctx, ' A supplemental version or summary may be needed.', ' 補足版や要約が必要な場合があります。') }),
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
