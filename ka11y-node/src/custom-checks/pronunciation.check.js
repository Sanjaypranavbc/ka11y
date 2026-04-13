'use strict';

const {
  getCheckConfig,
  getNumberConfig,
  getSharedRuleContext,
  renderReasonTemplate,
} = require('./sharedAssets');

const SC = '3.1.6';
const RULE_ID = 'custom-pronunciation';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/pronunciation';
const MODE = 'static';
const DESCRIPTION = 'Pronunciation of words must be determinable where meaning is ambiguous';
const FALLBACK_DESCRIPTION = DESCRIPTION;

const DEFAULT_CJK_RATIO_THRESHOLD = 0.05;
const DEFAULT_RUBY_MIN_COVERAGE_PCT = 30;
const DEFAULT_CJK_LANG_PREFIXES = ['ja', 'zh', 'zh-CN', 'zh-TW', 'zh-HK', 'ko', 'zh-hans', 'zh-hant', 'zh-cn', 'zh-tw'];

const KANJI_RE = /[\u4E00-\u9FFF\u3400-\u4DBF]/;

function _getPronunciationConfig(context = {}) {
  const sharedContext = getSharedRuleContext(context);
  const checkConfig = getCheckConfig('pronunciation', sharedContext);
  const cjkLangPrefixes = Array.isArray(checkConfig.cjk_lang_prefixes)
    ? checkConfig.cjk_lang_prefixes.map((value) => String(value || '').trim()).filter(Boolean)
    : DEFAULT_CJK_LANG_PREFIXES;

  return {
    sharedContext,
    cjkRatioThreshold: getNumberConfig('pronunciation', 'cjk_ratio_threshold', DEFAULT_CJK_RATIO_THRESHOLD, sharedContext),
    rubyMinCoveragePct: getNumberConfig('pronunciation', 'ruby_min_coverage_pct', DEFAULT_RUBY_MIN_COVERAGE_PCT, sharedContext),
    cjkLangPrefixes,
  };
}

function _reason(reasonCode, params, context, fallback) {
  return renderReasonTemplate('pronunciation', reasonCode, params, context, fallback);
}

