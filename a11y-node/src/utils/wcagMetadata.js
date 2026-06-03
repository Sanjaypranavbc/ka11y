'use strict';

/**
 * wcagMetadata.js
 * ===============
 * Exports WCAG_NAMES and WCAG_LEVEL lookup maps, now sourced from the shared
 * i18n/rules.yml via rulesLoader.  The export shape is identical to before
 * so all existing callers continue to work without changes.
 */

const { getRules } = require('./rulesLoader');

const BEST_PRACTICE_ID   = 'best-practice';
const BEST_PRACTICE_NAME = 'Best Practice';

// Build lookup maps from the English base rules (loaded once at startup).
const _rules = getRules('en');

/** @type {Record<string, string>} WCAG SC ID → human-readable name */
const WCAG_NAMES = Object.fromEntries(
  Object.entries(_rules).map(([id, r]) => [id, r.name]),
);

/** @type {Record<string, string>} WCAG SC ID → conformance level (A / AA / AAA) */
const WCAG_LEVEL = Object.fromEntries(
  Object.entries(_rules).map(([id, r]) => [id, r.level]),
);

module.exports = {
  BEST_PRACTICE_ID,
  BEST_PRACTICE_NAME,
  WCAG_NAMES,
  WCAG_LEVEL,
};
