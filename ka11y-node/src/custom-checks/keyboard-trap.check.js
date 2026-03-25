'use strict';

const SC = '2.1.2';
const RULE_ID = 'custom-keyboard-trap';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/no-keyboard-trap';
const MAX_TABS = 60;
// Bug fix: use consecutive repeat count (not total), to avoid false positives
// from elements that legitimately appear multiple times in DOM (e.g. same nav on mobile/desktop)
const CONSECUTIVE_THRESHOLD = 3;
// Settle delay: allow focus event handlers and page mutations to complete before reading state
const SETTLE_MS = 60;

async function run(page) {
  // Focus the page body to start from a known position
  await page.evaluate(() => { try { document.body.focus(); } catch (_) {} });

  // Bug fix: track the LAST N focus targets to detect consecutive repetition
  // rather than cumulative count which caused false positives on identical elements
  const recentKeys = [];
  let trapHtml = null;

  for (let i = 0; i < MAX_TABS; i++) {
    await page.keyboard.press('Tab');
    // Wait for focus event handlers and React/Vue re-renders to settle
    await new Promise(r => setTimeout(r, SETTLE_MS));

    const activeInfo = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body || el === document.documentElement) return null;
      // Bug fix: use position-stable key combining tag + position in DOM
      // to avoid key collision between elements with same class/no id
      const allEls = Array.from(document.querySelectorAll('*'));
      const pos = allEls.indexOf(el);
      const key = `${pos}:${el.tagName}`;
      return { key, html: el.outerHTML.slice(0, 150), tagName: el.tagName.toLowerCase() };
    });

    if (!activeInfo) break; // focus left the page or hit body

    recentKeys.push(activeInfo.key);
    if (recentKeys.length > CONSECUTIVE_THRESHOLD) recentKeys.shift();

    // Consecutive repeat: same element focused N times in a row
    const isConsecutiveTrap = recentKeys.length === CONSECUTIVE_THRESHOLD &&
      recentKeys.every(k => k === activeInfo.key);

    if (isConsecutiveTrap) {
      // Verify it's a real trap: try Escape then Tab
      // Settle after Escape to allow modal-close / focus-restore handlers to run
      await page.keyboard.press('Escape');
      await new Promise(r => setTimeout(r, SETTLE_MS));
      await page.keyboard.press('Tab');
      await new Promise(r => setTimeout(r, SETTLE_MS));

      const afterEscape = await page.evaluate(() => {
        const el = document.activeElement;
        if (!el || el === document.body) return null;
        const allEls = Array.from(document.querySelectorAll('*'));
        const pos = allEls.indexOf(el);
        return `${pos}:${el.tagName}`;
      });

      if (afterEscape === activeInfo.key) {
        trapHtml = activeInfo.html;
        break;
      }
      // Escape worked — reset tracking and continue
      recentKeys.length = 0;
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

module.exports = { run, SC, RULE_ID, HELP_URL };
