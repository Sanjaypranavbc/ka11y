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
      _criteriaId: extractSuccessCriteriaId(rule.tags),
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
      _criteriaId: extractSuccessCriteriaId(rule.tags),
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
      _criteriaId: extractSuccessCriteriaId(rule.tags),
    };
  }

  const order = { fail: 0, incomplete: 1, pass: 2 };
  return Object.values(resultMap)
    .filter(r => !criteriaFilter || r._criteriaId === criteriaFilter)
    .sort((a, b) => (order[a.status] ?? 3) - (order[b.status] ?? 3))
    .map(({ _criteriaId, ...rest }) => rest);
}

/**
 * Extracts the WCAG Success Criterion numeric ID from axe-core rule tags.
 * e.g. ["wcag2a", "wcag111"] → "1.1.1"
 * e.g. ["wcag2aa", "wcag1412"] → "1.4.12"
 *
 * @param {Array<string>} tags - Rule tags from axe-core
 * @returns {string|null}
 */
function extractSuccessCriteriaId(tags) {
  const wcagTag = tags.find((tag) => /^wcag\d{3,}$/.test(tag));
  if (!wcagTag) return null;

  const digits = wcagTag.slice(4); // strip "wcag"
  if (digits.length === 3) return `${digits[0]}.${digits[1]}.${digits[2]}`;
  if (digits.length === 4) return `${digits[0]}.${digits[1]}.${digits.slice(2)}`;
  return null;
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
