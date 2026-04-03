'use strict';

const SC = '3.2.1';
const RULE_ID = 'custom-on-focus';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/on-focus';
const MAX_ELEMENTS = 60;
const SETTLE_MS = 100;

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

async function run(page) {
  const violations = [];
  let navigationDetected = false;
  const initialUrl = page.url();

  const onNavigated = () => { navigationDetected = true; };
  page.on('framenavigated', onNavigated);

  try {
    // Inject SPA navigation detection via pushState/replaceState interception
    await page.evaluate(() => {
      window.__navChanges = 0;
      const orig = history.pushState.bind(history);
      history.pushState = function(...args) { window.__navChanges++; return orig(...args); };
      const origReplace = history.replaceState.bind(history);
      history.replaceState = function(...args) { window.__navChanges++; return origReplace(...args); };
    });

    const focusable = await page.evaluate((sel, max) => {
      // Deduplicate: [tabindex] may overlap with a, button, etc.
      const seen = new Set();
      const results = [];
      for (const el of document.querySelectorAll(sel)) {
        if (seen.has(el)) continue;
        seen.add(el);
        results.push({
          tagName: el.tagName.toLowerCase(),
          id: el.id || null,
          html: el.outerHTML.slice(0, 150),
        });
        if (results.length >= max) break;
      }
      return results;
    }, SELECTOR, MAX_ELEMENTS);

    for (let i = 0; i < focusable.length; i++) {
      navigationDetected = false;
      const urlBefore = page.url();

      await page.evaluate((sel, idx) => {
        // Re-query each time — prior focus interactions may have altered DOM
        const uniqueEls = [];
        const seen = new Set();
        for (const el of document.querySelectorAll(sel)) {
          if (!seen.has(el)) { seen.add(el); uniqueEls.push(el); }
        }
        const el = uniqueEls[idx];
        if (el) el.focus({ preventScroll: true });
      }, SELECTOR, i);

      await new Promise(r => setTimeout(r, SETTLE_MS));

      const currentUrl = page.url();
      const spaNavChanged = await page.evaluate(() => window.__navChanges > 0).catch(() => false);
      if (spaNavChanged) {
        // Reset counter for next iteration
        await page.evaluate(() => { window.__navChanges = 0; }).catch(() => {});
      }

      // Only flag pathname/search changes — hash-only changes (skip-links, anchor navigation)
      // are not a WCAG 3.2.1 context change.
      if (navigationDetected || spaNavChanged || urlPathAndSearch(currentUrl) !== urlPathAndSearch(urlBefore)) {
        violations.push(focusable[i]);
        break; // page may have navigated; unsafe to continue testing other elements
      }
      // Reset SPA counter for next element
      await page.evaluate(() => { window.__navChanges = 0; }).catch(() => {});
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
      reason: `Focusing <${violations[0].tagName}${violations[0].id ? ` id="${violations[0].id}"` : ''}> triggered an unexpected navigation or context change. Testing stopped at the first violation — additional elements may be affected. Review all focusable elements for focus-triggered navigation.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
