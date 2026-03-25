'use strict';

const SC = '3.3.3';
const RULE_ID = 'custom-error-suggestion';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/error-suggestion';

// Patterns that indicate a message provides actual correction guidance
const SUGGESTION_RE = /please\s+(enter|provide|use|select|check|make sure|ensure|type|choose|pick)|must\s+(be|contain|have|include|start|end|match|not|be\s+at\s+least|be\s+between)|should\s+(be|contain|include|not)|at\s+least\s+\d|at\s+most\s+\d|between\s+\d+\s+and\s+\d+|characters?\s+(long|minimum|maximum|required)|valid\s+(email|phone|date|format|url|number|value)|try\s+again|example:/i;

// Patterns that indicate a terse/uninformative error message
const TERSE_RE = /^(invalid|error|required|failed|wrong|incorrect|bad\s+input|not\s+valid|this\s+field\s+is\s+required)\.?$/i;

async function run(page) {
  const data = await page.evaluate(() => {
    const formCount = document.querySelectorAll('form').length;

    // Bug fix: be more precise — require non-empty text content and some minimum length
    // to avoid false positives from decorative elements with "error" classes
    const errorSelectors = [
      '[role="alert"]',
      '[aria-live="assertive"]',
      '[aria-invalid="true"] + *',     // element immediately after invalid input
      '[aria-errormessage]',
    ];

    // Class/ID based selectors: scoped to form descendants to avoid false positives
    // from documentation pages and decorative elements that happen to have "error" in their class.
    const classSelectors = [
      'form .error-message', 'form .field-error', 'form .form-error', 'form .validation-error',
      'form .help-block.error', 'form [class*="error-msg"]', 'form [class*="error-text"]',
    ];

    const allSelectors = [...errorSelectors, ...classSelectors];
    const errorEls = Array.from(document.querySelectorAll(allSelectors.join(',')));

    // Also check aria-errormessage referenced elements
    for (const el of document.querySelectorAll('[aria-errormessage]')) {
      const targetId = el.getAttribute('aria-errormessage');
      if (targetId) {
        const target = document.getElementById(targetId);
        if (target && !errorEls.includes(target)) errorEls.push(target);
      }
    }

    // Deduplicate
    const seen = new Set();
    const allErrors = [];
    for (const el of errorEls) {
      if (seen.has(el)) continue;
      seen.add(el);
      const text = (el.textContent || '').trim().replace(/\s+/g, ' ');
      // Bug fix: filter out elements with no/trivial text (icons, decorative elements)
      if (text.length > 3) {
        allErrors.push(text.slice(0, 120));
      }
    }

    return { formCount, allErrors };
  });

  const { formCount, allErrors } = data;

  if (formCount === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Error messages must suggest how to correct mistakes',
        impact: null,
        status: 'pass',
        reason: 'No forms detected on this page.',
        helpUrl: HELP_URL,
      }],
    };
  }

  if (allErrors.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Error messages must suggest how to correct mistakes',
        impact: 'moderate',
        status: 'incomplete',
        reason: `${formCount} form(s) found but no visible error messages detected. Submit with invalid data and verify error messages explain how to correct the input (e.g. "Please enter a valid email" not just "Invalid").`,
        helpUrl: HELP_URL,
      }],
    };
  }

  const errorsWithoutSuggestion = allErrors.filter(text =>
    TERSE_RE.test(text) || (!SUGGESTION_RE.test(text) && text.length < 25)
  );

  if (errorsWithoutSuggestion.length > 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Error messages must suggest how to correct mistakes',
        impact: 'moderate',
        status: 'fail',
        reason: `${errorsWithoutSuggestion.length} of ${allErrors.length} error message(s) appear to lack correction guidance: "${errorsWithoutSuggestion.slice(0, 3).join('", "')}". Provide specific instructions, not just "Invalid" or "Error".`,
        helpUrl: HELP_URL,
      }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Error messages must suggest how to correct mistakes',
      impact: null,
      status: 'pass',
      reason: `${allErrors.length} error message(s) checked — all appear to provide correction guidance.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
