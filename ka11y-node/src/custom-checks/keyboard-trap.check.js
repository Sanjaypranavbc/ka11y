'use strict';

const SC = '2.1.2';
const RULE_ID = 'custom-keyboard-trap';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/no-keyboard-trap';
const MAX_TABS = 60;
// Buffer size for cycle detection: tracks last 4 focused keys.
// This detects both single-element stuck traps (A,A,A) and two-element cycling
// traps (A,B,A,B) — the most common real-world pattern (dialog with 2 focusable elements).
const CYCLE_WINDOW = 4;
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
      // Bug fix: prefer stable identifiers (id, name, aria-label) over DOM position.
      // Fall back to position+tag only when no stable attribute is available.
      const allEls = Array.from(document.querySelectorAll('*'));
      const pos = allEls.indexOf(el);
      // Use only id or name as stable key — NOT aria-label, which is often shared across
      // multiple elements (e.g. three "Close" buttons) and would produce false-positive traps.
      const stable = el.id || el.getAttribute('name') || '';
      const key = stable ? `${el.tagName}:${stable}` : `${pos}:${el.tagName}`;
      return { key, html: el.outerHTML.slice(0, 150), tagName: el.tagName.toLowerCase() };
    });

    if (!activeInfo) break; // focus left the page or hit body

    recentKeys.push(activeInfo.key);
    if (recentKeys.length > CYCLE_WINDOW) recentKeys.shift();

    // Detect two trap patterns:
    // 1. Stuck: same element focused 3+ times consecutively (1-element trap)
    const isStuck = recentKeys.length >= 3 && recentKeys.every(k => k === recentKeys[0]);
    // 2. Two-element cycle: A→B→A→B (most common dialog/tooltip trap)
    const n = recentKeys.length;
    const isTwoElemCycle = n >= 4 &&
      recentKeys[n - 1] === recentKeys[n - 3] &&
      recentKeys[n - 2] === recentKeys[n - 4] &&
      recentKeys[n - 1] !== recentKeys[n - 2];
    const isConsecutiveTrap = isStuck || isTwoElemCycle;

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
        const stable = el.id || el.getAttribute('name') || el.getAttribute('aria-label') || '';
        return stable ? `${el.tagName}:${stable}` : `${pos}:${el.tagName}`;
      });

      if (afterEscape === activeInfo.key) {
        trapHtml = activeInfo.html;
        break;
      }
      // Escape worked — reset tracking and continue
      recentKeys.length = 0;
    }
  }

  // FN fix: also test Shift+Tab (backward) navigation for traps.
  // A trap may only manifest when tabbing backward through the component.
  // Puppeteer helper: 'Shift+Tab' is not a valid key name — use down/press/up.
  const shiftTab = async () => {
    await page.keyboard.down('Shift');
    await page.keyboard.press('Tab');
    await page.keyboard.up('Shift');
  };

  if (!trapHtml) {
    const recentShiftKeys = [];

    for (let i = 0; i < MAX_TABS; i++) {
      await shiftTab();
      await new Promise(r => setTimeout(r, SETTLE_MS));

      const activeInfo = await page.evaluate(() => {
        const el = document.activeElement;
        if (!el || el === document.body || el === document.documentElement) return null;
        const allEls = Array.from(document.querySelectorAll('*'));
        const pos = allEls.indexOf(el);
        const stable = el.id || el.getAttribute('name') || '';
        const key = stable ? `${el.tagName}:${stable}` : `${pos}:${el.tagName}`;
        return { key, html: el.outerHTML.slice(0, 150), tagName: el.tagName.toLowerCase() };
      });

      if (!activeInfo) break;

      recentShiftKeys.push(activeInfo.key);
      if (recentShiftKeys.length > CYCLE_WINDOW) recentShiftKeys.shift();

      const sn = recentShiftKeys.length;
      const isShiftStuck = sn >= 3 && recentShiftKeys.every(k => k === recentShiftKeys[0]);
      const isShiftTwoElemCycle = sn >= 4 &&
        recentShiftKeys[sn - 1] === recentShiftKeys[sn - 3] &&
        recentShiftKeys[sn - 2] === recentShiftKeys[sn - 4] &&
        recentShiftKeys[sn - 1] !== recentShiftKeys[sn - 2];
      const isConsecutiveTrap = isShiftStuck || isShiftTwoElemCycle;

      if (isConsecutiveTrap) {
        // Verify: try Escape then Shift+Tab
        await page.keyboard.press('Escape');
        await new Promise(r => setTimeout(r, SETTLE_MS));
        await shiftTab();
        await new Promise(r => setTimeout(r, SETTLE_MS));

        const afterEscape = await page.evaluate(() => {
          const el = document.activeElement;
          if (!el || el === document.body) return null;
          const allEls = Array.from(document.querySelectorAll('*'));
          const pos = allEls.indexOf(el);
          const stable = el.id || el.getAttribute('name') || '';
          return stable ? `${el.tagName}:${stable}` : `${pos}:${el.tagName}`;
        });

        if (afterEscape === activeInfo.key) {
          trapHtml = activeInfo.html;
          break;
        }
        recentShiftKeys.length = 0;
      }
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
