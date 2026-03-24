'use strict';

const SC = '3.2.6';
const RULE_ID = 'custom-consistent-help';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/consistent-help';

const HELP_PATTERNS = /\b(help|contact\s*us|support|faq|frequently\s*asked|live\s*chat|customer\s*service|get\s*help|need\s*help|assistance|helpdesk|help\s*centre|help\s*center)\b/i;

async function run(page) {
  const data = await page.evaluate((helpPattern) => {
    const re = new RegExp(helpPattern);
    const helpLinks = [];

    // Search <a>, <button>, nav elements for help-related text or aria-label
    const candidates = Array.from(document.querySelectorAll('a, button, [role="link"], [role="button"]'));
    for (const el of candidates) {
      const text  = (el.textContent || '').trim();
      const label = el.getAttribute('aria-label') || '';
      const href  = el.getAttribute('href') || '';

      if (re.test(text) || re.test(label) || re.test(href)) {
        // Determine position: header, footer, nav, or body
        const inHeader = !!el.closest('header, [role="banner"]');
        const inFooter = !!el.closest('footer, [role="contentinfo"]');
        const inNav    = !!el.closest('nav, [role="navigation"]');
        helpLinks.push({
          text: text.slice(0, 60),
          href: href.slice(0, 80),
          inHeader,
          inFooter,
          inNav,
          html: el.outerHTML.slice(0, 150),
        });
      }
    }

    // Also check for common help widgets: chat bubbles, phone icons
    const chatWidget = !!(
      document.querySelector('[id*="chat" i], [class*="chat" i], [id*="intercom" i], [id*="zendesk" i]') ||
      document.querySelector('iframe[src*="chat"], iframe[src*="support"]')
    );

    return { helpLinks, chatWidget };
  }, HELP_PATTERNS.source);

  const { helpLinks, chatWidget } = data;

  if (helpLinks.length === 0 && !chatWidget) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Help mechanisms must appear in a consistent location across pages',
        impact: 'moderate',
        status: 'incomplete',
        reason: 'No help, contact, or support links/widgets detected on this page. If this is part of a multi-page site, ensure help mechanisms appear consistently.',
        helpUrl: HELP_URL,
      }],
    };
  }

  const locations = helpLinks.map(l => {
    if (l.inHeader) return 'header';
    if (l.inFooter) return 'footer';
    if (l.inNav) return 'nav';
    return 'body';
  });
  const uniqueLocations = [...new Set(locations)];
  const locationStr = uniqueLocations.length > 0 ? ` in: ${uniqueLocations.join(', ')}` : '';
  const chatStr = chatWidget ? ' + chat widget' : '';

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Help mechanisms must appear in a consistent location across pages',
      impact: null,
      status: 'pass',
      reason: `${helpLinks.length} help mechanism(s) detected${chatStr}${locationStr}. Verify placement is consistent across all pages of the site.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run };