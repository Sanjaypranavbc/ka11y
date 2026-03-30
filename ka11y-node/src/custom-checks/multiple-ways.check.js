'use strict';

const SC = '2.4.5';
const RULE_ID = 'custom-multiple-ways';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/multiple-ways';

async function run(page) {
  const data = await page.evaluate(() => {
    const hasSearch = !!(
      document.querySelector('input[type="search"]') ||
      document.querySelector('[role="search"]') ||
      document.querySelector('[aria-label*="search" i]') ||
      document.querySelector('[aria-label*="検索" i]') ||
      document.querySelector('[placeholder*="search" i]') ||
      document.querySelector('[placeholder*="検索" i]') ||
      Array.from(document.querySelectorAll('form')).some(f =>
        /search|検索/i.test(f.action || '') || /search|検索/i.test(f.getAttribute('aria-label') || '')
      )
    );

    const hasSitemap = !!(
      document.querySelector('a[href*="sitemap"], a[href*="site-map"], a[href*="サイトマップ"]') ||
      Array.from(document.querySelectorAll('a')).some(a =>
        /site.?map|サイトマップ/i.test(a.textContent || '') || /site.?map|サイトマップ/i.test(a.href || '')
      )
    );

    const navEls = document.querySelectorAll('nav, [role="navigation"]');
    const navCount = navEls.length;

    // Additional navigation mechanisms per WCAG 2.4.5 technique list
    const hasBreadcrumb = !!(
      document.querySelector('[aria-label*="breadcrumb" i], [aria-label*="パンくず" i], [class*="breadcrumb" i], [id*="breadcrumb" i], [class*="パンくず" i], [id*="パンくず" i]') ||
      document.querySelector('nav[aria-label*="breadcrumb" i]') ||
      // Schema.org breadcrumb structured data
      document.querySelector('[itemtype*="BreadcrumbList"]')
    );

    const hasTableOfContents = !!(
      document.querySelector('[aria-label*="table of contents" i], [aria-label*="目次" i], [id*="toc" i], [class*="toc" i], [id*="目次" i], [class*="目次" i]') ||
      Array.from(document.querySelectorAll('a')).some(a =>
        /table\s+of\s+content|目次/i.test(a.textContent || '')
      )
    );

    return { hasSearch, hasSitemap, navCount, hasBreadcrumb, hasTableOfContents };
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
      rules: [{ ruleId: RULE_ID, description: 'More than one way must be available to locate a page', impact: null, status: 'pass', reason: `Multiple navigation mechanisms found: ${list.join(', ')}.`, helpUrl: HELP_URL }],
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
      reason: `Only ${ways} navigation mechanism(s) detected${found.length ? ': ' + found.join(', ') : ''}. At least 2 are required — consider adding: ${missing.slice(0, 3).join(', ')}.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
