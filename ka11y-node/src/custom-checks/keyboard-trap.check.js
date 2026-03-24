'use strict';

const SC = '2.1.2';
const RULE_ID = 'custom-keyboard-trap';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/no-keyboard-trap';
const MAX_TABS = 60;
const CONSECUTIVE_REPEATS_THRESHOLD = 3;

async function run(page) {
  // Focus the page body to start from a known position
  await page.evaluate(() => document.body.focus());

  const seen = {};
  let trapHtml = null;

  for (let i = 0; i < MAX_TABS; i++) {
    await page.keyboard.press('Tab');

    const activeInfo = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body || el === document.documentElement) return null;
      const key = (el.id || '') + '|' + el.tagName + '|' + (el.className || '').slice(0, 30);
      return { key, html: el.outerHTML.slice(0, 150), tagName: el.tagName.toLowerCase() };
    });

    if (!activeInfo) break;

    seen[activeInfo.key] = (seen[activeInfo.key] || 0) + 1;

    if (seen[activeInfo.key] >= CONSECUTIVE_REPEATS_THRESHOLD) {
      // Potential trap: same element focused 3 times — try Escape to break out
      await page.keyboard.press('Escape');
      await page.keyboard.press('Tab');

      const afterEscape = await page.evaluate(() => {
        const el = document.activeElement;
        if (!el || el === document.body) return null;
        return (el.id || '') + '|' + el.tagName + '|' + (el.className || '').slice(0, 30);
      });

      if (afterEscape === activeInfo.key) {
        trapHtml = activeInfo.html;
        break;
      }
      // Escape worked — not a trap, reset counter
      seen[activeInfo.key] = 0;
    }
  }

  if (!trapHtml) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: 'Keyboard focus must not be trapped in a component', impact: null, status: 'pass', reason: 'No keyboard focus traps detected during Tab navigation.', helpUrl: HELP_URL }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Keyboard focus must not be trapped in a component',
      impact: 'critical',
      status: 'fail',
      reason: `Keyboard focus appears trapped in: ${trapHtml.slice(0, 120)}. Tab key could not escape the component even after pressing Escape.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run };