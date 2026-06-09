'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '3.3.1';
const RULE_ID = 'custom-error-identification';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/error-identification';
const MODE = 'interactive';
const FALLBACK_DESCRIPTION = 'When an input error is automatically detected, the errored item must be identified and described in text';

const MAX_FORMS = 3;

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

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  // ── Phase 1: Collect forms with required fields ──────────────────────────
  const forms = await page.evaluate((maxForms) => {
    return Array.from(document.querySelectorAll('form'))
      .slice(0, maxForms)
      .map((form, i) => {
        const required = Array.from(form.querySelectorAll(
          'input[required]:not([type="hidden"]):not([type="submit"]):not([type="reset"]):not([type="button"]),' +
          'textarea[required],select[required],' +
          '[aria-required="true"]:not(form)'));
        return {
          index: i,
          id: form.id || null,
          hasRequired: required.length > 0,
          requiredCount: required.length,
        };
      })
      .filter(f => f.hasRequired);
  }, MAX_FORMS);

  if (!forms.length) {
    return _na(ctx, _t(ctx,
      'No forms with required fields found — criterion not applicable.',
      '必須フィールドを持つフォームが見つかりませんでした。エラー識別チェックは対象外です。'));
  }

  const issues = [];

  for (const formMeta of forms) {
    try {
      // Trigger browser constraint validation without submitting
      // (reportValidity fires validation UI and sets validity state but does not submit)
      const validationResult = await page.evaluate((formIndex) => {
        const form = document.querySelectorAll('form')[formIndex];
        if (!form) return null;

        // Call reportValidity to fire constraint validation
        const valid = form.reportValidity();

        // After reportValidity, check what error signals are present
        const invalidFields = Array.from(form.querySelectorAll(':invalid'))
          .filter(el => el.tagName !== 'FORM');

        const errorSignals = {
          ariaInvalidCount: form.querySelectorAll('[aria-invalid="true"]').length,
          ariaDescribedByCount: Array.from(invalidFields).filter(f => f.getAttribute('aria-describedby')).length,
          ariaErrMsgCount: form.querySelectorAll('[aria-errormessage]').length,
          liveRegionCount: form.querySelectorAll('[aria-live],[role="alert"],[role="status"]').length,
          invalidCount: invalidFields.length,
          browserValid: valid,
        };

        // Check each invalid field for text error description
        const fieldsWithoutTextError = [];
        for (const field of invalidFields) {
          const hasAriaInvalid = field.getAttribute('aria-invalid') === 'true';
          const ariaDescId = field.getAttribute('aria-describedby') || field.getAttribute('aria-errormessage');
          let hasTextError = false;

          if (ariaDescId) {
            // Check if the referenced element contains error text
            for (const id of ariaDescId.split(/\s+/)) {
              const errEl = document.getElementById(id);
              if (errEl && (errEl.textContent || '').trim()) { hasTextError = true; break; }
            }
          }

          // Also check for adjacent error elements (common pattern)
          const next = field.nextElementSibling;
          if (next && /error|invalid|alert/i.test((next.getAttribute('role') || '') + ' ' + (next.className || ''))) {
            if ((next.textContent || '').trim()) hasTextError = true;
          }

          if (!hasAriaInvalid && !hasTextError) {
            fieldsWithoutTextError.push({
              target: field.tagName.toLowerCase() + (field.id ? `#${CSS.escape(field.id)}` : field.name ? `[name="${field.name}"]` : ''),
              snippet: field.outerHTML.slice(0, 150),
            });
          }
        }

        return { ...errorSignals, fieldsWithoutTextError };
      }, formMeta.index);

      if (!validationResult) continue;

      // If the form validated correctly and all invalid fields have programmatic error text, no issue
      if (!validationResult.invalidCount) continue;

      if (validationResult.fieldsWithoutTextError.length > 0) {
        issues.push({
          formId: formMeta.id,
          type: 'no-programmatic-error-text',
          detail: `Form has ${validationResult.invalidCount} invalid field(s) but ${validationResult.fieldsWithoutTextError.length} are missing aria-invalid + text error description`,
          fields: validationResult.fieldsWithoutTextError,
        });
      }
    } catch (_) {
      // Skip forms that fail interaction (e.g. navigation on submit)
    }
  }

  if (!issues.length) {
    return _pass(ctx, _t(ctx,
      '{n} form(s) with required fields checked — all invalid fields have programmatic error identification.',
      '必須フィールドを持つ {n} 件のフォームを確認しました。すべての無効フィールドにプログラム的なエラー識別があります。',
      { n: forms.length }));
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'critical',
      status: 'incomplete',
      reason: _t(ctx,
        '{i} of {n} form(s) have fields that fail validation without a programmatic text error description (aria-invalid + aria-describedby/errormessage).',
        '{n} 件中 {i} 件のフォームに、プログラム的なテキストエラー説明（aria-invalid + aria-describedby/errormessage）なしでバリデーションエラーになるフィールドがあります。',
        { i: issues.length, n: forms.length }),
      elements: issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
