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
      document.querySelector('[placeholder*="search" i]') ||
      Array.from(document.querySelectorAll('form')).some(f =>
        /search/i.test(f.action || '') || /search/i.test(f.getAttribute('aria-label') || '')
      )
    );

    const hasSitemap = !!(
      document.querySelector('a[href*="sitemap"]') ||
      Array.from(document.querySelectorAll('a')).some(a =>
        /site.?map/i.test(a.textContent || '') || /site.?map/i.test(a.href || '')
      )
    );

    const navEls = document.querySelectorAll('nav, [role="navigation"]');
    const navCount = navEls.length;

    return { hasSearch, hasSitemap, navCount };
  });

  const { hasSearch, hasSitemap, navCount } = data;
  const ways = (hasSearch ? 1 : 0) + (hasSitemap ? 1 : 0) + (navCount >= 1 ? 1 : 0);

  if (ways >= 2) {
    const list = [hasSearch && 'search', hasSitemap && 'sitemap', navCount >= 1 && `${navCount} nav element(s)`].filter(Boolean);
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: 'More than one way must be available to locate a page', impact: null, status: 'pass', reason: `Multiple navigation mechanisms found: ${list.join(', ')}.`, helpUrl: HELP_URL }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'More than one way must be available to locate a page',
      impact: 'moderate',
      status: 'incomplete',
      reason: `Only ${ways} navigation mechanism(s) detected (search: ${hasSearch}, sitemap: ${hasSitemap}, nav: ${navCount}). Provide at least two of: site search, sitemap, navigation menu.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
