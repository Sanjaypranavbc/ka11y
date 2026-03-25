'use strict';

const htmlParsing         = require('./html-parsing.check');
const focusVisible        = require('./focus-visible.check');
const focusAppearance     = require('./focus-appearance.check');
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
const useOfColor          = require('./use-of-color.check');

// Static checks: only DOM inspection, safe for raw HTML pages
const STATIC_CHECKS = [
  { check: htmlParsing,        fallbackDescription: 'HTML id attributes must be unique' },
  { check: statusMessages,     fallbackDescription: 'Status messages must be programmatically determinable' },
  { check: multipleWays,       fallbackDescription: 'More than one way must be available to locate a page' },
  { check: meaningfulSeq,      fallbackDescription: 'Reading and navigation order must be programmatically determinable' },
  { check: charKeyShortcuts,   fallbackDescription: 'Single character key shortcuts must be remappable or disableable' },
  { check: pointerCancellation, fallbackDescription: 'Functionality that uses a single pointer must be cancellable' },
  { check: draggingMovements,  fallbackDescription: 'Dragging movements must have a single-pointer alternative' },
  { check: consistentHelp,     fallbackDescription: 'Help mechanisms must appear in a consistent location across pages' },
  { check: errorSuggestion,    fallbackDescription: 'Error messages must suggest how to correct mistakes' },
  { check: errorPrevention,    fallbackDescription: 'High-risk submissions must be reversible, checked, or confirmed' },
  { check: accessibleAuth,     fallbackDescription: 'Authentication must not rely solely on cognitive function tests' },
  { check: useOfColor,         fallbackDescription: 'Color must not be the only visual means of conveying information' },
];

// Interactive checks: require a live navigable page with events
const INTERACTIVE_CHECKS = [
  { check: focusVisible,    fallbackDescription: 'Focusable elements must have a visible focus indicator' },
  { check: focusAppearance, fallbackDescription: 'Focus indicators must have sufficient area and contrast' },
  { check: onFocus,         fallbackDescription: 'Focusing an element must not trigger a context change' },
  { check: onInput,         fallbackDescription: 'Changing an input value must not trigger a context change' },
  { check: keyboardTrap,    fallbackDescription: 'Keyboard focus must not be trapped in a component' },
];

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

function _checkName(checkDef, idx) {
  return checkDef && checkDef.check && checkDef.check.RULE_ID
    ? checkDef.check.RULE_ID
    : `check[${idx}]`;
}

function _buildExecutionFailure(checkDef, reason) {
  const check = checkDef && checkDef.check ? checkDef.check : {};
  const message = reason && reason.message ? reason.message : String(reason || 'unknown error');

  return {
    successCriteriaId: check.SC || 'best-practice',
    rules: [{
      ruleId: check.RULE_ID || 'custom-check-execution-error',
      description: checkDef && checkDef.fallbackDescription
        ? checkDef.fallbackDescription
        : 'Custom accessibility check execution failed',
      impact: 'moderate',
      status: 'incomplete',
      reason: `Custom check execution failed: ${message}`,
      helpUrl: check.HELP_URL || null,
    }],
  };
}

async function _runChecks(checkDefs, page) {
  const results = await Promise.allSettled(checkDefs.map(d => d.check.run(page)));
  return results
    .map((r, i) => {
      if (r.status === 'rejected') {
        const name = _checkName(checkDefs[i], i);
        console.warn(`[custom-checks] ${name} failed:`, r.reason && r.reason.message || r.reason);
        return _buildExecutionFailure(checkDefs[i], r.reason);
      }
      return r.value;
    })
    .filter(Boolean);
}

async function runStaticChecks(page) {
  return _runChecks(STATIC_CHECKS, page);
}

async function runInteractiveChecks(page) {
  // Interactive checks must run sequentially (they mutate focus/keyboard/page state)
  const results = [];
  for (let i = 0; i < INTERACTIVE_CHECKS.length; i++) {
    const checkDef = INTERACTIVE_CHECKS[i];
    try {
      results.push(await checkDef.check.run(page));
    } catch (err) {
      const name = _checkName(checkDef, i);
      console.warn(`[custom-checks] ${name} failed:`, err && err.message || err);
      results.push(_buildExecutionFailure(checkDef, err));
    }
  }
  return results;
}

async function runAll(page) {
  // Deterministic order: static first, then interactive.
  // Running both in parallel on the same page can cause state interference.
  const staticR = await runStaticChecks(page);
  const interactiveR = await runInteractiveChecks(page);
  return [...staticR, ...interactiveR];
}

module.exports = { runAll, runStaticChecks, runInteractiveChecks, mergeWithAxe };
