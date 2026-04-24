'use strict';

const {
  buildKeywordPattern,
  getKeywordList,
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '2.4.8';
const RULE_ID = 'custom-location';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/location';

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);
  const breadcrumbPattern = buildKeywordPattern(
    getKeywordList('location', 'breadcrumb_keywords', sharedContext)
  ) || 'breadcrumb|パンくず';
  const sitemapPattern = buildKeywordPattern(
    getKeywordList('location', 'sitemap_keywords', sharedContext)
  ) || 'sitemap|site\\s*map';
  const tocPattern = buildKeywordPattern(
    getKeywordList('location', 'toc_keywords', sharedContext)
  ) || 'table\\s+of\\s+contents?|toc|目次';

  const data = await page.evaluate((patterns) => {
    const breadcrumbRe = new RegExp(patterns.breadcrumbPattern, 'i');
    const sitemapRe = new RegExp(patterns.sitemapPattern, 'i');
    const tocRe = new RegExp(patterns.tocPattern, 'i');
    // 1. Breadcrumb navigation — explicit aria-label or class patterns
    const hasBreadcrumb = !!(
      document.querySelector('[class*="breadcrumb" i]') ||
      document.querySelector('[class*="pan-kuzu" i], [class*="panku-zu" i], [id*="pan-kuzu" i], [id*="panku-zu" i]') ||
      Array.from(document.querySelectorAll('[class], [id], [aria-label]')).some(el =>
        breadcrumbRe.test(el.getAttribute('class') || '') ||
        breadcrumbRe.test(el.getAttribute('id') || '') ||
        breadcrumbRe.test(el.getAttribute('aria-label') || '')
      ) ||
      document.querySelector('[itemtype*="BreadcrumbList"]') ||
      document.querySelector('nav [aria-current="page"]') // current page in nav = location indicator
    );

    // 2. aria-current="page" anywhere in a navigational context
    const hasAriaCurrent = !!document.querySelector(
      'nav [aria-current="page"], [role="navigation"] [aria-current="page"]'
    );

    // 3. Active/selected nav item (common visual pattern)
    const hasActiveNavItem = !!(
      document.querySelector('nav .active, nav [aria-selected="true"]') ||
      document.querySelector('[role="navigation"] .active, [role="navigation"] [aria-selected="true"]')
    );

    // 4. Sitemap or location landmark (rare but valid)
    const hasSiteMap = !!(
      document.querySelector('a[href*="sitemap" i], a[href*="site-map" i], a[href*="site map" i]') ||
      Array.from(document.querySelectorAll('a, [aria-label]')).some(el =>
        sitemapRe.test(el.textContent || '') ||
        sitemapRe.test(el.getAttribute('href') || '') ||
        sitemapRe.test(el.getAttribute('aria-label') || '')
      )
    );

    // 4b. Table-of-contents style location aid
    const hasTableOfContents = !!(
      document.querySelector('[id*="toc" i], [class*="toc" i]') ||
      Array.from(document.querySelectorAll('[class], [id], [aria-label], a[href]')).some(el =>
        tocRe.test(el.getAttribute('class') || '') ||
        tocRe.test(el.getAttribute('id') || '') ||
        tocRe.test(el.getAttribute('aria-label') || '') ||
        tocRe.test(el.textContent || '')
      )
    );

    // 5. aria-current="step" — indicates current step in a multi-step process
    const hasAriaCurrentStep = !!document.querySelector('[aria-current="step"]');

    // 6. JSON-LD BreadcrumbList structured data
    let hasJsonLdBreadcrumb = false;
    for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
      if (/"BreadcrumbList"/.test(script.textContent || '')) {
        hasJsonLdBreadcrumb = true;
        break;
      }
    }

    const hasLocationIndicator = hasBreadcrumb || hasAriaCurrent || hasActiveNavItem || hasSiteMap || hasTableOfContents || hasAriaCurrentStep || hasJsonLdBreadcrumb;

    return {
      hasBreadcrumb,
      hasAriaCurrent,
      hasActiveNavItem,
      hasSiteMap,
      hasTableOfContents,
      hasAriaCurrentStep,
      hasJsonLdBreadcrumb,
      hasLocationIndicator,
    };
  }, { breadcrumbPattern, sitemapPattern, tocPattern });

  if (data.hasLocationIndicator) {
    const mechanisms = [
      data.hasBreadcrumb && 'breadcrumb navigation',
      data.hasAriaCurrent && 'aria-current="page"',
      data.hasActiveNavItem && 'active navigation item',
      data.hasSiteMap && 'sitemap link',
      data.hasTableOfContents && 'table of contents',
      data.hasAriaCurrentStep && 'aria-current="step"',
      data.hasJsonLdBreadcrumb && 'JSON-LD BreadcrumbList',
    ].filter(Boolean).join(', ');

    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Users must be able to determine their location within a set of web pages',
        impact: null,
        status: 'pass',
        reason: _t(sharedContext, 'Location indicator(s) detected: {mechanisms}.', '現在位置を示す手段が検出されました: {mechanisms}。', { mechanisms }),
        helpUrl: HELP_URL,
      }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Users must be able to determine their location within a set of web pages',
      impact: 'moderate',
      status: 'incomplete',
      reason: _t(sharedContext, 'No location indicator detected (no breadcrumb, no aria-current="page" in navigation, no active nav item, no sitemap link, no table of contents). If this is a multi-page site, provide a breadcrumb or highlight the current page in navigation.', '現在位置を示す手段は検出されませんでした（パンくず、ナビゲーション内の aria-current="page"、アクティブなナビ項目、サイトマップリンク、目次なし）。複数ページのサイトであれば、パンくずを提供するか、ナビゲーションで現在ページを明示してください。'),
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