async function run(page, context = {}) {
  const { sharedContext, cjkRatioThreshold, rubyMinCoveragePct, cjkLangPrefixes } = _getPronunciationConfig(context);
  const data = await page.evaluate((config) => {
    const langPrefixes = Array.isArray(config.cjkLangPrefixes) ? config.cjkLangPrefixes : [];
    const rubyMinCoveragePctLocal = Number(config.rubyMinCoveragePct) || 30;
    const cjkRatioThresholdLocal = Number(config.cjkRatioThreshold) || 0.05;

    const htmlLang = (document.documentElement.getAttribute('lang') || '').toLowerCase();
    const isCjkPage = langPrefixes.some(prefix => htmlLang.startsWith(String(prefix).toLowerCase()));

    const bodyText = (document.body && document.body.innerText) || '';
    const totalChars = bodyText.replace(/\s/g, '').length;
    const cjkChars = (bodyText.match(/[\u3400-\u9FFF\uF900-\uFAFF]/g) || []).length;
    const cjkDensity = totalChars > 0 ? cjkChars / totalChars : 0;
    const hasCjkContent = cjkDensity >= cjkRatioThresholdLocal;

    if (!isCjkPage && !hasCjkContent) {
      return {
        applicable: false,
        rubyCount: 0,
        kanjiCount: 0,
        kanjiWithRuby: 0,
        sampleKanji: [],
        htmlLang,
        cjkDensityPct: Math.round(cjkDensity * 100),
        cjkSectionIssues: [],
      };
    }

    const rubyEls = Array.from(document.querySelectorAll('ruby'));
    const rubyCount = rubyEls.length;
    const kanjiRe = new RegExp(config.kanjiSource);
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

      const localKanji = (text.match(/[\u4E00-\u9FFF\u3400-\u4DBF]/g) || []).length;
      if (localKanji === 0) continue;
      kanjiCount += localKanji;

      let ancestor = node.parentElement;
      let insideRuby = false;
      while (ancestor && ancestor !== document.body) {
        if (ancestor.tagName === 'RUBY') {
          insideRuby = true;
          break;
        }
        ancestor = ancestor.parentElement;
      }

      if (insideRuby) {
        kanjiWithRuby += localKanji;
      } else if (unrubyedSamples.length < 5) {
        unrubyedSamples.push(text.slice(0, 40));
      }
    }

    const cjkSectionIssues = [];

    if (!isCjkPage) {
      const cjkSections = Array.from(document.querySelectorAll('[lang]')).filter(section => {
        const sectionLang = (section.getAttribute('lang') || '').toLowerCase();
        return langPrefixes.some(prefix => sectionLang.startsWith(String(prefix).toLowerCase()));
      });
      for (const section of cjkSections) {
        const secRubyEls = Array.from(section.querySelectorAll('ruby'));
        const secText = (section.innerText || section.textContent || '').trim();
        const secKanji = (secText.match(/[\u4E00-\u9FFF\u3400-\u4DBF]/g) || []).length;
        if (secKanji === 0) continue;

        let secKanjiWithRuby = 0;
        for (const rubyEl of secRubyEls) {
          const baseText = Array.from(rubyEl.childNodes)
            .filter(nodeItem => nodeItem.nodeType === Node.TEXT_NODE || (nodeItem.nodeType === Node.ELEMENT_NODE && nodeItem.nodeName !== 'RT'))
            .map(nodeItem => nodeItem.textContent || '')
            .join('');
          secKanjiWithRuby += (baseText.match(/[\u4E00-\u9FFF\u3400-\u4DBF]/g) || []).length;
        }

        const secRubyPct = secKanji > 0 ? Math.round((secKanjiWithRuby / secKanji) * 100) : 0;
        if (secRubyPct < rubyMinCoveragePctLocal) {
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
  }, {
    cjkRatioThreshold,
    rubyMinCoveragePct,
    cjkLangPrefixes,
    kanjiSource: KANJI_RE.source,
  });

  if (!data.applicable) {
    if (data.cjkSectionIssues && data.cjkSectionIssues.length > 0) {
      const sampleSections = data.cjkSectionIssues.slice(0, 3)
        .map(section => `[lang="${section.lang}"] (${section.kanjiCount} kanji, ${section.rubyPct}% ruby coverage)`)
        .join('; ');

      return {
        successCriteriaId: SC,
        rules: [{
          ruleId: RULE_ID,
          description: DESCRIPTION,
          impact: 'moderate',
          status: 'incomplete',
          reason: _reason(
            'section_low_ruby',
            {
              html_lang: data.htmlLang,
              issue_count: data.cjkSectionIssues.length,
              ruby_min_coverage_pct: rubyMinCoveragePct,
              sample_sections: sampleSections,
            },
            sharedContext,
            `Page language is "${data.htmlLang}" but ${data.cjkSectionIssues.length} section(s) with explicit CJK lang attributes have low ruby coverage (< ${rubyMinCoveragePct}%): ${sampleSections}.`,
          ),
          helpUrl: HELP_URL,
        }],
      };
    }

    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: DESCRIPTION,
        impact: null,
        status: 'pass',
        reason: _reason(
          'not_applicable',
          {
            html_lang: data.htmlLang,
            cjk_density_pct: data.cjkDensityPct,
          },
          sharedContext,
          `Page language is "${data.htmlLang}" with ${data.cjkDensityPct}% CJK characters. WCAG 3.1.6 Pronunciation is not applicable.`,
        ),
        helpUrl: HELP_URL,
      }],
    };
  }

  const { rubyCount, kanjiCount, kanjiWithRuby, sampleKanji, htmlLang, cjkDensityPct } = data;

  if (kanjiCount === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: DESCRIPTION,
        impact: null,
        status: 'pass',
        reason: _reason(
          'no_kanji',
          {
            html_lang: htmlLang,
            cjk_density_pct: cjkDensityPct,
          },
          sharedContext,
          `Page lang="${htmlLang}" (${cjkDensityPct}% CJK), but no kanji characters were detected.`,
        ),
        helpUrl: HELP_URL,
      }],
    };
  }

  const rubyPct = kanjiCount > 0 ? Math.round((kanjiWithRuby / kanjiCount) * 100) : 0;

  if (rubyCount > 0 && rubyPct >= rubyMinCoveragePct) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: DESCRIPTION,
        impact: null,
        status: 'pass',
        reason: _reason(
          'pass_with_ruby',
          {
            ruby_count: rubyCount,
            ruby_pct: rubyPct,
            html_lang: htmlLang,
          },
          sharedContext,
          `${rubyCount} <ruby> element(s) were found covering about ${rubyPct}% of kanji characters on this ${htmlLang} page.`,
        ),
        helpUrl: HELP_URL,
      }],
    };
  }

  if (rubyCount > 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: DESCRIPTION,
        impact: 'moderate',
        status: 'incomplete',
        reason: _reason(
          'low_ruby',
          {
            ruby_count: rubyCount,
            ruby_pct: rubyPct,
            kanji_with_ruby: kanjiWithRuby,
            kanji_count: kanjiCount,
          },
          sharedContext,
          `${rubyCount} <ruby> element(s) were found but only about ${rubyPct}% of kanji characters are annotated (${kanjiWithRuby}/${kanjiCount}).`,
        ),
        helpUrl: HELP_URL,
      }],
    };
  }

  const sampleText = sampleKanji.slice(0, 3).map(sample => `"${sample}"`).join(', ');
  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: DESCRIPTION,
      impact: 'moderate',
      status: 'fail',
      reason: _reason(
        'missing_ruby',
        {
          html_lang: htmlLang,
          cjk_density_pct: cjkDensityPct,
          kanji_count: kanjiCount,
          sample_text: sampleText,
        },
        sharedContext,
        `No <ruby> elements were found on this ${htmlLang} page (${cjkDensityPct}% CJK, ${kanjiCount} kanji characters). Sample text: ${sampleText}.`,
      ),
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = {
  DESCRIPTION,
  FALLBACK_DESCRIPTION,
  HELP_URL,
  MODE,
  RULE_ID,
  SC,
  run,
};
