'use strict';

/**
 * Maps axe-core raw results into the structured response format.
 * Pure function — no I/O, no side effects.
 *
 * @param {object} axeResults        - Raw result from axe.run()
 * @param {string|null} criteriaFilter - Optional WCAG SC ID to filter by (e.g. "1.1.1")
 * @returns {Array<object>} Structured rule results sorted by severity
 */
function mapResults(axeResults, criteriaFilter = null) {
  const resultMap = {};

  // violations → status: "fail"
  for (const rule of axeResults.violations) {
    const node = rule.nodes[0] || {};
    resultMap[rule.id] = {
      ruleId:      rule.id,
      description: rule.description,
      impact:      rule.impact || null,
      status:      'fail',
      reason:      node.failureSummary
        ? node.failureSummary.replace(/^Fix (?:any|all) of the following:\s*/i, '').trim()
        : rule.help,
      helpUrl:     rule.helpUrl,
      _criteriaId: extractSuccessCriteriaId(rule.tags, rule.id),
    };
  }

  // passes → status: "pass" (skip if already marked as fail)
  for (const rule of axeResults.passes) {
    if (resultMap[rule.id]) continue;
    resultMap[rule.id] = {
      ruleId:      rule.id,
      description: rule.description,
      impact:      null,
      status:      'pass',
      reason:      rule.help,
      helpUrl:     rule.helpUrl,
      _criteriaId: extractSuccessCriteriaId(rule.tags, rule.id),
    };
  }

  // incomplete → status: "incomplete" (needs review)
  for (const rule of axeResults.incomplete || []) {
    if (resultMap[rule.id]) continue;
    const node = rule.nodes[0] || {};
    resultMap[rule.id] = {
      ruleId:      rule.id,
      description: rule.description,
      impact:      rule.impact || null,
      status:      'incomplete',
      reason:      node.failureSummary
        ? node.failureSummary.replace(/^Fix (?:any|all) of the following:\s*/i, '').trim()
        : rule.help,
      helpUrl:     rule.helpUrl,
      _criteriaId: extractSuccessCriteriaId(rule.tags, rule.id),
    };
  }

  const order = { fail: 0, incomplete: 1, pass: 2 };
  const flat = Object.values(resultMap)
    .filter(r => !criteriaFilter || r._criteriaId === criteriaFilter)
    .sort((a, b) => (order[a.status] ?? 3) - (order[b.status] ?? 3));

  // Group by successCriteriaId
  const grouped = {};
  for (const { _criteriaId, ...rule } of flat) {
    const key = _criteriaId ?? 'best-practice';
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(rule);
  }

  return Object.entries(grouped)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([successCriteriaId, rules]) => ({
      successCriteriaId,
      rules: rules.map(rule => {
        if (rule.impact === null) {
          const { impact, ...rest } = rule;
          return rest;
        }
        return rule;
      }),
    }));
}

/**
 * Fallback WCAG SC mapping for best-practice rules that carry no numeric SC tag.
 * Keyed by axe-core rule ID → closest WCAG 2.x Success Criterion.
 */
const RULE_SC_FALLBACK = {
  // Landmarks & structure
  'landmark-one-main':                 '1.3.1',
  'landmark-banner-is-top-level':      '1.3.1',
  'landmark-contentinfo-is-top-level': '1.3.1',
  'landmark-no-duplicate-banner':      '1.3.1',
  'landmark-no-duplicate-contentinfo': '1.3.1',
  'landmark-no-duplicate-main':        '1.3.1',
  'landmark-unique':                   '1.3.1',
  'region':                            '1.3.1',

  // Headings
  'empty-heading':      '2.4.6',
  'heading-order':      '1.3.1',
  'page-has-heading-one': '2.4.6',

  // Images
  'image-redundant-alt': '1.1.1',

  // ARIA
  'aria-allowed-role':        '4.1.2',
  'presentation-role-conflict': '4.1.2',

  // Keyboard / focus
  'tabindex': '2.4.3',

  // Viewport
  'meta-viewport-large': '1.4.4',
};

/**
 * Extracts the WCAG Success Criterion numeric ID from axe-core rule tags.
 * Falls back to RULE_SC_FALLBACK for best-practice rules with no numeric SC tag.
 * e.g. ["wcag2a", "wcag111"] → "1.1.1"
 * e.g. ["wcag2aa", "wcag1412"] → "1.4.12"
 *
 * @param {Array<string>} tags   - Rule tags from axe-core
 * @param {string}        ruleId - axe-core rule ID (used for fallback lookup)
 * @returns {string|null}
 */
function extractSuccessCriteriaId(tags, ruleId = '') {
  const wcagTag = tags.find((tag) => /^wcag\d{3,}$/.test(tag));

  if (wcagTag) {
    const digits = wcagTag.slice(4); // strip "wcag"
    if (digits.length === 3) return `${digits[0]}.${digits[1]}.${digits[2]}`;
    if (digits.length === 4) return `${digits[0]}.${digits[1]}.${digits.slice(2)}`;
  }

  return RULE_SC_FALLBACK[ruleId] ?? null;
}

/**
 * Formats WCAG tags into Success Criterion names.
 * e.g. "wcag1412" → "WCAG 1.4.12"
 *
 * @param {Array<string>} tags - Rule tags from axe-core
 * @returns {string|null}
 */
function formatSuccessCriterion(tags) {
  const id = extractSuccessCriteriaId(tags);
  if (!id) return null;
  return `WCAG ${id}`;
}

module.exports = { mapResults, formatSuccessCriterion, extractSuccessCriteriaId };
