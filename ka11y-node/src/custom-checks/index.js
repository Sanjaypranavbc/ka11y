'use strict';

const htmlParsing         = require('./html-parsing.check');
const focusVisible        = require('./focus-visible.check');
const statusMessages      = require('./status-messages.check');
const multipleWays        = require('./multiple-ways.check');
const onFocus             = require('./on-focus.check');
const onInput             = require('./on-input.check');
const keyboardTrap        = require('./keyboard-trap.check');
const meaningfulSeq       = require('./meaningful-sequence.check');
const charKeyShortcuts    = require('./character-key-shortcuts.check');
const pointerCancellation = require('./pointer-cancellation.check');
const draggingMovements   = require('./dragging-movements.check');
const consistentHelp      = require('./consistent-help.check');
const errorSuggestion     = require('./error-suggestion.check');
const errorPrevention     = require('./error-prevention.check');
const accessibleAuth      = require('./accessible-auth.check');

// Static checks: only DOM inspection, safe for raw HTML pages
const STATIC_CHECKS = [
  htmlParsing, statusMessages, multipleWays, meaningfulSeq,
  charKeyShortcuts, pointerCancellation, draggingMovements,
  consistentHelp, errorSuggestion, errorPrevention, accessibleAuth,
];

// Interactive checks: require a live navigable page with events
const INTERACTIVE_CHECKS = [focusVisible, onFocus, onInput, keyboardTrap];

/**
 * Merge custom check results with axe mapResults() output.
 * Both arrays have shape: [{ successCriteriaId, rules: [...] }]
 */
function mergeWithAxe(axeResults, customResults) {
  const map = new Map();
  for (const entry of axeResults) map.set(entry.successCriteriaId, { ...entry, rules: [...entry.rules] });

  for (const entry of customResults) {
    if (map.has(entry.successCriteriaId)) {
      map.get(entry.successCriteriaId).rules.push(...entry.rules);
    } else {
      map.set(entry.successCriteriaId, entry);
    }
  }

  return [...map.values()].sort((a, b) => a.successCriteriaId.localeCompare(b.successCriteriaId));
}

async function _runChecks(checks, page) {
  const results = await Promise.allSettled(checks.map(c => c.run(page)));
  return results
    .map((r, i) => {
      if (r.status === 'rejected') {
        // Bug fix: log failures instead of silently discarding them
        const name = checks[i] && checks[i].run && checks[i].run.name
          ? checks[i].run.name
          : `check[${i}]`;
        console.warn(`[custom-checks] ${name} failed:`, r.reason && r.reason.message || r.reason);
        return null;
      }
      return r.value;
    })
    .filter(Boolean);
}

async function runStaticChecks(page) {
  return _runChecks(STATIC_CHECKS, page);
}

async function runInteractiveChecks(page) {
  // Interactive checks must run sequentially (they interact with focus/keyboard state)
  const results = [];
  for (const check of INTERACTIVE_CHECKS) {
    try {
      results.push(await check.run(page));
    } catch (_) { /* swallow: page may have navigated */ }
  }
  return results;
}

async function runAll(page) {
  const [staticR, interactiveR] = await Promise.all([
    runStaticChecks(page),
    runInteractiveChecks(page),
  ]);
  return [...staticR, ...interactiveR];
}

module.exports = { runAll, runStaticChecks, runInteractiveChecks, mergeWithAxe };