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
  const notes = [];

  // SCR18: alert()-based validation surfaces as a browser dialog — capture and dismiss it.
  const alerts = [];
  const onDialog = async (d) => { try { alerts.push(String(d.message ? d.message() : '')); await d.dismiss(); } catch (_) { /* ignore */ } };
  const canListen = typeof page.on === 'function' && typeof page.off === 'function';
  if (canListen) page.on('dialog', onDialog);

  try {
  for (const formMeta of forms) {
    try {
      // Trigger browser constraint validation without submitting
      // (reportValidity fires validation UI and sets validity state but does not submit)
      const validationResult = await page.evaluate(async (formIndex) => {
        const form = document.querySelectorAll('form')[formIndex];
        if (!form) return null;

        // Call reportValidity to fire constraint validation
        const valid = form.reportValidity();

        // After reportValidity, check what error signals are present
        const invalidFields = Array.from(form.querySelectorAll(':invalid'))
          .filter(el => el.tagName !== 'FORM');

        // G83: many sites validate on blur/change rather than on submit — fire those events
        // on the invalid fields so custom validation renders its messages, then wait a beat.
        for (const f of invalidFields.slice(0, 20)) {
          try {
            f.dispatchEvent(new Event('input', { bubbles: true }));
            f.dispatchEvent(new Event('change', { bubbles: true }));
            f.dispatchEvent(new FocusEvent('blur', { bubbles: false }));
            f.dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
          } catch (_) { /* ignore */ }
        }
        await new Promise(r => setTimeout(r, 250));

        const visibleText = (el) => { const cs = window.getComputedStyle(el); return cs.display !== 'none' && cs.visibility !== 'hidden' ? (el.textContent || '').trim() : ''; };
        // ARIA18: an alertdialog announcing the errors
        const alertDialog = Array.from(document.querySelectorAll('[role="alertdialog"]')).find(d => visibleText(d));
        // G139: an error summary whose links jump to the fields
        const summaryLinks = Array.from(document.querySelectorAll('[role="alert"] a[href^="#"], [class*="error-summary" i] a[href^="#"], [class*="errorsummary" i] a[href^="#"], [id*="error-summary" i] a[href^="#"], [class*="validation-summary" i] a[href^="#"]'))
          .filter(a => { try { const t = document.getElementById(decodeURIComponent(a.getAttribute('href').slice(1))); return !!t && (t.matches('input, select, textarea') || !!t.querySelector('input, select, textarea')); } catch (_) { return false; } });
        const focusOnFirstError = invalidFields.length > 0 && document.activeElement === invalidFields[0];
        // G199: a status region for success/failure feedback
        const statusRegion = !!form.querySelector('[role="status"], [aria-live="polite"], [aria-live="assertive"], output') || !!document.querySelector('[role="status"], form ~ [aria-live]');

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
          // Error text rendered inside the field's wrapper (label/div) after blur validation
          if (!hasTextError) {
            const wrap = field.closest('.form-group, .field, .form-row, .input-group, .form-item, [class*="field" i], label, li, p, div');
            const errEl = wrap && wrap !== form ? wrap.querySelector('[class*="error" i], [class*="invalid" i], [role="alert"], .help-block, [class*="message" i]') : null;
            if (errEl && visibleText(errEl)) hasTextError = true;
          }

          if (!hasAriaInvalid && !hasTextError) {
            fieldsWithoutTextError.push({
              target: field.tagName.toLowerCase() + (field.id ? `#${CSS.escape(field.id)}` : field.name ? `[name="${field.name}"]` : ''),
              snippet: field.outerHTML.slice(0, 150),
            });
          }
        }

        // G83: visible error messages that no field references (aria-describedby/aria-errormessage)
        // and that do not sit next to a field — screen reader users cannot connect them.
        const referenced = new Set();
        for (const f of form.querySelectorAll('[aria-describedby], [aria-errormessage]')) {
          for (const id of ((f.getAttribute('aria-describedby') || '') + ' ' + (f.getAttribute('aria-errormessage') || '')).split(/\s+/).filter(Boolean)) referenced.add(id);
        }
        const unlinkedErrors = [];
        for (const el of document.querySelectorAll('[class*="error" i], [class*="invalid" i], [role="alert"], [aria-live="assertive"]')) {
          const txt = visibleText(el);
          if (!txt || txt.length > 200 || el.matches('input, select, textarea, label, form, fieldset, li')) continue;
          if (el.id && referenced.has(el.id)) continue;
          if (el.querySelector('input, select, textarea, a[href^="#"]')) continue;
          const prev = el.previousElementSibling, nextEl = el.nextElementSibling;
          if ((prev && prev.matches('input, select, textarea')) || (nextEl && nextEl.matches('input, select, textarea'))) continue;
          if (el.closest('[role="alert"] , [class*="error-summary" i], [class*="validation-summary" i]') && summaryLinks.length) continue;
          if (!form.contains(el) && !(el.compareDocumentPosition(form) & Node.DOCUMENT_POSITION_FOLLOWING)) continue;
          unlinkedErrors.push({ target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''), snippet: el.outerHTML.slice(0, 150), text: txt.slice(0, 80) });
          if (unlinkedErrors.length >= 8) break;
        }

        // G84 / G85: probe one constrained field with an invalid value and read the error text.
        let formatProbe = null;
        const probeField = Array.from(form.querySelectorAll('input[type="email"], input[type="url"], input[type="number"], input[type="tel"], input[pattern]')).find(f => !f.disabled && !f.readOnly);
        if (probeField) {
          const original = probeField.value;
          const bad = probeField.type === 'email' ? 'not-an-email' : probeField.type === 'url' ? 'not a url' : probeField.type === 'number' ? 'abc' : 'x';
          try {
            probeField.value = bad;
            probeField.dispatchEvent(new Event('input', { bubbles: true }));
            probeField.dispatchEvent(new Event('change', { bubbles: true }));
            probeField.dispatchEvent(new FocusEvent('blur', { bubbles: false }));
            probeField.dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
            await new Promise(r => setTimeout(r, 250));
            let errText = '';
            for (const id of ((probeField.getAttribute('aria-describedby') || '') + ' ' + (probeField.getAttribute('aria-errormessage') || '')).split(/\s+/).filter(Boolean)) { const n = document.getElementById(id); if (n) errText += ' ' + visibleText(n); }
            const wrap = probeField.closest('.form-group, .field, .form-row, .input-group, .form-item, [class*="field" i], label, li, p, div');
            const errEl = wrap && wrap !== form ? wrap.querySelector('[class*="error" i], [class*="invalid" i], [role="alert"], .help-block') : null;
            if (errEl) errText += ' ' + visibleText(errEl);
            errText = errText.trim();
            const FORMAT_RE = /format|valid|must|should|example|e\.g\.|such as|@|digits?|numbers? only|characters|between|at least|at most|yyyy|dd|mm|形式|有効|正しい|例|半角|数字|文字|以上|以下|@/i;
            formatProbe = { type: probeField.type || 'pattern', hasError: !!errText, descriptive: FORMAT_RE.test(errText), text: errText.slice(0, 100), target: probeField.tagName.toLowerCase() + (probeField.id ? `#${CSS.escape(probeField.id)}` : probeField.name ? `[name="${probeField.name}"]` : '') };
          } finally {
            probeField.value = original;
            probeField.dispatchEvent(new Event('input', { bubbles: true }));
            probeField.dispatchEvent(new Event('change', { bubbles: true }));
          }
        }

        return { ...errorSignals, fieldsWithoutTextError, alertDialog: !!alertDialog, summaryLinks: summaryLinks.length, focusOnFirstError, statusRegion, unlinkedErrors, formatProbe };
      }, formMeta.index);

      if (!validationResult) continue;

      if (validationResult.alertDialog) notes.push('errors announced with role="alertdialog" (ARIA18)');
      if (validationResult.summaryLinks) notes.push(`error summary with ${validationResult.summaryLinks} link(s) to the fields (G139)`);
      if (validationResult.focusOnFirstError) notes.push('focus moved to the first invalid field (G139)');
      if (validationResult.statusRegion) notes.push('status/live region available for success feedback (G199)');

      if (validationResult.formatProbe) {
        const fp = validationResult.formatProbe;
        if (!fp.hasError) issues.push({ formId: formMeta.id, type: 'no-client-error-for-invalid-format', detail: `Entering an invalid ${fp.type} value produced no client-side error text — if validation is server-side, verify the error identifies the field and the expected format (G84/G85)`, fields: [{ target: fp.target }] });
        else if (!fp.descriptive) issues.push({ formId: formMeta.id, type: 'format-error-not-descriptive', detail: `Error for an invalid ${fp.type} value ("${fp.text}") does not describe the expected format or allowed values (G84/G85)`, fields: [{ target: fp.target }] });
      }

      if (validationResult.unlinkedErrors && validationResult.unlinkedErrors.length) {
        issues.push({
          formId: formMeta.id,
          type: 'error-text-not-associated',
          detail: `${validationResult.unlinkedErrors.length} visible error message(s) are not associated with any field (aria-describedby/aria-errormessage) nor adjacent to one (G83)`,
          fields: validationResult.unlinkedErrors,
        });
      }

      // If the form validated correctly and all invalid fields have programmatic error text, no issue
      if (!validationResult.invalidCount) continue;

      if (validationResult.fieldsWithoutTextError.length > 0) {
        // An alert() dialog (SCR18) does identify the error in text, but is a poor experience — downgrade to advisory.
        issues.push({
          formId: formMeta.id,
          type: alerts.length ? 'alert-dialog-validation' : 'no-programmatic-error-text',
          detail: alerts.length
            ? `Validation errors are reported with a JavaScript alert() ("${alerts[0].slice(0, 80)}") instead of text next to the ${validationResult.fieldsWithoutTextError.length} invalid field(s) — acceptable under SCR18 but hard to use; prefer inline messages`
            : `Form has ${validationResult.invalidCount} invalid field(s) but ${validationResult.fieldsWithoutTextError.length} are missing aria-invalid + text error description`,
          fields: validationResult.fieldsWithoutTextError,
        });
      }
    } catch (_) {
      // Skip forms that fail interaction (e.g. navigation on submit)
    }
  }
  } finally {
    if (canListen) page.off('dialog', onDialog);
  }

  const noteText = notes.length ? ` (${[...new Set(notes)].join('; ')})` : '';

  if (!issues.length) {
    return _pass(ctx, _t(ctx,
      '{n} form(s) with required fields checked — all invalid fields have programmatic error identification{notes}.',
      '必須フィールドを持つ {n} 件のフォームを確認しました。すべての無効フィールドにプログラム的なエラー識別があります{notes}。',
      { n: forms.length, notes: noteText }));
  }

  const hard = issues.filter(i => i.type === 'no-programmatic-error-text' || i.type === 'error-text-not-associated');
  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: hard.length ? 'critical' : 'moderate',
      status: 'incomplete',
      reason: _t(ctx,
        '{i} issue(s) across {n} form(s): {types}. Errors must be identified in text and associated with the field (aria-invalid + aria-describedby/aria-errormessage), and format errors should say what is expected{notes}.',
        '{n} 件のフォームで {i} 件の問題: {types}。エラーはテキストで示し、フィールドに関連付け（aria-invalid + aria-describedby/aria-errormessage）、形式エラーは期待される形式を伝える必要があります{notes}。',
        { i: issues.length, n: forms.length, types: [...new Set(issues.map(i => i.type))].join(', '), notes: noteText }),
      elements: issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
