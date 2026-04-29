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
  const relatedPattern = buildKeywordPattern(
    getKeywordList('multiple_ways', 'related_links_keywords', sharedContext)
  ) || 'related|recommended|similar|popular|also\\s+viewed|関連|おすすめ|関連記事';
  const pageIndexPattern = buildKeywordPattern(
    getKeywordList('multiple_ways', 'page_index_keywords', sharedContext)
  ) || 'all\\s+pages|index|a-z|directory|site\\s+index|一覧|索引';

  const data = await page.evaluate((patterns) => {
    const searchRe = new RegExp(patterns.searchPattern, 'i');
    const sitemapRe = new RegExp(patterns.sitemapPattern, 'i');
    const tocRe = new RegExp(patterns.tocPattern, 'i');
    const breadcrumbRe = new RegExp(patterns.breadcrumbPattern, 'i');
    const relatedRe = new RegExp(patterns.relatedPattern, 'i');
    const pageIndexRe = new RegExp(patterns.pageIndexPattern, 'i');
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

    const hasRelatedLinks = !!(
      Array.from(document.querySelectorAll('section, aside, nav, div, [aria-label]')).some(el => {
        const signal = [
          el.getAttribute('id') || '',
          el.getAttribute('class') || '',
          el.getAttribute('aria-label') || '',
          (el.querySelector('h1,h2,h3,h4,h5,h6') || {}).textContent || '',
        ].join(' ');
        if (!relatedRe.test(signal)) return false;
        return el.querySelectorAll('a[href]').length >= 2;
      }) ||
      Array.from(document.querySelectorAll('a[href]')).some(a => relatedRe.test(a.getAttribute('href') || ''))
    );

    const hasPageIndexList = !!(
      Array.from(document.querySelectorAll('section, nav, div, main, article')).some(el => {
        const signal = [
          el.getAttribute('id') || '',
          el.getAttribute('class') || '',
          el.getAttribute('aria-label') || '',
          (el.querySelector('h1,h2,h3,h4,h5,h6') || {}).textContent || '',
        ].join(' ');
        if (!pageIndexRe.test(signal)) return false;
        return el.querySelectorAll('a[href]').length >= 8;
      }) ||
      Array.from(document.querySelectorAll('a[href]')).some(a => pageIndexRe.test((a.textContent || '') + ' ' + (a.getAttribute('href') || '')))
    );

    return { hasSearch, hasSitemap, navCount, hasBreadcrumb, hasTableOfContents, hasRelatedLinks, hasPageIndexList };
  }, {
    searchPattern,
    sitemapPattern,
    tocPattern,
    breadcrumbPattern,
    relatedPattern,
    pageIndexPattern,
  });

  const { hasSearch, hasSitemap, navCount, hasBreadcrumb, hasTableOfContents, hasRelatedLinks, hasPageIndexList } = data;
  const ways = (hasSearch ? 1 : 0) +
               (hasSitemap ? 1 : 0) +
               (navCount >= 1 ? 1 : 0) +
               (hasBreadcrumb ? 1 : 0) +
               (hasTableOfContents ? 1 : 0) +
               (hasRelatedLinks ? 1 : 0) +
               (hasPageIndexList ? 1 : 0);

  if (ways >= 2) {
    const list = [
      hasSearch && 'search',
      hasSitemap && 'sitemap',
      navCount >= 1 && `${navCount} nav element(s)`,
      hasBreadcrumb && 'breadcrumb',
      hasTableOfContents && 'table of contents',
      hasRelatedLinks && 'related links section',
      hasPageIndexList && 'page index list',
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
    hasRelatedLinks && 'related links section',
    hasPageIndexList && 'page index list',
  ].filter(Boolean);
  const missing = [
    !hasSearch && 'search',
    !hasSitemap && 'sitemap',
    navCount < 1 && 'navigation menu',
    !hasBreadcrumb && 'breadcrumb',
    !hasTableOfContents && 'table of contents',
    !hasRelatedLinks && 'related links',
    !hasPageIndexList && 'page index list',
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
