'use strict';

const {
  buildKeywordPattern,
  getKeywordList,
  getSharedRuleContext,
  renderReasonTemplate,
} = require('./sharedAssets');

const SC = '2.4.5';
const RULE_ID = 'custom-multiple-ways';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/multiple-ways';

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);
  const searchPattern = buildKeywordPattern(
    getKeywordList('multiple_ways', 'search_keywords', sharedContext)
  ) || 'search';
  const sitemapPattern = buildKeywordPattern(
    getKeywordList('multiple_ways', 'sitemap_keywords', sharedContext)
  ) || 'sitemap|site\\s*map';
  const tocPattern = buildKeywordPattern(
    getKeywordList('multiple_ways', 'toc_keywords', sharedContext)
  ) || 'table\\s+of\\s+contents?';
  const breadcrumbPattern = buildKeywordPattern(
    getKeywordList('multiple_ways', 'breadcrumb_keywords', sharedContext)
  ) || 'breadcrumb';

  const data = await page.evaluate((patterns) => {
    const searchRe = new RegExp(patterns.searchPattern, 'i');
    const sitemapRe = new RegExp(patterns.sitemapPattern, 'i');
    const tocRe = new RegExp(patterns.tocPattern, 'i');
    const breadcrumbRe = new RegExp(patterns.breadcrumbPattern, 'i');
    const hasSearch = !!(
      document.querySelector('input[type="search"]') ||
      document.querySelector('[role="search"]') ||
      Array.from(document.querySelectorAll('[aria-label]')).some(el => searchRe.test(el.getAttribute('aria-label') || '')) ||
      Array.from(document.querySelectorAll('[placeholder]')).some(el => searchRe.test(el.getAttribute('placeholder') || '')) ||
      Array.from(document.querySelectorAll('form')).some(f =>
        searchRe.test(f.action || '') || searchRe.test(f.getAttribute('aria-label') || '')
      )
    );

    const hasSitemap = !!(
      document.querySelector('a[href*="sitemap"], a[href*="site-map"], a[href*="site map"]') ||
      Array.from(document.querySelectorAll('a')).some(a =>
        sitemapRe.test(a.textContent || '') || sitemapRe.test(a.href || '')
      )
    );

    const navEls = document.querySelectorAll('nav, [role="navigation"]');
    const navCount = navEls.length;

    // Additional navigation mechanisms per WCAG 2.4.5 technique list
    const hasBreadcrumb = !!(
      Array.from(document.querySelectorAll('[class], [id], [aria-label]')).some(el =>
        breadcrumbRe.test(el.getAttribute('class') || '') ||
        breadcrumbRe.test(el.getAttribute('id') || '') ||
        breadcrumbRe.test(el.getAttribute('aria-label') || '')
      ) ||
      Array.from(document.querySelectorAll('[aria-label]')).some(el => breadcrumbRe.test(el.getAttribute('aria-label') || '')) ||
      Array.from(document.querySelectorAll('nav[aria-label], [role="navigation"][aria-label]')).some(el =>
        breadcrumbRe.test(el.getAttribute('aria-label') || '')
      ) ||
      // Schema.org breadcrumb structured data
      document.querySelector('[itemtype*="BreadcrumbList"]')
    );

    const hasTableOfContents = !!(
      document.querySelector('[id*="toc" i], [class*="toc" i]') ||
      Array.from(document.querySelectorAll('[class], [id], [aria-label]')).some(el =>
        tocRe.test(el.getAttribute('class') || '') ||
        tocRe.test(el.getAttribute('id') || '') ||
        tocRe.test(el.getAttribute('aria-label') || '')
      ) ||
      Array.from(document.querySelectorAll('[aria-label]')).some(el => tocRe.test(el.getAttribute('aria-label') || '')) ||
      Array.from(document.querySelectorAll('a')).some(a =>
        tocRe.test(a.textContent || '')
      )
    );

    return { hasSearch, hasSitemap, navCount, hasBreadcrumb, hasTableOfContents };
  }, {
    searchPattern,
    sitemapPattern,
    tocPattern,
    breadcrumbPattern,
  });

  const { hasSearch, hasSitemap, navCount, hasBreadcrumb, hasTableOfContents } = data;
  const ways = (hasSearch ? 1 : 0) +
               (hasSitemap ? 1 : 0) +
               (navCount >= 1 ? 1 : 0) +
               (hasBreadcrumb ? 1 : 0) +
               (hasTableOfContents ? 1 : 0);

  if (ways >= 2) {
    const list = [
      hasSearch && 'search',
      hasSitemap && 'sitemap',
      navCount >= 1 && `${navCount} nav element(s)`,
      hasBreadcrumb && 'breadcrumb',
      hasTableOfContents && 'table of contents',
    ].filter(Boolean);
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'More than one way must be available to locate a page',
        impact: null,
        status: 'pass',
        reason: renderReasonTemplate(
          'multiple_ways',
          'pass',
          { found_list: list.join(', ') },
          sharedContext,
          `Multiple navigation mechanisms found: ${list.join(', ')}.`,
        ),
        helpUrl: HELP_URL,
      }],
    };
  }

  const found = [
    hasSearch && 'search',
    hasSitemap && 'sitemap',
    navCount >= 1 && `${navCount} nav element(s)`,
    hasBreadcrumb && 'breadcrumb',
    hasTableOfContents && 'table of contents',
  ].filter(Boolean);
  const missing = [
    !hasSearch && 'search',
    !hasSitemap && 'sitemap',
    navCount < 1 && 'navigation menu',
    !hasBreadcrumb && 'breadcrumb',
    !hasTableOfContents && 'table of contents',
  ].filter(Boolean);

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'More than one way must be available to locate a page',
      impact: 'moderate',
      status: 'incomplete',
      reason: renderReasonTemplate(
        'multiple_ways',
        'insufficient',
        {
          ways,
          found_suffix: found.length ? `: ${found.join(', ')}` : '',
          missing_list: missing.slice(0, 3).join(', '),
        },
        sharedContext,
        `Only ${ways} navigation mechanism(s) detected${found.length ? ': ' + found.join(', ') : ''}. At least 2 are required — consider adding: ${missing.slice(0, 3).join(', ')}.`,
      ),
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
