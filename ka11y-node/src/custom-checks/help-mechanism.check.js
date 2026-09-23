'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '3.3.5';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/help';
const RULE_ID = 'custom-help-mechanism';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'If a web page requires user input, context-sensitive help must be available';

function _t(ctx, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, ctx, en);
}

function _pass(ctx, reason) {
  return {
    successCriteriaId: SC,
    rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'pass', reason, helpUrl: HELP_URL }],
  };
}
function _na(ctx, reason) {
  return {
    successCriteriaId: SC,
    rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'not_applicable', reason, helpUrl: HELP_URL }],
  };
}

const HELP_KEYWORDS_RE = /\bhelp\b|faq|support|contact\s+us|how\s+to|instructions?|guide|tutorial|ヘルプ|サポート|お問い合わせ|使い方|ガイド/i;
const HELP_ARIA_RE = /help|support|faq/i;

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  const data = await page.evaluate((helpPattern, ariaPattern) => {
    const helpRe = new RegExp(helpPattern, 'i');
    const ariaRe = new RegExp(ariaPattern, 'i');

    const forms = Array.from(document.querySelectorAll('form'));
    if (!forms.length) return { formCount: 0, issues: [] };

    // Page-level help mechanisms
    const pageHelpLink = Array.from(document.querySelectorAll('a[href]')).some(a =>
      helpRe.test(a.textContent || '') || helpRe.test(a.getAttribute('aria-label') || ''));

    const pageHelpRegion = document.querySelector('[role="complementary"][aria-label]') !== null &&
      ariaRe.test(document.querySelector('[role="complementary"][aria-label]')?.getAttribute('aria-label') || '');

    // G193: help by an assistant in the page — chat / support widgets (often third-party iframes)
    const pageHelpChat = !!document.querySelector([
      'iframe[src*="intercom"]', 'iframe[src*="zendesk"]', 'iframe[src*="zopim"]', 'iframe[src*="drift"]', 'iframe[src*="tawk"]',
      'iframe[src*="crisp"]', 'iframe[src*="hubspot"]', 'iframe[src*="freshchat"]', 'iframe[src*="livechat"]', 'iframe[src*="tidio"]',
      'iframe[src*="olark"]', 'iframe[src*="salesforce"][src*="chat"]', 'iframe[title*="chat" i]', 'iframe[title*="チャット"]',
      '[id*="intercom" i]', '[class*="intercom" i]', '[id*="crisp-chatbox" i]', '[class*="tawk" i]', '[id*="hubspot-messages" i]',
      '[class*="chat-widget" i]', '[id*="chat-widget" i]', '[aria-label*="chat" i]', '[aria-label*="チャット"]',
    ].join(', '));

    // Per-form help signals
    const issues = [];
    for (const form of forms) {
      // Form-level: aria-describedby pointing to a help block, or a help link inside the form
      const formHelpLink = Array.from(form.querySelectorAll('a[href]')).some(a =>
        helpRe.test(a.textContent || ''));

      const formHelpText = Array.from(form.querySelectorAll('[id]')).some(el => {
        const id = el.id;
        const referencedBy = form.querySelector(`[aria-describedby~="${CSS.escape(id)}"]`);
        return referencedBy && helpRe.test(el.textContent || '');
      });

      // Inputs with aria-describedby hint text
      const inputsWithHints = Array.from(form.querySelectorAll('input,textarea,select')).filter(inp =>
        inp.getAttribute('aria-describedby') || inp.getAttribute('aria-details'));

      // G194: spell checking and suggestions for free-text input
      const hasSpellcheck = !!form.querySelector('textarea[spellcheck="true"], input[spellcheck="true"], [contenteditable][spellcheck="true"]');

      const hasHelpMechanism = pageHelpLink || pageHelpRegion || pageHelpChat || formHelpLink || formHelpText || inputsWithHints.length > 0 || hasSpellcheck;
      if (!hasHelpMechanism) {
        issues.push({
          target: `form${form.id ? '#' + CSS.escape(form.id) : ''}`,
          snippet: form.outerHTML.slice(0, 150),
          detail: 'Form has no detectable help mechanism (no help link, aria-describedby hints, or support contact)',
        });
      }
    }

    return { formCount: forms.length, pageHelpLink, pageHelpChat, issues };
  }, HELP_KEYWORDS_RE.source, HELP_ARIA_RE.source);

  if (!data.formCount) {
    return _na(ctx, _t(ctx, 'No forms found on this page — criterion not applicable.', 'このページにフォームはありません。'));
  }

  if (!data.issues.length) {
    return _pass(ctx, _t(ctx,
      'All {n} form(s) have a detectable help mechanism (help link, aria-describedby hints, or support contact).',
      '{n} 件のフォームすべてにヘルプメカニズムが検出されました。',
      { n: data.formCount }));
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'moderate',
      status: 'incomplete',
      reason: _t(ctx,
        '{i} of {n} form(s) have no detectable help mechanism. Manual review required.',
        '{n} 件中 {i} 件のフォームにヘルプメカニズムが見当たりません。手動確認が必要です。',
        { i: data.issues.length, n: data.formCount }),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
