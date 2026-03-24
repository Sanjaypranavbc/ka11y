'use strict';

const SC = '3.2.2';
const RULE_ID = 'custom-on-input';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/on-input';
const MAX_INPUTS = 10;
const SETTLE_MS = 100;

async function run(page) {
  const violations = [];
  let navigationDetected = false;
  const initialUrl = page.url();

  const onNavigated = () => { navigationDetected = true; };
  page.on('framenavigated', onNavigated);

  try {
    const inputs = await page.evaluate((max) => {
      const SELECTOR = 'input:not([type="submit"]):not([type="button"]):not([type="reset"]):not([type="hidden"]):not([type="file"]):not([disabled]), textarea:not([disabled])';
      return Array.from(document.querySelectorAll(SELECTOR)).slice(0, max).map((el, i) => ({
        index: i,
        tagName: el.tagName.toLowerCase(),
        type: el.type || null,
        id: el.id || null,
        html: el.outerHTML.slice(0, 150),
      }));
    }, MAX_INPUTS);

    for (const inputInfo of inputs) {
      navigationDetected = false;

      // Focus and type a single safe character
      await page.evaluate((idx) => {
        const SELECTOR = 'input:not([type="submit"]):not([type="button"]):not([type="reset"]):not([type="hidden"]):not([type="file"]):not([disabled]), textarea:not([disabled])';
        const el = document.querySelectorAll(SELECTOR)[idx];
        if (el) el.focus({ preventScroll: true });
      }, inputInfo.index);

      await page.keyboard.type('a');
      await new Promise(r => setTimeout(r, SETTLE_MS));

      const currentUrl = page.url();
      if (navigationDetected || currentUrl !== initialUrl) {
        violations.push(inputInfo);
        break;
      }

      // Clean up typed character
      await page.keyboard.press('Backspace');
    }
  } finally {
    page.off('framenavigated', onNavigated);
  }

  if (violations.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: 'Changing an input value must not trigger a context change', impact: null, status: 'pass', reason: 'No unexpected context changes detected on input.', helpUrl: HELP_URL }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Changing an input value must not trigger a context change',
      impact: 'serious',
      status: 'fail',
      reason: `Typing into <${violations[0].tagName}${violations[0].id ? ` id="${violations[0].id}"` : ''}> triggered an unexpected navigation or context change.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run };