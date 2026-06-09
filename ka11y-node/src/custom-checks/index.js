'use strict';

const fs = require('fs');
const path = require('path');
const { loadSharedConfig } = require('../utils/sharedConfigLoader');
const { sanitizeLang } = require('./sharedAssets');

const STATIC_ORDER = [
  'custom-html-parsing',
  'custom-status-messages',
  'custom-multiple-ways',
  'custom-meaningful-sequence',
  'custom-character-key-shortcuts',
  'custom-pointer-cancellation',
  'custom-dragging-movements',
  'custom-pointer-gestures',
  'custom-motion-actuation',
  'custom-consistent-help',
  'custom-error-suggestion',
  'custom-error-prevention',
  'custom-redundant-entry',
  'custom-accessible-auth',
  'custom-use-of-color',
  'custom-audio-transcript',
  'custom-captions-prerecorded',
  'custom-captions-live',
  'custom-audio-description',
  'custom-audio-description-prerecorded',
  'custom-extended-audio-description',
  'custom-media-alternative',
  'custom-audio-control',
  'custom-link-purpose',
  'custom-location',
  'custom-orientation',
  'custom-sensory-characteristics',
  'custom-identify-purpose',
  'custom-images-of-text',
  'custom-images-of-text-no-exception',
  'custom-visual-presentation',
  'custom-background-image-content',
  'custom-keyboard-no-exception',
  'custom-animation-from-interactions',
  'custom-target-size-enhanced',
  'custom-concurrent-input-mechanisms',
  'custom-pronunciation',
  'custom-language-of-parts',
  'custom-unusual-words',
  'custom-abbreviations',
  'custom-reading-level',
  'custom-help-mechanism',
  'custom-error-prevention-all',
  'custom-accessible-auth-enhanced',
  'custom-audio-only-live',
  'custom-three-flashes',
  'custom-three-flashes-no-exception',
  'custom-consistent-navigation',
  'custom-consistent-identification',
  'custom-change-on-request',
  'custom-contrast-enhanced',
  'custom-text-spacing',
  'custom-pause-stop-hide',
  'custom-section-headings',
];

const INTERACTIVE_ORDER = [
  'custom-reflow',
  'custom-content-on-hover-focus',
  'custom-focus-visible',
  'custom-focus-appearance',
  'custom-focus-not-obscured',
  'custom-focus-not-obscured-enhanced',
  'custom-on-focus',
  'custom-on-input',
  'custom-keyboard-trap',
  'custom-error-identification',
];

