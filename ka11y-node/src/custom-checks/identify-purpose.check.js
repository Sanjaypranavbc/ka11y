'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '1.3.6';
const RULE_ID = 'custom-identify-purpose';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/identify-purpose';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'The purpose of UI components, icons, and regions must be programmatically determinable';

function _t(ctx, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, ctx, en);
}

function _pass(ctx, reason) {
  return {
    successCriteriaId: SC,
    rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'pass', reason, helpUrl: HELP_URL }],
  };
}

// Input types that benefit from autocomplete
const AUTOCOMPLETE_INPUTS = [
  { type: /^(text|email|tel|url|search)$/, purpose: /name|email|phone|tel|address|url|search|post|zip|city|country|org|job/i },
  { type: /^password$/, purpose: /password/i },
];

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  const data = await page.evaluate(() => {
    const issues = [];

    // ── Check 1: Icon-only buttons/links must have an accessible name ──────────
    const interactives = document.querySelectorAll('button,a,[role="button"],[role="link"]');
    for (const el of interactives) {
      // Consider it icon-only if visible text is empty or just punctuation
      const visibleText = (el.textContent || '').replace(/[\s​]/g, '');
      const hasVisibleText = visibleText.length > 1 && !/^[^\w]+$/.test(visibleText);
      if (hasVisibleText) continue;

      const ariaLabel = el.getAttribute('aria-label') || '';
      const ariaLabelledBy = el.getAttribute('aria-labelledby') || '';
      const title = el.getAttribute('title') || '';
      const altText = el.querySelector('img') ? (el.querySelector('img').getAttribute('alt') || '') : '';

      if (!ariaLabel.trim() && !ariaLabelledBy.trim() && !title.trim() && !altText.trim()) {
        issues.push({
          type: 'icon-only-no-name',
          target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
          snippet: el.outerHTML.slice(0, 150),
          reason: 'Icon-only interactive element has no accessible name',
        });
      }
    }

    // ── Check 2: Personal-data inputs should have autocomplete attribute ──────
    const inputs = document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="reset"]):not([type="button"]):not([type="file"])');
    for (const input of inputs) {
      const type = (input.getAttribute('type') || 'text').toLowerCase();
      const name = (input.getAttribute('name') || input.getAttribute('id') || input.getAttribute('placeholder') || '').toLowerCase();
      const hasAutoComplete = input.hasAttribute('autocomplete');

      // Flag personal-data inputs without autocomplete
      const isPII = /name|email|phone|tel|mobile|address|street|city|zip|postal|country|org|company|job|title|password|credit|card|cvv|expir/i.test(name);
      if (isPII && !hasAutoComplete) {
        issues.push({
          type: 'missing-autocomplete',
          target: `input[name="${input.getAttribute('name') || input.getAttribute('id') || ''}"]`,
          snippet: input.outerHTML.slice(0, 150),
          reason: 'Personal-data input is missing an autocomplete attribute to identify its purpose',
        });
      }
    }

    // ── Check 3: Landmark regions should have unique accessible names if >1 same type ──
    const landmarkRoles = ['navigation', 'complementary', 'form', 'search', 'region'];
    for (const role of landmarkRoles) {
      const els = document.querySelectorAll(`[role="${role}"],` + (role === 'navigation' ? 'nav' : role === 'complementary' ? 'aside' : role === 'form' ? 'form' : role === 'search' ? '[role="search"]' : 'section'));
      if (els.length <= 1) continue;
      for (const el of els) {
        const label = el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || el.getAttribute('title') || '';
        if (!label.trim()) {
          issues.push({
            type: 'landmark-no-label',
            target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
            snippet: el.outerHTML.slice(0, 100),
            reason: `Multiple <${el.tagName.toLowerCase()}> / [role="${role}"] landmarks — each needs a unique accessible name`,
          });
        }
      }
    }

    return { issues };
  });

  if (!data.issues.length) {
    return _pass(ctx, _t(ctx,
      'UI component purpose checks passed — icon controls have names, personal inputs have autocomplete, landmarks are labelled.',
      'UI コンポーネントの目的チェックに合格しました。'));
  }

  const byType = {};
  for (const iss of data.issues) {
    byType[iss.type] = (byType[iss.type] || 0) + 1;
  }
  const summary = Object.entries(byType).map(([k, v]) => `${k}: ${v}`).join(', ');

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'moderate',
      status: 'incomplete',
      reason: _t(ctx,
        '{n} component purpose issue(s) detected ({summary}). Manual review recommended.',
        '{n} 件のコンポーネント目的の問題が検出されました（{summary}）。手動確認を推奨します。',
        { n: data.issues.length, summary }),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
