'use strict';

const fs = require('fs');
const path = require('path');

const STATIC_ORDER = [
  'custom-html-parsing',
  'custom-status-messages',
  'custom-multiple-ways',
  'custom-meaningful-sequence',
  'custom-character-key-shortcuts',
  'custom-pointer-cancellation',
  'custom-dragging-movements',
  'custom-consistent-help',
  'custom-error-suggestion',
  'custom-error-prevention',
  'custom-accessible-auth',
  'custom-use-of-color',
  'custom-audio-transcript',
  'custom-link-purpose',
  'custom-location',
  'custom-orientation',
];

const INTERACTIVE_ORDER = [
  'custom-focus-visible',
  'custom-focus-appearance',
  'custom-on-focus',
  'custom-on-input',
  'custom-keyboard-trap',
];

const LEGACY_META = {
  'custom-html-parsing':          { mode: 'static',      fallbackDescription: 'HTML id attributes must be unique' },
  'custom-status-messages':       { mode: 'static',      fallbackDescription: 'Status messages must be programmatically determinable' },
  'custom-multiple-ways':         { mode: 'static',      fallbackDescription: 'More than one way must be available to locate a page' },
  'custom-meaningful-sequence':   { mode: 'static',      fallbackDescription: 'Reading and navigation order must be programmatically determinable' },
  'custom-character-key-shortcuts': { mode: 'static',    fallbackDescription: 'Single character key shortcuts must be remappable or disableable' },
  'custom-pointer-cancellation':  { mode: 'static',      fallbackDescription: 'Functionality that uses a single pointer must be cancellable' },
  'custom-dragging-movements':    { mode: 'static',      fallbackDescription: 'Dragging movements must have a single-pointer alternative' },
  'custom-consistent-help':       { mode: 'static',      fallbackDescription: 'Help mechanisms must appear in a consistent location across pages' },
  'custom-error-suggestion':      { mode: 'static',      fallbackDescription: 'Error messages must suggest how to correct mistakes' },
  'custom-error-prevention':      { mode: 'static',      fallbackDescription: 'High-risk submissions must be reversible, checked, or confirmed' },
  'custom-accessible-auth':       { mode: 'static',      fallbackDescription: 'Authentication must not rely solely on cognitive function tests' },
  'custom-use-of-color':          { mode: 'static',      fallbackDescription: 'Color must not be the only visual means of conveying information' },
  'custom-audio-transcript':      { mode: 'static',      fallbackDescription: 'Audio-only prerecorded content must have a text alternative' },
  'custom-link-purpose':          { mode: 'static',      fallbackDescription: 'Link purpose must be determinable from link text alone' },
  'custom-location':              { mode: 'static',      fallbackDescription: 'Users must be able to determine their location within a set of web pages' },
  'custom-orientation':           { mode: 'static',      fallbackDescription: 'Content must not restrict its view and operation to a single display orientation' },
  'custom-focus-visible':         { mode: 'interactive', fallbackDescription: 'Focusable elements must have a visible focus indicator' },
  'custom-focus-appearance':      { mode: 'interactive', fallbackDescription: 'Focus indicators must have sufficient area and contrast' },
  'custom-on-focus':              { mode: 'interactive', fallbackDescription: 'Focusing an element must not trigger a context change' },
  'custom-on-input':              { mode: 'interactive', fallbackDescription: 'Changing an input value must not trigger a context change' },
  'custom-keyboard-trap':         { mode: 'interactive', fallbackDescription: 'Keyboard focus must not be trapped in a component' },
};

function _ruleIdFromFile(file) {
  return path.basename(file, '.check.js');
}

function _normalizeMode(check, ruleId) {
  const explicit = check && typeof check.MODE === 'string'
    ? check.MODE.toLowerCase()
    : null;
  if (explicit === 'static' || explicit === 'interactive') return explicit;
  return (LEGACY_META[ruleId] && LEGACY_META[ruleId].mode) || 'static';
}

function _fallbackDescription(check, ruleId) {
  return (check && (check.FALLBACK_DESCRIPTION || check.DESCRIPTION))
    || (LEGACY_META[ruleId] && LEGACY_META[ruleId].fallbackDescription)
    || 'Custom accessibility check execution failed';
}

function _sortChecks(a, b) {
  if (a.mode !== b.mode) return a.mode.localeCompare(b.mode);
  const order = a.mode === 'interactive' ? INTERACTIVE_ORDER : STATIC_ORDER;
  const aIdx = order.indexOf(a.ruleId);
  const bIdx = order.indexOf(b.ruleId);
  if (aIdx !== -1 || bIdx !== -1) {
    const aRank = aIdx === -1 ? Number.MAX_SAFE_INTEGER : aIdx;
    const bRank = bIdx === -1 ? Number.MAX_SAFE_INTEGER : bIdx;
    if (aRank !== bRank) return aRank - bRank;
  }
  return a.ruleId.localeCompare(b.ruleId);
}

function _buildLoadFailure(file, err) {
  const message = err && err.message ? err.message : String(err || 'unknown error');
  const ruleId = `custom-load-failure:${file}`;
  return {
    ruleId,
    mode: 'static',
    fallbackDescription: 'Custom accessibility check module failed to load',
    check: {
      SC: 'best-practice',
      RULE_ID: ruleId,
      HELP_URL: null,
      async run() {
        return {
          successCriteriaId: 'best-practice',
          rules: [{
            ruleId,
            description: 'Custom accessibility check module failed to load',
            impact: 'moderate',
            status: 'incomplete',
            reason: `Custom check module failed to load (${file}): ${message}`,
            helpUrl: null,
          }],
        };
      },
    },
  };
}

function _loadCheckDefinitions(dir = __dirname) {
  return fs.readdirSync(dir)
    .filter(file => file.endsWith('.check.js'))
    .map((file) => {
      try {
        const check = require(path.join(dir, file));
        const ruleId = check && check.RULE_ID ? check.RULE_ID : _ruleIdFromFile(file);

        if (!check || typeof check.run !== 'function') {
          throw new Error(`Module "${file}" does not export a run(page) function`);
        }

        return {
          check,
          ruleId,
          mode: _normalizeMode(check, ruleId),
          fallbackDescription: _fallbackDescription(check, ruleId),
        };
      } catch (err) {
        console.warn(`[custom-checks] failed to load ${file}:`, err && err.message || err);
        return _buildLoadFailure(file, err);
      }
    })
    .sort(_sortChecks);
}

const CHECK_DEFINITIONS = _loadCheckDefinitions();
const STATIC_CHECKS = CHECK_DEFINITIONS.filter(def => def.mode === 'static');
const INTERACTIVE_CHECKS = CHECK_DEFINITIONS.filter(def => def.mode === 'interactive');

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
    .filter(r => r != null);
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

module.exports = {
  _loadCheckDefinitions,
  mergeWithAxe,
  runAll,
  runInteractiveChecks,
  runStaticChecks,
};
