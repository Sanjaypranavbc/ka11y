'use strict';

const SC = '4.1.3';
const RULE_ID = 'custom-status-messages';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/status-messages';

async function run(page) {
  const data = await page.evaluate(() => {
    const liveRegions = Array.from(document.querySelectorAll(
      '[aria-live], [role="status"], [role="alert"], [role="log"], [role="timer"], [role="marquee"]'
    ));
    const forms = document.querySelectorAll('form');
    const hasAlerts = liveRegions.some(el =>
      el.getAttribute('role') === 'alert' ||
      el.getAttribute('aria-live') === 'assertive'
    );
    const hasPolite = liveRegions.some(el =>
      el.getAttribute('role') === 'status' ||
      el.getAttribute('aria-live') === 'polite'
    );
    return {
      liveRegionCount: liveRegions.length,
      formCount: forms.length,
      hasAlerts,
      hasPolite,
    };
  });

  const { liveRegionCount, formCount, hasAlerts, hasPolite } = data;

  // If the page has forms but no live regions: fail (errors won't be announced)
  if (formCount > 0 && liveRegionCount === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Status messages must be programmatically determinable',
        impact: 'serious',
        status: 'fail',
        reason: `Page has ${formCount} form(s) but no ARIA live regions (role="status/alert" or aria-live). Validation errors and success messages will not be announced to screen readers.`,
        helpUrl: HELP_URL,
      }],
    };
  }

  // If live regions exist, pass (dynamic check would need form submission)
  if (liveRegionCount > 0) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: 'Status messages must be programmatically determinable', impact: null, status: 'pass', reason: `${liveRegionCount} ARIA live region(s) found (alerts: ${hasAlerts}, polite: ${hasPolite}).`, helpUrl: HELP_URL }],
    };
  }

  // No forms, no live regions — incomplete (can't tell without dynamic interaction)
  return {
    successCriteriaId: SC,
    rules: [{ ruleId: RULE_ID, description: 'Status messages must be programmatically determinable', impact: 'moderate', status: 'incomplete', reason: 'No ARIA live regions detected. If this page displays status updates (notifications, alerts, form feedback), verify they use role="status", role="alert", or aria-live.', helpUrl: HELP_URL }],
  };
}

module.exports = { run };