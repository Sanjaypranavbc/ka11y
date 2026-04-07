'use strict';

const SC = '3.1.6';
const RULE_ID = 'custom-pronunciation';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/pronunciation';

// Minimum share of CJK characters in text before a page is considered to
// benefit significantly from ruby annotation (≥ 5 % of visible characters).
const CJK_RATIO_THRESHOLD = 0.05;

// CJK Unified Ideographs + CJK Extension A/B + Katakana + Hiragana
// Note: hiragana/katakana are phonetic but kanji in the CJK block benefit most.
const CJK_RE = /[\u3400-\u9FFF\uF900-\uFAFF\u{20000}-\u{2A6DF}]/u;
const KANJI_RE = /[\u4E00-\u9FFF\u3400-\u4DBF]/; // CJK Unified Ideographs (common kanji)

async function run(page) {
  const data = await page.evaluate((cjkRatio, kanji) => {
    // ── 1. Page language ──────────────────────────────────────────────────────
    const htmlLang = (document.documentElement.getAttribute('lang') || '').toLowerCase();
    // Only apply pronunciation check to pages declared as Japanese (or CJK).
    // For non-CJK pages this check is not applicable → pass.
    const isCjkPage = /^(ja|zh|ko|zh-hans|zh-hant|zh-tw|zh-cn)/.test(htmlLang);

    // ── 2. Check visible text CJK density (heuristic for unlabelled lang attr) ─
    const bodyText = (document.body && document.body.innerText) || '';
    const totalChars = bodyText.replace(/\s/g, '').length;
    const cjkChars   = (bodyText.match(/[\u3400-\u9FFF\uF900-\uFAFF]/g) || []).length;
    const cjkDensity = totalChars > 0 ? cjkChars / totalChars : 0;
    const hasCjkContent = cjkDensity >= cjkRatio;

    // If no CJK content and not a CJK-declared page → pass (not applicable)
    if (!isCjkPage && !hasCjkContent) {
      return {
        applicable: false,
        rubyCount: 0,
        kanjiCount: 0,
        kanjiWithRuby: 0,
        sampleKanji: [],
        htmlLang,
        cjkDensityPct: Math.round(cjkDensity * 100),
      };
    }

    // ── 3. Count <ruby> elements ──────────────────────────────────────────────
    const rubyEls = Array.from(document.querySelectorAll('ruby'));
    const rubyCount = rubyEls.length;

    // ── 4. Sample kanji-heavy text nodes not wrapped in <ruby> ───────────────
    // Walk all text nodes in the body, find ones with kanji not inside a <ruby>.
    const kanjiRe = new RegExp(kanji);
    const walker = document.createTreeWalker(
      document.body || document.documentElement,
      NodeFilter.SHOW_TEXT,
      null,
      false,
    );

    const unrubyedSamples = [];
    let kanjiCount = 0;
    let kanjiWithRuby = 0;

    let node;
    while ((node = walker.nextNode())) {
      const text = (node.nodeValue || '').trim();
      if (!text || !kanjiRe.test(text)) continue;

      // Count kanji chars in this text node
      const localKanji = (text.match(/[\u4E00-\u9FFF\u3400-\u4DBF]/g) || []).length;
      if (localKanji === 0) continue;
      kanjiCount += localKanji;

      // Is this node inside a <ruby> element?
      let ancestor = node.parentElement;
      let insideRuby = false;
      while (ancestor && ancestor !== document.body) {
        if (ancestor.tagName === 'RUBY') { insideRuby = true; break; }
        ancestor = ancestor.parentElement;
      }

      if (insideRuby) {
        kanjiWithRuby += localKanji;
      } else if (unrubyedSamples.length < 5) {
        unrubyedSamples.push(text.slice(0, 40));
      }
    }

    // ── 5. Section-level CJK scan (even on non-CJK pages) ────────────────────
    // Find sub-elements with explicit CJK lang attributes, check ruby coverage
    const cjkSectionIssues = [];
    if (!isCjkPage) {
      const cjkSections = document.querySelectorAll('[lang^="ja"], [lang^="zh"], [lang^="ko"]');
      for (const section of cjkSections) {
        const secRubyEls = Array.from(section.querySelectorAll('ruby'));
        const secText = (section.innerText || section.textContent || '').trim();
        const secKanji = (secText.match(/[\u4E00-\u9FFF\u3400-\u4DBF]/g) || []).length;
        if (secKanji === 0) continue;

        let secKanjiWithRuby = 0;
        for (const rubyEl of secRubyEls) {
          const rt = rubyEl.textContent || '';
          const rubyKanji = (rt.match(/[\u4E00-\u9FFF\u3400-\u4DBF]/g) || []).length;
          secKanjiWithRuby += rubyKanji;
        }

        const secRubyPct = Math.round((secKanjiWithRuby / secKanji) * 100);
        if (secRubyPct < 30) {
          cjkSectionIssues.push({
            lang: section.getAttribute('lang'),
            kanjiCount: secKanji,
            rubyPct: secRubyPct,
            html: section.outerHTML.slice(0, 100),
          });
        }
      }
    }

    return {
      applicable: true,
      rubyCount,
      kanjiCount,
      kanjiWithRuby,
      sampleKanji: unrubyedSamples,
      htmlLang,
      cjkDensityPct: Math.round(cjkDensity * 100),
      cjkSectionIssues,
    };
  }, CJK_RATIO_THRESHOLD, KANJI_RE.source);

  // Not a CJK page — criterion not applicable at page level
  // but check section-level CJK elements
  if (!data.applicable) {
    if (data.cjkSectionIssues && data.cjkSectionIssues.length > 0) {
      const sampleSections = data.cjkSectionIssues.slice(0, 3)
        .map(s => `[lang="${s.lang}"] (${s.kanjiCount} kanji, ${s.rubyPct}% ruby coverage)`)
        .join('; ');
      return {
        successCriteriaId: SC,
        rules: [{
          ruleId: RULE_ID,
          description: 'Pronunciation of words must be determinable where meaning is ambiguous',
          impact: 'moderate',
          status: 'incomplete',
          reason: `Page language is "${data.htmlLang}" but ${data.cjkSectionIssues.length} section(s) with explicit CJK lang attributes have low ruby coverage (< 30%): ${sampleSections}. Add <ruby> annotations for kanji within these sections.`,
          helpUrl: HELP_URL,
        }],
      };
    }
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Pronunciation of words must be determinable where meaning is ambiguous',
        impact: null,
        status: 'pass',
        reason: `Page language is "${data.htmlLang}" with ${data.cjkDensityPct}% CJK characters — WCAG 3.1.6 Pronunciation is not applicable.`,
        helpUrl: HELP_URL,
      }],
    };
  }

  const { rubyCount, kanjiCount, kanjiWithRuby, sampleKanji, htmlLang, cjkDensityPct } = data;

  // No kanji at all → pass
  if (kanjiCount === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Pronunciation of words must be determinable where meaning is ambiguous',
        impact: null,
        status: 'pass',
        reason: `Page lang="${htmlLang}" (${cjkDensityPct}% CJK), but no kanji characters detected — no ruby annotation needed.`,
        helpUrl: HELP_URL,
      }],
    };
  }

  const rubyPct = kanjiCount > 0 ? Math.round((kanjiWithRuby / kanjiCount) * 100) : 0;

  // Good ruby coverage (≥ 30 % of kanji chars annotated) → pass
  if (rubyCount > 0 && rubyPct >= 30) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Pronunciation of words must be determinable where meaning is ambiguous',
        impact: null,
        status: 'incomplete',
        reason: `${rubyCount} <ruby> element(s) found covering ~${rubyPct}% of kanji characters on this ${htmlLang} page. This is positive evidence, but SC 3.1.6 depends on whether ambiguous words have pronunciation support where needed, so manual verification is still required.`,
        helpUrl: HELP_URL,
      }],
    };
  }

  // Ruby present but low coverage → needs_review
  if (rubyCount > 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Pronunciation of words must be determinable where meaning is ambiguous',
        impact: 'moderate',
        status: 'incomplete',
        reason: `${rubyCount} <ruby> element(s) found but only ~${rubyPct}% of kanji characters are annotated (${kanjiWithRuby}/${kanjiCount}). Consider adding furigana to difficult or ambiguous kanji, especially technical terms and proper nouns, and manually verify that ambiguous pronunciations are covered.`,
        helpUrl: HELP_URL,
      }],
    };
  }

  // No ruby at all on a kanji-heavy page is not enough to auto-fail SC 3.1.6.
  // The criterion is about ambiguous pronunciation, so surface this as manual review.
  const sample = sampleKanji.slice(0, 3).map(s => `"${s}"`).join(', ');
  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Pronunciation of words must be determinable where meaning is ambiguous',
      impact: 'moderate',
      status: 'incomplete',
      reason: `No <ruby> elements found on this ${htmlLang} page (${cjkDensityPct}% CJK, ${kanjiCount} kanji characters). This is not enough to auto-fail SC 3.1.6, but ambiguous terms may lack pronunciation support. Manually verify technical terms, proper nouns, and unusual readings. Sample kanji text: ${sample}.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
