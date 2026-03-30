'use strict';

const SC = '4.1.3';
const RULE_ID = 'custom-status-messages';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/status-messages';

async function run(page) {
  const data = await page.evaluate(() => {
    const liveRegions = Array.from(document.querySelectorAll(
      '[aria-live], [role="status"], [role="alert"], [role="log"], [role="timer"], [role="marquee"]'
    ));

    const forms     = document.querySelectorAll('form');
    const formCount = forms.length;

    const hasAlerts = liveRegions.some(el =>
      el.getAttribute('role') === 'alert' ||
      el.getAttribute('aria-live') === 'assertive'
    );
    const hasPolite = liveRegions.some(el =>
      el.getAttribute('role') === 'status' ||
      el.getAttribute('aria-live') === 'polite'
    );

    // Bug fix: detect other dynamic-content contexts beyond forms
    // that would need status messages (search results, cart, notifications)
    const hasSearchResults = !!(
      document.querySelector('[role="region"][aria-label*="result" i]') ||
      document.querySelector('[aria-live][id*="result" i]') ||
      document.querySelector('[id*="search-result" i], [class*="search-result" i]')
    );
    // B14: '[class*="badge" i]' was too broad — it matched Bootstrap decorative labels
    // ("New", "Pro", "Beta") and other non-counter badge components, causing false
    // positives. Only count a badge as a dynamic counter if it contains a number or
    // an aria-label that explicitly signals counter behaviour.
    const badgeEls = Array.from(document.querySelectorAll('[class*="badge" i]'));
    const hasCounterBadge = badgeEls.some(el => {
      const text = (el.textContent || '').trim();
      const label = (el.getAttribute('aria-label') || '').toLowerCase();
      return /^\d+\+?$/.test(text) ||
             /count|counter|notification|unread|\bnew\b/i.test(label);
    });
    const hasCartOrCounter = !!(
      document.querySelector('[aria-label*="cart" i], [aria-label*="basket" i]') ||
      document.querySelector('[class*="cart-count" i]') ||
      hasCounterBadge
    );
    // FP fix: detect visual notification patterns only when they are NOT already
    // contained within an existing live region. If the notification element is already
    // inside a [role="status"], [role="alert"], or [aria-live] ancestor, it already
    // has a live region and should not trigger "needs live regions".
    const notificationCandidates = Array.from(document.querySelectorAll(
      '[class*="notification" i], [class*="toast" i], [class*="snackbar" i], [class*="flash" i], ' +
      '[class*="alert" i]:not([role]), [class*="banner" i]:not([role])'
    ));
    const hasNotificationArea = notificationCandidates.some(el => {
      // Walk up ancestors to check if this element is already inside a live region
      let node = el;
      while (node && node !== document.body) {
        const role = node.getAttribute('role');
        const ariaLive = node.getAttribute('aria-live');
        if (role === 'status' || role === 'alert' || role === 'log' ||
            ariaLive === 'polite' || ariaLive === 'assertive') {
          return false; // already inside a live region — not a problem
        }
        node = node.parentElement;
      }
      return true; // notification element has no live region ancestor
    });

    const needsLiveRegions = formCount > 0 || hasSearchResults || hasCartOrCounter || hasNotificationArea;

    // Probe: check whether any live region already has text content at page-load time.
    // An empty live region (no content) has never been used yet — flag it as a signal
    // that the live regions may be structural placeholders not wired to actual updates.
    // Note: live regions that are correctly empty at load and populated on interaction
    // will appear as "no content", so this is informational, not a definitive fail.
    const anyLiveRegionHasContent = liveRegions.some(
      el => (el.textContent || '').trim().length > 0
    );

    return {
      liveRegionCount: liveRegions.length,
      formCount,
      hasAlerts,
      hasPolite,
      needsLiveRegions,
      anyLiveRegionHasContent,
      dynamicContexts: [
        formCount > 0 && `${formCount} form(s)`,
        hasSearchResults && 'search results',
        hasCartOrCounter && 'cart/counter',
        hasNotificationArea && 'notification area',
      ].filter(Boolean),
    };
  });

  const { liveRegionCount, formCount, hasAlerts, hasPolite, needsLiveRegions, anyLiveRegionHasContent, dynamicContexts } = data;

  // Page has dynamic contexts but no live regions at all → clear fail
  if (needsLiveRegions && liveRegionCount === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Status messages must be programmatically determinable',
        impact: 'serious',
        status: 'fail',
        reason: `Dynamic content contexts detected (${dynamicContexts.join(', ')}) but no ARIA live regions found. Validation errors and status updates will not be announced to screen readers.`,
        helpUrl: HELP_URL,
      }],
    };
  }

  // Dynamic contexts exist AND live regions exist → needs_review (can't verify coverage statically).
  // Add an informational note about whether any live region had text content at page load —
  // all-empty live regions may be structural placeholders that are never written to.
  if (needsLiveRegions && liveRegionCount > 0) {
    const contentNote = anyLiveRegionHasContent
      ? 'At least one live region contains text at page load.'
      : 'All live regions are empty at page load — confirm they are populated on status updates at runtime.';
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: 'Status messages must be programmatically determinable', impact: null, status: 'incomplete', reason: `${liveRegionCount} ARIA live region(s) found (assertive: ${hasAlerts}, polite: ${hasPolite}) alongside dynamic contexts (${dynamicContexts.join(', ')}). ${contentNote} Verify live regions are correctly wired to each status update.`, helpUrl: HELP_URL }],
    };
  }

  // Live regions present, no unprotected dynamic contexts → pass
  if (liveRegionCount > 0) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: 'Status messages must be programmatically determinable', impact: null, status: 'pass', reason: `${liveRegionCount} ARIA live region(s) found (assertive: ${hasAlerts}, polite: ${hasPolite}).`, helpUrl: HELP_URL }],
    };
  }

  // No dynamic contexts and no live regions — not enough info, mark incomplete
  return {
    successCriteriaId: SC,
    rules: [{ ruleId: RULE_ID, description: 'Status messages must be programmatically determinable', impact: 'moderate', status: 'incomplete', reason: 'No ARIA live regions detected. If this page displays status updates (alerts, notifications, form feedback), verify they use role="status", role="alert", or aria-live.', helpUrl: HELP_URL }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
