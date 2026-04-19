'use strict';

const {
  buildKeywordPattern,
  getKeywordList,
  getSharedRuleContext,
  renderReasonTemplate,
} = require('./sharedAssets');

const SC = '3.2.6';
const RULE_ID = 'custom-consistent-help';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/consistent-help';

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);
  const helpPattern = buildKeywordPattern(
    getKeywordList('consistent_help', 'help_keywords', sharedContext)
  ) || 'help|support|contact';
  const chatPattern = buildKeywordPattern(
    getKeywordList('consistent_help', 'chat_keywords', sharedContext)
  ) || 'chat';

  const data = await page.evaluate((patterns) => {
    const re = new RegExp(patterns.helpPattern, 'i');
    const chatRe = new RegExp(patterns.chatPattern, 'i');
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
      document.querySelector('iframe[src*="chat"], iframe[src*="support"]') ||
      Array.from(document.querySelectorAll('[data-testid], [aria-label]')).some(el =>
        chatRe.test(el.getAttribute('data-testid') || '') || chatRe.test(el.getAttribute('aria-label') || '')
      )
    );

    // Known chatbot platform selectors (including JP-common LINE and SmartHR widgets)
    const chatbotSelectors = [
      '#intercom-container',
      '#drift-widget',
      '#zendesk-widget',
      '[id*="helpscout"]',
      '.crisp-client',
      '[id*="tawk"]',
      '[class*="hubspot-chat"]',
      // Japanese-specific chat/support widgets
      '#line-chat-widget',
      '[class*="line-chat" i]',
      '[id*="smarthr-help" i]',
      '[class*="smarthr-help" i]',
      '[id*="tayori" i]',
      '[class*="tayori" i]',
    ];
    const hasChatbot = chatbotSelectors.some(s => !!document.querySelector(s));

    // Phone / email contact mechanisms count as human contact mechanisms
    const hasPhoneLink = !!(
      document.querySelector('a[href^="tel:"]') ||
      Array.from(document.querySelectorAll('a')).some(a =>
        /\+?\d[\d\s\-().]{7,}\d/.test(a.textContent || '')
      )
    );
    const hasEmailLink = !!(
      document.querySelector('a[href^="mailto:"]')
    );

    return { helpLinks, chatWidget, hasChatbot, hasPhoneLink, hasEmailLink };
  }, { helpPattern, chatPattern });

  const { helpLinks, chatWidget, hasChatbot, hasPhoneLink, hasEmailLink } = data;
  const hasAnyHelpMechanism = helpLinks.length > 0 || chatWidget || hasChatbot || hasPhoneLink || hasEmailLink;

  if (!hasAnyHelpMechanism) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Help mechanisms must appear in a consistent location across pages',
        impact: 'moderate',
        status: 'incomplete',
        reason: renderReasonTemplate(
          'consistent_help',
          'missing_help',
          {},
          sharedContext,
          'No help, contact, or support links/widgets detected on this page. If this is part of a multi-page site, ensure help mechanisms appear consistently.',
        ),
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
  const extras = [
    chatWidget && 'chat widget',
    hasChatbot && 'chatbot platform',
    hasPhoneLink && 'phone link',
    hasEmailLink && 'email link',
  ].filter(Boolean);
  const extrasStr = extras.length > 0 ? ` + ${extras.join(', ')}` : '';

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Help mechanisms must appear in a consistent location across pages',
      impact: null,
      status: 'pass',
      reason: renderReasonTemplate(
        'consistent_help',
        'pass',
        {
          help_link_count: helpLinks.length,
          extras_suffix: extrasStr,
          location_suffix: locationStr,
        },
        sharedContext,
        `${helpLinks.length} help link(s)${extrasStr} detected${locationStr}. Verify placement is consistent across all pages of the site.`,
      ),
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
