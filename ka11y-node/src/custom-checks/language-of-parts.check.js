'use strict';

const {
  getKeywordList,
  getSharedRuleContext,
  renderReasonTemplate,
} = require('./sharedAssets');

const SC = '3.1.2';
const RULE_ID = 'custom-language-of-parts';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/language-of-parts';
const MODE = 'static';
const FALLBACK_DESCRIPTION =
  'Passages in a language different from the page language must be identified with a lang attribute';

// BCP47 primary language subtag: 2–3 alpha + optional subtags
const BCP47_RE = /^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{1,8})*$/;

// CJK Unicode ranges (Hiragana, Katakana, CJK unified ideographs, …)
const CJK_RE_SRC =
  '[぀-ヿ㐀-䶿一-鿿豈-﫿･-ﾟ]';

const CJK_LANGS = new Set(['ja', 'zh', 'ko', 'yue', 'cmn']);

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);

  const data = await page.evaluate(
    ({ cjkReSrc, cjkLangs }) => {
      const CJK_RE = new RegExp(cjkReSrc);
      const BCP47_PATTERN = /^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{1,8})*$/;

      // ── 1. Page language ────────────────────────────────────────────────
      const htmlEl = document.documentElement;
      const htmlLang = (htmlEl.getAttribute('lang') || '').trim().toLowerCase();
      const pageLang = htmlLang.split('-')[0] || '';
      const isCJKPage = cjkLangs.includes(pageLang);

      // ── 2. Collect elements with explicit lang= ─────────────────────────
      const invalidLangEls = [];
      const emptyLangEls = [];

      for (const el of document.querySelectorAll('[lang]')) {
        const langVal = (el.getAttribute('lang') || '').trim();
        if (!langVal) {
          const cs = window.getComputedStyle(el);
          if (cs.display === 'none' || cs.visibility === 'hidden') continue;
          emptyLangEls.push({
            tag: el.tagName.toLowerCase(),
            html: el.outerHTML.slice(0, 150),
            target: el.id
              ? [`${el.tagName.toLowerCase()}#${CSS.escape(el.id)}`]
              : [el.tagName.toLowerCase()],
          });
        } else if (!BCP47_PATTERN.test(langVal)) {
          invalidLangEls.push({
            tag: el.tagName.toLowerCase(),
            lang_value: langVal,
            html: el.outerHTML.slice(0, 150),
            target: el.id
              ? [`${el.tagName.toLowerCase()}#${CSS.escape(el.id)}`]
              : [el.tagName.toLowerCase()],
          });
        }
      }

      // ── 3. Detect unannotated CJK text on non-CJK pages ────────────────
      const unannotatedCJK = [];

      if (!isCJKPage && document.body) {
        const walker = document.createTreeWalker(
          document.body,
          NodeFilter.SHOW_ELEMENT,
          null,
          false
        );

        const seen = new WeakSet();
        let node;
        while ((node = walker.nextNode())) {
          if (seen.has(node)) continue;
          seen.add(node);

          // Skip invisible elements
          const cs = window.getComputedStyle(node);
          if (cs.display === 'none' || cs.visibility === 'hidden') continue;

          // Skip elements that already carry a lang attribute
          if (node.hasAttribute('lang')) continue;

          // Collect direct text content only (not descendants)
          const directText = Array.from(node.childNodes)
            .filter((n) => n.nodeType === Node.TEXT_NODE)
            .map((n) => n.textContent || '')
            .join('');

          if (!CJK_RE.test(directText) || directText.trim().length < 2) continue;

          // Check if any ancestor already has a CJK lang annotation
          let ancestorCovered = false;
          let anc = node.parentElement;
          while (anc && anc !== htmlEl) {
            const ancLang = (anc.getAttribute('lang') || '').toLowerCase();
            if (ancLang && cjkLangs.some((l) => ancLang.startsWith(l))) {
              ancestorCovered = true;
              break;
            }
            anc = anc.parentElement;
          }
          if (ancestorCovered) continue;

          unannotatedCJK.push({
            tag: node.tagName.toLowerCase(),
            text_sample: directText.trim().slice(0, 60),
            html: node.outerHTML.slice(0, 150),
            target: node.id
              ? [`${node.tagName.toLowerCase()}#${CSS.escape(node.id)}`]
              : [node.tagName.toLowerCase()],
          });

          // Limit scan to 20 findings max to avoid flooding the report
          if (unannotatedCJK.length >= 20) break;
        }
      }

      // ── 4. H58: same-script language changes (English inside a German/Japanese page …)
      // Stop-word profiling on text runs of ≥ 8 Latin words with no lang attribute of
      // their own. A run is reported when one language's stop words clearly dominate
      // and it is not the page language.
      const STOP = {
        en: ['the', 'and', 'of', 'to', 'in', 'is', 'that', 'for', 'with', 'you', 'this', 'are', 'on', 'be', 'it', 'as', 'was', 'not', 'have', 'from'],
        de: ['der', 'die', 'und', 'das', 'ist', 'nicht', 'mit', 'sie', 'ein', 'eine', 'den', 'von', 'für', 'auf', 'dem', 'des', 'wird', 'sind', 'zu', 'im'],
        fr: ['le', 'la', 'les', 'des', 'et', 'est', 'une', 'un', 'pour', 'dans', 'que', 'qui', 'pas', 'sur', 'avec', 'vous', 'nous', 'ce', 'du', 'au'],
        es: ['el', 'la', 'los', 'las', 'de', 'que', 'y', 'en', 'un', 'una', 'es', 'por', 'con', 'para', 'del', 'se', 'no', 'su', 'al', 'como'],
        it: ['il', 'la', 'di', 'che', 'e', 'un', 'una', 'per', 'con', 'non', 'del', 'della', 'sono', 'gli', 'le', 'si', 'al', 'da', 'nel', 'più'],
        pt: ['o', 'a', 'os', 'as', 'de', 'que', 'e', 'um', 'uma', 'para', 'com', 'não', 'do', 'da', 'em', 'se', 'por', 'na', 'no', 'mais'],
        nl: ['de', 'het', 'een', 'en', 'van', 'is', 'dat', 'niet', 'op', 'voor', 'met', 'zijn', 'je', 'dit', 'er', 'ook', 'aan', 'bij', 'als', 'maar'],
      };
      const sameScriptRuns = [];
      if (document.body && (STOP[pageLang] || isCJKPage)) {
        let n = 0;
        for (const el of document.querySelectorAll('p, li, blockquote, td, dd, h1, h2, h3, h4, figcaption')) {
          if (n++ > 1500 || sameScriptRuns.length >= 10) break;
          const owner = el.closest('[lang]');
          if (owner && owner !== htmlEl) continue;
          const cs = window.getComputedStyle(el);
          if (cs.display === 'none' || cs.visibility === 'hidden') continue;
          const words = (el.textContent || '').toLowerCase().match(/[a-zà-ÿ']+/g) || [];
          if (words.length < 8) continue;
          const ranked = Object.entries(STOP).map(([l, list]) => { const set = new Set(list); return [l, words.filter(w => set.has(w)).length]; }).sort((a, b) => b[1] - a[1]);
          const [best, bScore] = ranked[0];
          const second = ranked[1][1];
          if (best === pageLang) continue;
          if (bScore < 3 || bScore < second * 2 || bScore / words.length < 0.15) continue;
          sameScriptRuns.push({
            tag: el.tagName.toLowerCase(),
            detected: best,
            text_sample: (el.textContent || '').trim().slice(0, 60),
            html: el.outerHTML.slice(0, 150),
            target: el.id ? [`${el.tagName.toLowerCase()}#${CSS.escape(el.id)}`] : [el.tagName.toLowerCase()],
          });
        }
      }

      return { htmlLang, pageLang, emptyLangEls, invalidLangEls, unannotatedCJK, sameScriptRuns };
    },
    { cjkReSrc: CJK_RE_SRC, cjkLangs: [...CJK_LANGS] }
  );

  const { htmlLang, pageLang, emptyLangEls, invalidLangEls, unannotatedCJK } = data;
  const sameScriptRuns = Array.isArray(data.sameScriptRuns) ? data.sameScriptRuns : [];

  // ── No page language declared ─────────────────────────────────────────────
  if (!htmlLang) {
    return {
      successCriteriaId: SC,
      rules: [
        {
          ruleId: RULE_ID,
          description: FALLBACK_DESCRIPTION,
          impact: 'serious',
          status: 'fail',
          reason:
            'Page <html> element has no lang attribute. WCAG 3.1.1 requires a declared page language before 3.1.2 (Language of Parts) can be evaluated.',
          helpUrl: HELP_URL,
        },
      ],
    };
  }

  const rules = [];

  // ── Empty lang= attributes ────────────────────────────────────────────────
  if (emptyLangEls.length > 0) {
    rules.push({
      ruleId: `${RULE_ID}-empty`,
      description: 'lang attribute must not be empty',
      impact: 'serious',
      status: 'fail',
      reason: `${emptyLangEls.length} element(s) have an empty lang="" attribute. Screen readers cannot determine the language of the enclosed text.`,
      elements: emptyLangEls,
      helpUrl: HELP_URL,
    });
  }

  // ── Invalid BCP47 lang codes ──────────────────────────────────────────────
  if (invalidLangEls.length > 0) {
    rules.push({
      ruleId: `${RULE_ID}-invalid`,
      description: 'lang attribute must be a valid BCP47 language tag',
      impact: 'moderate',
      status: 'fail',
      reason: `${invalidLangEls.length} element(s) have a lang attribute that is not a valid BCP47 language tag (e.g. "en", "ja", "zh-Hant"). Screen readers may ignore or misinterpret invalid values.`,
      elements: invalidLangEls,
      helpUrl: HELP_URL,
    });
  }

  // ── Unannotated CJK text on a non-CJK page ───────────────────────────────
  if (unannotatedCJK.length > 0) {
    rules.push({
      ruleId: `${RULE_ID}-unannotated-cjk`,
      description: 'CJK text on a non-CJK page must have a lang attribute',
      impact: 'moderate',
      status: 'needs_review',
      reason: `${unannotatedCJK.length} element(s) contain CJK characters on a page declared lang="${pageLang}". Add lang="ja", lang="zh", or lang="ko" to the element or its nearest ancestor to enable correct pronunciation by screen readers.`,
      elements: unannotatedCJK,
      helpUrl: HELP_URL,
    });
  }

  // ── H58: passages in another Latin-script language without a lang attribute ──
  if (sameScriptRuns.length > 0) {
    const langs = [...new Set(sameScriptRuns.map(r => r.detected))].join(', ');
    rules.push({
      ruleId: `${RULE_ID}-same-script`,
      description: 'Passages in another language must carry a lang attribute',
      impact: 'moderate',
      status: 'needs_review',
      reason: `${sameScriptRuns.length} text passage(s) appear to be written in another language (${langs}) than the page language "${pageLang}" but have no lang attribute — screen readers will read them with the wrong pronunciation rules (H58).`,
      elements: sameScriptRuns,
      helpUrl: HELP_URL,
    });
  }

  // ── All clear ─────────────────────────────────────────────────────────────
  if (rules.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [
        {
          ruleId: RULE_ID,
          description: FALLBACK_DESCRIPTION,
          impact: null,
          status: 'pass',
          reason: `Page language is "${htmlLang}". No empty, invalid, or unannotated foreign-language text was detected.`,
          helpUrl: HELP_URL,
        },
      ],
    };
  }

  return { successCriteriaId: SC, rules };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
