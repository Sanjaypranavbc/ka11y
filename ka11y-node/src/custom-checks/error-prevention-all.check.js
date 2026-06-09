'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '3.3.6';
const RULE_ID = 'custom-error-prevention-all';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/error-prevention-all';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'For all forms, submissions must be reversible, checked for errors, or confirmed before final submission';

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

// Signals that a form has a reversibility/confirmation mechanism
function _hasConfirmSignal(form) {
  // data-confirm / data-undo attribute pattern
  if (form.hasAttribute('data-confirm') || form.hasAttribute('data-undo')) return true;
  // A confirmation step indicator (wizard steps, review screen)
  if (form.querySelector('[aria-current="step"],[data-step],[name*="confirm"],[name*="review"],[name*="preview"]')) return true;
  // A "Back" or "Edit" button inside the form
  if (Array.from(form.querySelectorAll('button,[role="button"]')).some(b => /back|edit|review|revise|cancel|undo|modify/i.test(b.textContent || b.getAttribute('aria-label') || ''))) return true;
  return false;
}

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  const data = await page.evaluate((hasConfirmSignalSrc) => {
    // Re-create hasConfirmSignal in browser context
    // eslint-disable-next-line no-new-func
    const hasConfirmSignal = new Function('form', `return (${hasConfirmSignalSrc})(form);`);

    const forms = Array.from(document.querySelectorAll('form'));
    if (!forms.length) return { formCount: 0, issues: [] };

    const issues = [];
    for (const form of forms) {
      // Skip trivial forms: search boxes, single-field newsletter signups, login forms
      const inputs = Array.from(form.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="reset"]):not([type="button"])'));
      if (inputs.length <= 1) continue;

      // Detect financial/transactional forms by keyword heuristic
      const formText = (form.textContent || '').toLowerCase();
      const isHighRisk = /purchase|checkout|order|payment|buy|confirm|submit|send|transfer|register|subscribe|enrol/i.test(formText) ||
        /credit|card|billing|invoice|price|\$|€|£|¥/i.test(formText);

      if (isHighRisk && !hasConfirmSignal(form)) {
        issues.push({
          target: `form${form.id ? '#' + CSS.escape(form.id) : ''}`,
          snippet: form.outerHTML.slice(0, 150),
          detail: 'High-risk form with no detectable confirmation, review step, or undo mechanism',
        });
      }
    }

    return { formCount: forms.length, issues };
  }, _hasConfirmSignal.toString());

  if (!data.formCount) {
    return _na(ctx, _t(ctx, 'No forms found on this page — criterion not applicable.', 'このページにフォームはありません。'));
  }

  if (!data.issues.length) {
    return _pass(ctx, _t(ctx,
      '{n} form(s) checked — all high-risk forms have a detectable confirmation or reversibility mechanism.',
      '{n} 件のフォームを確認しました。高リスクフォームすべてに確認または取り消し可能なメカニズムが検出されました。',
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
        '{i} high-risk form(s) have no detectable confirmation, review step, or undo mechanism. Manual review required.',
        '{i} 件の高リスクフォームに確認、レビュー、または取り消しのメカニズムが見当たりません。手動確認が必要です。',
        { i: data.issues.length }),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
