'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '3.2.3';
const RULE_ID = 'custom-consistent-navigation';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/consistent-navigation';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Navigation mechanisms repeated on multiple pages must appear in the same relative order';

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

  // Full cross-page verification requires crawling multiple pages and comparing
  // nav order — beyond single-URL scope. This check audits per-page structural
  // consistency signals that commonly correlate with cross-page inconsistency.
  const data = await page.evaluate(() => {
    const issues = [];

    // ── Check 1: Multiple <nav> / [role="navigation"] must have unique labels ─
    // Unlabelled duplicate nav landmarks almost always lead to cross-page inconsistency
    // because authors cannot reliably reproduce their order without naming them.
    const navEls = Array.from(document.querySelectorAll('nav,[role="navigation"]'));
    const unlabelledNavs = navEls.filter(el =>
      !el.getAttribute('aria-label') && !el.getAttribute('aria-labelledby') && !el.getAttribute('title'));

    if (navEls.length > 1 && unlabelledNavs.length > 0) {
      for (const el of unlabelledNavs) {
        issues.push({
          type: 'unlabelled-nav',
          target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
          snippet: el.outerHTML.slice(0, 150),
          detail: 'Multiple navigation regions found but this one has no aria-label — cross-page order cannot be verified programmatically',
        });
      }
    }

    // ── Check 2: Skip-nav / skip-to-main link must come first in the DOM ──────
    // If the skip link is buried mid-page, the pre-navigation link order is wrong.
    const SKIP_RE = /skip|jump\s+to|ショートカット|コンテンツへ/i;
    const skipLinks = Array.from(document.querySelectorAll('a[href^="#"]')).filter(a =>
      SKIP_RE.test(a.textContent || a.getAttribute('aria-label') || ''));

    if (skipLinks.length > 0) {
      const body = document.body;
      const allLinks = Array.from(body.querySelectorAll('a[href]'));
      const firstLinkIdx = allLinks.indexOf(allLinks[0]);
      const skipLinkIdx = allLinks.indexOf(skipLinks[0]);
      // Skip link should be among the first 5 links on the page
      if (skipLinkIdx > 5) {
        issues.push({
          type: 'skip-link-order',
          target: skipLinks[0].tagName.toLowerCase() + (skipLinks[0].id ? `#${CSS.escape(skipLinks[0].id)}` : ''),
          snippet: skipLinks[0].outerHTML.slice(0, 150),
          detail: `Skip-nav link is the ${skipLinkIdx + 1}th link in the DOM — it should be at the very start for consistent keyboard navigation order`,
        });
      }
    }

    // ── Check 3: Breadcrumb landmark position ─────────────────────────────────
    // Breadcrumbs should appear in a consistent position relative to main content.
    const breadcrumbs = document.querySelectorAll('[aria-label*="breadcrumb" i],[aria-label*="パンくず" i],nav[class*="breadcrumb" i],ol[class*="breadcrumb" i]');
    if (breadcrumbs.length > 1) {
      issues.push({
        type: 'multiple-breadcrumbs',
        target: 'multiple breadcrumb elements',
        detail: `${breadcrumbs.length} breadcrumb patterns found on a single page — verify only one is intended`,
      });
    }

    return {
      navCount: navEls.length,
      hasSkipLink: skipLinks.length > 0,
      issues,
    };
  });

  if (!data.issues.length) {
    return _pass(ctx, _t(ctx,
      'Navigation structure appears consistent on this page ({n} navigation region(s)). Multi-page cross-check is manual.',
      'このページのナビゲーション構造は一貫しているようです（{n} 件のナビゲーション領域）。複数ページの確認は手動で行ってください。',
      { n: data.navCount }));
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'moderate',
      status: 'incomplete',
      reason: _t(ctx,
        '{n} navigation consistency issue(s) detected. Full verification requires cross-page review.',
        '{n} 件のナビゲーション一貫性の問題が検出されました。完全な確認には複数ページのレビューが必要です。',
        { n: data.issues.length }),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
