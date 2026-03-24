'use strict';

const SC = '3.2.1';
const RULE_ID = 'custom-on-focus';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/on-focus';
const MAX_ELEMENTS = 20;
const SETTLE_MS = 80;

async function run(page) {
  const violations = [];
  let navigationDetected = false;
  const initialUrl = page.url();

  const onNavigated = () => { navigationDetected = true; };
  page.on('framenavigated', onNavigated);

  try {
    const focusable = await page.evaluate((max) => {
      const SELECTOR = 'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])';
      return Array.from(document.querySelectorAll(SELECTOR)).slice(0, max).map((el, i) => ({
        index: i,
        tagName: el.tagName.toLowerCase(),
        id: el.id || null,
        html: el.outerHTML.slice(0, 150),
      }));
    }, MAX_ELEMENTS);

    for (const elInfo of focusable) {
      navigationDetected = false;

      await page.evaluate((idx) => {
        const SELECTOR = 'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])';
        const el = document.querySelectorAll(SELECTOR)[idx];
        if (el) el.focus({ preventScroll: true });
      }, elInfo.index);

      await new Promise(r => setTimeout(r, SETTLE_MS));

      const currentUrl = page.url();
      if (navigationDetected || currentUrl !== initialUrl) {
        violations.push(elInfo);
        break; // Stop on first — page may have navigated away
      }
    }
  } finally {
    page.off('framenavigated', onNavigated);
  }

  if (violations.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: 'Focusing an element must not trigger a context change', impact: null, status: 'pass', reason: 'No unexpected context changes detected on focus.', helpUrl: HELP_URL }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Focusing an element must not trigger a context change',
      impact: 'serious',
      status: 'fail',
      reason: `Focusing <${violations[0].tagName}${violations[0].id ? ` id="${violations[0].id}"` : ''}> triggered an unexpected navigation or context change.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run };