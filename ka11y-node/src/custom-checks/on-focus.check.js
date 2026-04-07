'use strict';

const SC = '3.2.1';
const RULE_ID = 'custom-on-focus';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/on-focus';
const MAX_ELEMENTS = 60;
const SETTLE_MS = 100;
const NAV_STATE_KEY = '__ka11yOnFocusNavState';

// Includes form controls (input, select, textarea) — they can carry onfocus handlers
const SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

// Compare only pathname + search (not hash) to avoid false positives on skip-links
// and hash-based anchor navigation (B7), while still catching real navigations (B10).
function urlPathAndSearch(url) {
  try { const u = new URL(url); return u.pathname + u.search; } catch { return url; }
}

async function installNavInstrumentation(page) {
  await page.evaluate((stateKey) => {
    const existing = window[stateKey];
    if (existing && existing.originalPush && existing.originalReplace) {
      existing.count = 0;
      return;
    }

    const originalPush = history.pushState.bind(history);
    const originalReplace = history.replaceState.bind(history);
    window[stateKey] = {
      count: 0,
      originalPush,
      originalReplace,
    };

    history.pushState = function(...args) {
      window[stateKey].count++;
      return originalPush(...args);
    };
    history.replaceState = function(...args) {
      window[stateKey].count++;
      return originalReplace(...args);
    };
  }, NAV_STATE_KEY);
}

async function readAndResetNavInstrumentation(page) {
  return page.evaluate((stateKey) => {
    const state = window[stateKey];
    const changed = !!(state && state.count > 0);
    if (state) state.count = 0;
    return changed;
  }, NAV_STATE_KEY).catch(() => false);
}

async function uninstallNavInstrumentation(page) {
  await page.evaluate((stateKey) => {
    const state = window[stateKey];
    if (!state) return;
    if (state.originalPush) history.pushState = state.originalPush;
    if (state.originalReplace) history.replaceState = state.originalReplace;
    delete window[stateKey];
  }, NAV_STATE_KEY).catch(() => {});
}

async function run(page) {
  const violations = [];
  let navigationDetected = false;

  const onNavigated = () => { navigationDetected = true; };
  page.on('framenavigated', onNavigated);

  try {
    await installNavInstrumentation(page);

    const focusable = await page.evaluate((sel, max) => {
      const seen = new Set();
      const results = [];
      const idCounts = {};
      for (const el of document.querySelectorAll('[id]')) {
        idCounts[el.id] = (idCounts[el.id] || 0) + 1;
      }
      for (const el of document.querySelectorAll(sel)) {
        if (seen.has(el)) continue;
        seen.add(el);
        results.push({
          tagName: el.tagName.toLowerCase(),
          id: el.id || null,
          stableSel: el.id && idCounts[el.id] === 1 ? `#${CSS.escape(el.id)}` : null,
          html: el.outerHTML.slice(0, 150),
        });
        if (results.length >= max) break;
      }
      return results;
    }, SELECTOR, MAX_ELEMENTS);

    for (let i = 0; i < (focusable || []).length; i++) {
      navigationDetected = false;
      const urlBefore = page.url();

      await page.evaluate((sel, idx, stableSel) => {
        const all = Array.from(document.querySelectorAll(sel));
        const el = stableSel
          ? (document.querySelector(stableSel) || all[idx])
          : all[idx];
        if (el) el.focus({ preventScroll: true });
      }, SELECTOR, i, focusable[i].stableSel || null);

      await new Promise(r => setTimeout(r, SETTLE_MS));

      const currentUrl = page.url();
      const spaNavChanged = await readAndResetNavInstrumentation(page);

      // Only flag pathname/search changes — hash-only changes (skip-links, anchor navigation)
      // are not a WCAG 3.2.1 context change.
      if (navigationDetected || spaNavChanged || urlPathAndSearch(currentUrl) !== urlPathAndSearch(urlBefore)) {
        violations.push(focusable[i]);
        break; // page may have navigated; unsafe to continue testing other elements
      }
    }
  } finally {
    page.off('framenavigated', onNavigated);
    await uninstallNavInstrumentation(page);
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
      reason: `Focusing <${violations[0].tagName}${violations[0].id ? ` id="${violations[0].id}"` : ''}> triggered an unexpected navigation or context change. Testing stopped at the first violation — additional elements may be affected. Review all focusable elements for focus-triggered navigation.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
