'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '2.4.10';
const RULE_ID = 'custom-section-headings';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/section-headings';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Section headings must be used to organize content';

// Only flag sections with enough text to be considered "substantial content"
const MIN_TEXT_LENGTH = 120;

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

  const data = await page.evaluate((minTextLength) => {
    const HEADING_SEL = 'h1,h2,h3,h4,h5,h6,[role="heading"]';
    const SECTION_SEL = 'section,article,[role="region"],[role="main"],[role="complementary"]';

    function hasHeading(el) {
      return !!el.querySelector(HEADING_SEL);
    }

    function hasAriaLabel(el) {
      return el.hasAttribute('aria-label') ||
             (el.hasAttribute('aria-labelledby') && el.getAttribute('aria-labelledby').trim());
    }

    const sections = Array.from(document.querySelectorAll(SECTION_SEL));
    const totalSections = sections.length;

    if (totalSections === 0) {
      return { totalSections: 0, violations: [], notApplicable: true };
    }

    const violations = [];
    for (const el of sections) {
      // Skip non-content roles
      const role = (el.getAttribute('role') || '').toLowerCase();
      if (role === 'navigation' || role === 'banner' || role === 'contentinfo' || role === 'search') continue;

      // Skip sections with too little text to need a heading
      const textLen = (el.textContent || '').trim().length;
      if (textLen < minTextLength) continue;

      // Skip if hidden
      const cs = window.getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') continue;

      if (!hasHeading(el) && !hasAriaLabel(el)) {
        violations.push({
          target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
          snippet: el.outerHTML.slice(0, 120),
          detail: `Section contains ${textLen} characters of text but lacks a heading (h1-h6) or aria-label/aria-labelledby`,
        });
        if (violations.length >= 20) break;
      }
    }

    return { totalSections, violations, notApplicable: false };
  }, MIN_TEXT_LENGTH);

  if (data.notApplicable || data.totalSections === 0) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'not_applicable', reason: 'No section or article elements found on this page.', helpUrl: HELP_URL }],
    };
  }

  if (!data.violations.length) {
    return _pass(ctx, _t(ctx,
      '{n} section/article element(s) checked — all have a heading or aria-label to identify their content.',
      '{n} 件の section/article 要素を確認しました。すべてコンテンツを識別する見出しまたは aria-label を持っています。',
      { n: data.totalSections }));
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'moderate',
      status: 'incomplete',
      reason: _t(ctx,
        '{n} section(s) contain substantial content (≥{min} chars) but lack a heading (h1-h6) or aria-label. Add section headings to help users understand and navigate the page structure.',
        '{n} 件のセクションに十分な量のコンテンツ（{min}文字以上）がありますが、見出し（h1-h6）または aria-label がありません。',
        { n: data.violations.length, min: MIN_TEXT_LENGTH }),
      elements: data.violations,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