const LEGACY_META = {
  'custom-html-parsing':          { mode: 'static',      fallbackDescription: 'HTML id attributes must be unique' },
  'custom-status-messages':       { mode: 'static',      fallbackDescription: 'Status messages must be programmatically determinable' },
  'custom-multiple-ways':         { mode: 'static',      fallbackDescription: 'More than one way must be available to locate a page' },
  'custom-meaningful-sequence':   { mode: 'static',      fallbackDescription: 'Reading and navigation order must be programmatically determinable' },
  'custom-character-key-shortcuts': { mode: 'static',    fallbackDescription: 'Single character key shortcuts must be remappable or disableable' },
  'custom-pointer-cancellation':  { mode: 'static',      fallbackDescription: 'Functionality that uses a single pointer must be cancellable' },
  'custom-dragging-movements':    { mode: 'static',      fallbackDescription: 'Dragging movements must have a single-pointer alternative' },
  'custom-pointer-gestures':      { mode: 'static',      fallbackDescription: 'Complex gestures must have a single-pointer alternative' },
  'custom-motion-actuation':      { mode: 'static',      fallbackDescription: 'Motion-based functionality must have a UI alternative and be disableable' },
  'custom-consistent-help':       { mode: 'static',      fallbackDescription: 'Help mechanisms must appear in a consistent location across pages' },
  'custom-error-suggestion':      { mode: 'static',      fallbackDescription: 'Error messages must suggest how to correct mistakes' },
  'custom-error-prevention':      { mode: 'static',      fallbackDescription: 'High-risk submissions must be reversible, checked, or confirmed' },
  'custom-redundant-entry':       { mode: 'static',      fallbackDescription: 'Information previously entered in a process should not need to be entered again' },
  'custom-accessible-auth':       { mode: 'static',      fallbackDescription: 'Authentication must not rely solely on cognitive function tests' },
  'custom-use-of-color':          { mode: 'static',      fallbackDescription: 'Color must not be the only visual means of conveying information' },
  'custom-audio-transcript':      { mode: 'static',      fallbackDescription: 'Audio-only prerecorded content must have a text alternative' },
  'custom-captions-prerecorded':  { mode: 'static',      fallbackDescription: 'Prerecorded video content must have captions' },
  'custom-captions-live':         { mode: 'static',      fallbackDescription: 'Live audio or live video content must have real-time captions' },
  'custom-audio-description':     { mode: 'static',      fallbackDescription: 'Prerecorded synchronized media must have an audio description or full-text alternative' },
  'custom-audio-control':         { mode: 'static',      fallbackDescription: 'Audio that plays automatically for more than 3 seconds must have a pause/stop/volume control' },
  'custom-link-purpose':          { mode: 'static',      fallbackDescription: 'Link purpose must be determinable from link text alone' },
  'custom-location':              { mode: 'static',      fallbackDescription: 'Users must be able to determine their location within a set of web pages' },
  'custom-orientation':           { mode: 'static',      fallbackDescription: 'Content must not restrict its view and operation to a single display orientation' },
  'custom-images-of-text':        { mode: 'static',      fallbackDescription: 'Images of text must not be used when real text can achieve the same visual presentation' },
  'custom-background-image-content': { mode: 'static',   fallbackDescription: 'CSS background images carrying meaningful content must have a text alternative' },
  'custom-focus-visible':                  { mode: 'interactive', fallbackDescription: 'Focusable elements must have a visible focus indicator' },
  'custom-focus-appearance':               { mode: 'interactive', fallbackDescription: 'Focus indicators must have sufficient area and contrast' },
  'custom-on-focus':                       { mode: 'interactive', fallbackDescription: 'Focusing an element must not trigger a context change' },
  'custom-on-input':                       { mode: 'interactive', fallbackDescription: 'Changing an input value must not trigger a context change' },
  'custom-keyboard-trap':                  { mode: 'interactive', fallbackDescription: 'Keyboard focus must not be trapped in a component' },
  'custom-audio-description-prerecorded':  { mode: 'static',      fallbackDescription: 'Prerecorded video must have an audio description track' },
  'custom-extended-audio-description':     { mode: 'static',      fallbackDescription: 'Prerecorded video must have extended audio description when pauses are insufficient' },
  'custom-media-alternative':              { mode: 'static',      fallbackDescription: 'Prerecorded synchronized media must have a full-text media alternative' },
  'custom-sensory-characteristics':        { mode: 'static',      fallbackDescription: 'Instructions must not rely solely on shape, color, size, visual location, or sound' },
  'custom-identify-purpose':               { mode: 'static',      fallbackDescription: 'The purpose of UI components, icons, and regions must be programmatically determinable' },
  'custom-visual-presentation':            { mode: 'static',      fallbackDescription: 'Blocks of text must allow user control of presentation (no justified text, adequate line spacing)' },
  'custom-images-of-text-no-exception':    { mode: 'static',      fallbackDescription: 'Images of text must not be used, with no exception for logos' },
  'custom-keyboard-no-exception':          { mode: 'static',      fallbackDescription: 'All functionality must be operable via keyboard with no exception' },
  'custom-animation-from-interactions':    { mode: 'static',      fallbackDescription: 'Motion animation triggered by interaction must be able to be disabled' },
  'custom-target-size-enhanced':           { mode: 'static',      fallbackDescription: 'Interactive targets must be at least 44×44 CSS pixels' },
  'custom-concurrent-input-mechanisms':    { mode: 'static',      fallbackDescription: 'Web content must not restrict use of input modalities available on a platform' },
  'custom-unusual-words':                  { mode: 'static',      fallbackDescription: 'A mechanism must be available for identifying definitions of unusual words and jargon' },
  'custom-abbreviations':                  { mode: 'static',      fallbackDescription: 'A mechanism must be available for identifying the expanded form of abbreviations' },
  'custom-reading-level':                  { mode: 'static',      fallbackDescription: 'Content should not require reading ability more advanced than lower secondary education' },
  'custom-help-mechanism':                 { mode: 'static',      fallbackDescription: 'If a web page requires user input, context-sensitive help must be available' },
  'custom-error-prevention-all':           { mode: 'static',      fallbackDescription: 'For all forms, submissions must be reversible, checked for errors, or confirmed' },
  'custom-accessible-auth-enhanced':       { mode: 'static',      fallbackDescription: 'Authentication must not require cognitive function tests, including blocking copy-paste' },
  'custom-reflow':                         { mode: 'interactive', fallbackDescription: 'Content must be accessible without horizontal scrolling at 320×256 CSS pixels' },
  'custom-content-on-hover-focus':         { mode: 'interactive', fallbackDescription: 'Content that appears on hover or focus must be dismissible, hoverable, and persistent' },
  'custom-error-identification':           { mode: 'interactive', fallbackDescription: 'When an input error is detected, the errored item must be identified and described in text' },
  'custom-audio-only-live':               { mode: 'static',      fallbackDescription: 'Live audio-only content must have a text alternative presenting equivalent information' },
  'custom-three-flashes':                 { mode: 'static',      fallbackDescription: 'Pages must not contain anything that flashes more than three times per second' },
  'custom-three-flashes-no-exception':    { mode: 'static',      fallbackDescription: 'Pages must not contain anything that flashes more than three times per second (no size exception)' },
  'custom-consistent-navigation':               { mode: 'static',      fallbackDescription: 'Navigation mechanisms repeated on multiple pages must appear in the same relative order' },
  'custom-consistent-identification':           { mode: 'static',      fallbackDescription: 'Components with the same functionality must be identified consistently' },
  'custom-change-on-request':                   { mode: 'static',      fallbackDescription: 'Changes of context must be initiated only by user request, not automatically' },
  'custom-contrast-enhanced':                   { mode: 'static',      fallbackDescription: 'Text must have a contrast ratio of at least 7:1 (normal text) or 4.5:1 (large text)' },
  'custom-text-spacing':                        { mode: 'static',      fallbackDescription: 'Content must not lose information when line height, letter spacing, word spacing, or paragraph spacing is overridden' },
  'custom-pause-stop-hide':                     { mode: 'static',      fallbackDescription: 'Moving, blinking, or auto-updating content must be pausable, stoppable, or hideable' },
  'custom-section-headings':                    { mode: 'static',      fallbackDescription: 'Section headings must be used to organize content' },
  'custom-focus-not-obscured':                  { mode: 'interactive', fallbackDescription: 'When a UI component receives keyboard focus, it must not be entirely hidden by author-created content' },
  'custom-focus-not-obscured-enhanced':         { mode: 'interactive', fallbackDescription: 'When a UI component receives keyboard focus, it must not be hidden at all by author-created content' },
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

function _buildContext(context = {}, page = null) {
  return {
    config: context && context.config ? context.config : loadSharedConfig(),
    lang: sanitizeLang(context && context.lang ? context.lang : 'en'),
    page,
  };
}

/**
 * Normalize the flexible 2nd/3rd arguments of the run* helpers.
 *
 * Accepts either:
 *   - (page, criteriaId, context)  → criteriaId is a WCAG SC string ("1.1.1")
 *   - (page, context)              → legacy form; context = { lang, config, criteriaId? }
 *
 * Returning a single criterion lets callers run ONLY the relevant check(s) for a
 * single-SC audit instead of running all checks and filtering afterwards.
 *
 * @returns {{ criteriaId: string|null, context: object }}
 */
function _parseRunArgs(criteriaIdOrContext, context) {
  if (criteriaIdOrContext && typeof criteriaIdOrContext === 'object') {
    return { criteriaId: criteriaIdOrContext.criteriaId || null, context: criteriaIdOrContext };
  }
  if (typeof criteriaIdOrContext === 'string') {
    return { criteriaId: criteriaIdOrContext || null, context: context || {} };
  }
  return { criteriaId: null, context: context || {} };
}

/**
 * Filter a list of check definitions down to those mapped to `criteriaId`.
 * A null/empty criterion means "run everything" (full audit).
 */
function _selectChecks(checkDefs, criteriaId) {
  if (!criteriaId) return checkDefs;
  return checkDefs.filter(d => d && d.check && d.check.SC === criteriaId);
}

async function _runChecks(checkDefs, page, context = {}) {
  const sharedContext = _buildContext(context, page);
  const results = await Promise.allSettled(checkDefs.map(d => d.check.run(page, sharedContext)));
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

async function runStaticChecks(page, criteriaIdOrContext = null, context = {}) {
  const { criteriaId, context: ctx } = _parseRunArgs(criteriaIdOrContext, context);
  return _runChecks(_selectChecks(STATIC_CHECKS, criteriaId), page, ctx);
}

async function runInteractiveChecks(page, criteriaIdOrContext = null, context = {}) {
  const { criteriaId, context: ctx } = _parseRunArgs(criteriaIdOrContext, context);
  const selected = _selectChecks(INTERACTIVE_CHECKS, criteriaId);
  if (selected.length === 0) return [];

  // Interactive checks must run sequentially (they mutate focus/keyboard/page state)
  const sharedContext = _buildContext(ctx, page);

  // Technique #3: Discover focusable set once and share across all 5 interactive checks
  const { discoverPageElements, FOCUSABLE_SELECTOR } = require('./sharedAssets');
  try {
    sharedContext.focusableElements = await discoverPageElements(page, FOCUSABLE_SELECTOR);
  } catch (err) {
    console.warn('[custom-checks] focusable element discovery failed:', err && err.message || err);
    sharedContext.focusableElements = [];
  }

  const results = [];
  for (let i = 0; i < selected.length; i++) {
    const checkDef = selected[i];
    try {
      results.push(await checkDef.check.run(page, sharedContext));
    } catch (err) {
      const name = _checkName(checkDef, i);
      console.warn(`[custom-checks] ${name} failed:`, err && err.message || err);
      results.push(_buildExecutionFailure(checkDef, err));
    }
  }
  return results;
}

async function runAll(page, criteriaIdOrContext = null, context = {}) {
  const { criteriaId, context: ctx } = _parseRunArgs(criteriaIdOrContext, context);
  // Deterministic order: static first, then interactive.
  // Running both in parallel on the same page can cause state interference.

  // Cooperative timeout: when ctx.timeoutMs is set, each phase races against
  // its own slice of the budget so a slow page that exceeded the previous
  // single overall Promise.race could lose ALL completed work. With the split
  // budget, a timed-out interactive phase still preserves static findings
  // (and vice-versa). 60/40 favours static because it's the larger phase.
  const timeoutMs = ctx && typeof ctx.timeoutMs === 'number' && ctx.timeoutMs > 0
    ? ctx.timeoutMs
    : null;

  if (!timeoutMs) {
    const staticR = await runStaticChecks(page, criteriaId, ctx);
    const interactiveR = await runInteractiveChecks(page, criteriaId, ctx);
    return [...staticR, ...interactiveR];
  }

  const staticBudget = Math.max(15_000, Math.floor(timeoutMs * 0.6));
  const interactiveBudget = Math.max(15_000, timeoutMs - staticBudget);

  function _withTimeout(promise, ms, label) {
    let timer;
    const timeout = new Promise((_, reject) => {
      timer = setTimeout(
        () => reject(new Error(`${label} timed out after ${ms}ms`)),
        ms,
      );
    });
    return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
  }

  let staticR = [];
  const staticStart = Date.now();
  try {
    staticR = await _withTimeout(
      runStaticChecks(page, criteriaId, ctx), staticBudget, 'static custom checks'
    );
  } catch (err) {
    // Note: the WARN level makes this visible in the timing summary as the
    // reason a page only returned partial custom-check findings. The
    // split-budget design (60/40) ensures the other phase still ran.
    console.warn(
      `[custom-checks] static phase hit ${staticBudget}ms cap after ` +
      `${Date.now() - staticStart}ms — partial results returned. ` +
      `Increase CUSTOM_CHECKS_TIMEOUT_MS if this site needs full coverage.`
    );
  }

  let interactiveR = [];
  const interactiveStart = Date.now();
  try {
    interactiveR = await _withTimeout(
      runInteractiveChecks(page, criteriaId, ctx), interactiveBudget, 'interactive custom checks'
    );
  } catch (err) {
    console.warn(
      `[custom-checks] interactive phase hit ${interactiveBudget}ms cap after ` +
      `${Date.now() - interactiveStart}ms — partial results returned. ` +
      `Increase CUSTOM_CHECKS_TIMEOUT_MS if this site needs full coverage.`
    );
  }

  return [...staticR, ...interactiveR];
}

module.exports = {
  _loadCheckDefinitions,
  mergeWithAxe,
  runAll,
  runInteractiveChecks,
  runStaticChecks,
};
