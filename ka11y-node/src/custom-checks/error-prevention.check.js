'use strict';

const SC = '3.3.4';
const RULE_ID = 'custom-error-prevention';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/error-prevention-legal-financial-data';

// Bug fix: expanded financial/legal/destructive patterns for better coverage
const FINANCIAL_PATTERNS = /\b(payment|checkout|purchase|buy\s+now|credit\s*card|debit\s*card|card\s*number|billing|invoice|subscribe|subscription|order|confirm\s+order|place\s+order|donate|donation|fund|invest|transfer|wire\s+transfer|ach|withdraw|bank\s+account|routing\s+number)\b/i;
const LEGAL_PATTERNS     = /\b(legal|terms\s*(of\s*(service|use))?|privacy\s*policy|agreement|consent|contract|liability|gdpr|hipaa|sign\s*here|e[- ]?sign|electronic\s*signature)\b/i;
const DESTRUCTIVE_PATTERNS = /\b(delete\s+(account|data|profile|content)|remove\s+(account|data)|close\s+account|shut\s+down|deactivate|cancel\s+(account|subscription|membership)|unsubscribe|permanently\s+(delete|remove)|irreversible|purge|wipe|terminate)\b/i;

async function run(page) {
  const data = await page.evaluate((financialSrc, legalSrc, destructiveSrc) => {
    const financialRe   = new RegExp(financialSrc, 'i');
    const legalRe       = new RegExp(legalSrc, 'i');
    const destructiveRe = new RegExp(destructiveSrc, 'i');

    const forms = Array.from(document.querySelectorAll('form'));
    const riskForms = [];

    for (const form of forms) {
      const formText = (form.textContent || '').replace(/\s+/g, ' ');
      const isFinancial   = financialRe.test(formText);
      const isLegal       = legalRe.test(formText);
      const isDestructive = destructiveRe.test(formText);

      if (!isFinancial && !isLegal && !isDestructive) continue;

      const category = isDestructive ? 'destructive' : isFinancial ? 'financial' : 'legal';

      // Safeguard 1: Review/confirm step text present
      const hasReviewText = /\b(review|confirm|verify|check\s+your|summary|order\s+summary|please\s+review|are\s+you\s+sure)\b/i.test(formText);

      // Safeguard 2: Required confirmation checkbox
      const hasConfirmCheckbox = !!(
        form.querySelector('input[type="checkbox"][required]') ||
        form.querySelector('input[type="checkbox"][aria-required="true"]') ||
        // Bug fix: also detect JS-required checkboxes via data attributes
        form.querySelector('input[type="checkbox"][data-required]')
      );

      // Safeguard 3: Review/preview button before final submit
      const buttons = Array.from(form.querySelectorAll('button, input[type="submit"], input[type="button"]'));
      const hasReviewButton = buttons.some(b => {
        const label = ((b.textContent || '') + (b.getAttribute('value') || '')).trim();
        return /\b(review|preview|continue|next|proceed|back|edit)\b/i.test(label);
      });

      // Bug fix: Safeguard 4: Multi-step indicator (step/wizard UI)
      const hasMultiStepIndicator = !!(
        form.querySelector('[class*="step"],[class*="wizard"],[class*="progress"],[aria-label*="step" i]') ||
        document.querySelector('[class*="stepper"],[class*="multi-step"]')
      );

      const hasSafeguard = hasReviewText || hasConfirmCheckbox || hasReviewButton || hasMultiStepIndicator;

      riskForms.push({
        category,
        hasSafeguard,
        formId: form.id || null,
      });
    }

    return riskForms;
  }, FINANCIAL_PATTERNS.source, LEGAL_PATTERNS.source, DESTRUCTIVE_PATTERNS.source);

  if (data.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Legal, financial, and data submissions must be reversible, checked, or confirmed',
        impact: null,
        status: 'pass',
        reason: 'No legal, financial, or destructive action forms detected.',
        helpUrl: HELP_URL,
      }],
    };
  }

  const unsafeForms = data.filter(f => !f.hasSafeguard);

  if (unsafeForms.length > 0) {
    const categories = [...new Set(unsafeForms.map(f => f.category))];
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Legal, financial, and data submissions must be reversible, checked, or confirmed',
        impact: 'serious',
        status: 'fail',
        reason: `${unsafeForms.length} of ${data.length} ${categories.join('/')} form(s) detected without a visible review step, confirmation checkbox, multi-step indicator, or preview mechanism. Add a confirm/review step so users can verify before submitting.`,
        helpUrl: HELP_URL,
      }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Legal, financial, and data submissions must be reversible, checked, or confirmed',
      impact: null,
      status: 'pass',
      reason: `${data.length} high-risk form(s) detected — all appear to have a review/confirm safeguard in place.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run };