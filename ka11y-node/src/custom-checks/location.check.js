'use strict';

const SC = '2.4.8';
const RULE_ID = 'custom-location';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/location';

async function run(page) {
  const data = await page.evaluate(() => {
    // 1. Breadcrumb navigation — explicit aria-label or class patterns
    const hasBreadcrumb = !!(
      document.querySelector('[aria-label*="breadcrumb" i]') ||
      document.querySelector('[aria-label*="パンくず" i]') ||
      document.querySelector('[class*="breadcrumb" i]') ||
      document.querySelector('[class*="パンくず" i], [id*="パンくず" i], [class*="pan-kuzu" i], [class*="panku-zu" i], [id*="pan-kuzu" i], [id*="panku-zu" i]') ||
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
      document.querySelector('a[href*="sitemap" i], a[href*="site-map" i], a[href*="サイトマップ" i]') ||
      document.querySelector('[aria-label*="site map" i], [aria-label*="sitemap" i], [aria-label*="サイトマップ" i]')
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

    const hasLocationIndicator = hasBreadcrumb || hasAriaCurrent || hasActiveNavItem || hasSiteMap || hasAriaCurrentStep || hasJsonLdBreadcrumb;

    return {
      hasBreadcrumb,
      hasAriaCurrent,
      hasActiveNavItem,
      hasSiteMap,
      hasAriaCurrentStep,
      hasJsonLdBreadcrumb,
      hasLocationIndicator,
    };
  });

  if (data.hasLocationIndicator) {
    const mechanisms = [
      data.hasBreadcrumb && 'breadcrumb navigation',
      data.hasAriaCurrent && 'aria-current="page"',
      data.hasActiveNavItem && 'active navigation item',
      data.hasSiteMap && 'sitemap link',
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
        reason: `Location indicator(s) detected: ${mechanisms}.`,
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
      reason: 'No location indicator detected (no breadcrumb, no aria-current="page" in navigation, no active nav item, no sitemap link). If this is a multi-page site, provide a breadcrumb or highlight the current page in navigation.',
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
