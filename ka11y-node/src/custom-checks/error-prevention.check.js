'use strict';

const {
  buildKeywordPattern,
  getKeywordList,
  getSharedRuleContext,
  renderReasonTemplate,
} = require('./sharedAssets');

const SC = '3.3.4';
const RULE_ID = 'custom-error-prevention';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/error-prevention-legal-financial-data';

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);
  const financialPattern = buildKeywordPattern(
    getKeywordList('error_prevention', 'financial_keywords', sharedContext)
  ) || 'payment|checkout|purchase|order';
  const legalPattern = buildKeywordPattern(
    getKeywordList('error_prevention', 'legal_keywords', sharedContext)
  ) || 'legal|terms|privacy|contract|consent';
  const destructivePattern = buildKeywordPattern(
    getKeywordList('error_prevention', 'destructive_keywords', sharedContext)
  ) || 'delete|remove|cancel|unsubscribe';
  const reviewPattern = buildKeywordPattern(
    getKeywordList('error_prevention', 'review_keywords', sharedContext)
  ) || 'review|confirm|verify|summary';
  const reviewButtonPattern = buildKeywordPattern(
    getKeywordList('error_prevention', 'review_button_keywords', sharedContext)
  ) || 'review|preview|continue|next|edit';
  const stepPattern = buildKeywordPattern(
    getKeywordList('error_prevention', 'step_keywords', sharedContext)
  ) || 'step|wizard|progress';

  const data = await page.evaluate((patterns) => {
    const financialRe = new RegExp(patterns.financialPattern, 'i');
    const legalRe = new RegExp(patterns.legalPattern, 'i');
    const destructiveRe = new RegExp(patterns.destructivePattern, 'i');
    const reviewRe = new RegExp(patterns.reviewPattern, 'i');
    const reviewButtonRe = new RegExp(patterns.reviewButtonPattern, 'i');
    const stepRe = new RegExp(patterns.stepPattern, 'i');

    function isVisible(el) {
      const cs = window.getComputedStyle(el);
      return cs.display !== 'none' && cs.visibility !== 'hidden' && cs.opacity !== '0';
    }

    const forms = Array.from(document.querySelectorAll('form'));
    const riskForms = [];

    for (const form of forms) {
      // Scope matching to high-signal elements: headings, submit buttons, fieldset legends,
      // and form action/id attributes. Avoid matching all form text to prevent false positives
      // from inline links like "Read our privacy policy" inside checkbox labels.
      const submitLabels = Array.from(
        form.querySelectorAll('button[type="submit"], input[type="submit"], button:not([type])')
      ).map(b => ((b.textContent || '') + (b.getAttribute('value') || '')).trim()).join(' ');
      const headings = Array.from(form.querySelectorAll('h1,h2,h3,h4,h5,h6,legend,label[class*="head"]'))
        .map(h => h.textContent || '').join(' ');
      const formMeta = [(form.id || ''), (form.getAttribute('action') || ''), (form.getAttribute('name') || '')].join(' ');
      const focusedText = [submitLabels, headings, formMeta].join(' ').replace(/\s+/g, ' ');

      const isFinancial   = financialRe.test(focusedText);
      const isLegal       = legalRe.test(focusedText);
      const isDestructive = destructiveRe.test(focusedText);

      if (!isFinancial && !isLegal && !isDestructive) continue;

      const category = isDestructive ? 'destructive' : isFinancial ? 'financial' : 'legal';

      // Safeguard 1: Review/confirm step text present
      const hasReviewText = reviewRe.test(focusedText);

      // Safeguard 2: Required confirmation checkbox (must be visible)
      const confirmCheckboxCandidates = [
        form.querySelector('input[type="checkbox"][required]'),
        form.querySelector('input[type="checkbox"][aria-required="true"]'),
        form.querySelector('input[type="checkbox"][data-required]'),
      ].filter(Boolean);
      const hasConfirmCheckbox = confirmCheckboxCandidates.some(el => isVisible(el));

      // Safeguard 3: Review/preview button before final submit (must be visible)
      const buttons = Array.from(form.querySelectorAll('button, input[type="submit"], input[type="button"]')).filter(isVisible);
      const hasReviewButton = buttons.some(b => {
        const label = ((b.textContent || '') + (b.getAttribute('value') || '')).trim();
        return reviewButtonRe.test(label);
      });

      // Bug fix: Safeguard 4: Multi-step indicator (step/wizard UI)
      const hasMultiStepIndicator = !!(
        form.querySelector('[class*="step"],[class*="wizard"],[class*="progress"],[aria-label*="step" i]') ||
        document.querySelector('[class*="stepper"],[class*="multi-step"]') ||
        Array.from(document.querySelectorAll('[class], [aria-label]')).some(el =>
          stepRe.test(el.getAttribute('class') || '') || stepRe.test(el.getAttribute('aria-label') || '')
        )
      );

      const hasSafeguard = hasReviewText || hasConfirmCheckbox || hasReviewButton || hasMultiStepIndicator;

      riskForms.push({
        category,
        hasSafeguard,
        formId: form.id || null,
      });
    }

    return riskForms;
  }, {
    destructivePattern,
    financialPattern,
    legalPattern,
    reviewButtonPattern,
    reviewPattern,
    stepPattern,
  });

  if (data.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Legal, financial, and data submissions must be reversible, checked, or confirmed',
        impact: null,
        status: 'pass',
        reason: renderReasonTemplate(
          'error_prevention',
          'no_risk',
          {},
          sharedContext,
          'No legal, financial, or destructive action forms detected.',
        ),
        helpUrl: HELP_URL,
      }],
    };
  }

  const unsafeForms = data.filter(f => !f.hasSafeguard);

  if (unsafeForms.length > 0) {
    const categories = [...new Set(unsafeForms.map(f => f.category))];
    const formRefs = unsafeForms.slice(0, 3)
      .map(f => f.formId ? `form#${f.formId}` : `<form> (${f.category})`).join(', ');
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
      description: 'Legal, financial, and data submissions must be reversible, checked, or confirmed',
      impact: 'serious',
      status: 'fail',
      reason: renderReasonTemplate(
        'error_prevention',
        'unsafe',
        {
          unsafe_count: unsafeForms.length,
          total_count: data.length,
          category_list: categories.join('/'),
          form_refs: formRefs,
        },
        sharedContext,
        `${unsafeForms.length} of ${data.length} ${categories.join('/')} form(s) have no review step, confirmation checkbox, multi-step indicator, or preview mechanism: ${formRefs}.`,
      ),
      helpUrl: HELP_URL,
    }],
    };
  }

  const safeForms = data.map(f => f.formId ? `form#${f.formId}` : `<form> (${f.category})`).join(', ');
  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Legal, financial, and data submissions must be reversible, checked, or confirmed',
      impact: null,
      status: 'pass',
      reason: renderReasonTemplate(
        'error_prevention',
        'safe',
        {
          total_count: data.length,
          safe_refs: safeForms,
        },
        sharedContext,
        `${data.length} high-risk form(s) detected — all have a review/confirm safeguard: ${safeForms}.`,
      ),
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
