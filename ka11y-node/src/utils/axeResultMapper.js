













































































'use strict';

const rulesGuide = require('./rulesGuide');
const {
  BEST_PRACTICE_ID,
  BEST_PRACTICE_NAME,
  WCAG_LEVEL,
  WCAG_NAMES,
} = require('./wcagMetadata');
const { getRules } = require('./rulesLoader');

// English rules loaded once at startup — used for suggested_fix lookups.
const _enRules = getRules('en');

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
      _criteriaId: _normalizeCriterionId(extractSuccessCriteriaId(rule.tags, rule.id), rule.id, rule.tags),
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
      _criteriaId: _normalizeCriterionId(extractSuccessCriteriaId(rule.tags, rule.id), rule.id, rule.tags),
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
      _criteriaId: _normalizeCriterionId(extractSuccessCriteriaId(rule.tags, rule.id), rule.id, rule.tags),
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

  // Target size
  'target-size': '2.5.8',

  // Colour contrast
  'color-contrast-enhanced': '1.4.6',

  // Links / navigation
  'identical-links-same-purpose': '2.4.9',

  // Focus / keyboard
  'focus-order-semantics':       '2.4.3',
  'scrollable-region-focusable': '2.1.1',
  'accesskeys':                  '2.1.1',

  // Tables
  'table-duplicate-name': '1.3.1',

  // ARIA field names
  'aria-input-field-name':  '4.1.2',
  'aria-toggle-field-name': '4.1.2',

  // Additional best-practice rules with clear WCAG mapping
  'aria-dialog-name':    '4.1.2',
  'aria-treeitem-name':  '4.1.2',
  'skip-link':           '2.4.1',

  // WCAG 2.2 rules (active after adding wcag22a/wcag22aa tags to runOnly)
  'focus-appearance':   '2.4.13',
  'focus-visible':      '2.4.7',
  'target-size':        '2.5.8',   // already mapped, kept explicit for WCAG 2.2 tag
  'duplicate-id':       '4.1.1',   // still runs in axe 4.9+ under wcag2a-obsolete tag
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
  const id = _normalizeCriterionId(extractSuccessCriteriaId(tags), '', tags);
  if (!id) return null;
  if (id === BEST_PRACTICE_ID) return BEST_PRACTICE_NAME;
  return `WCAG ${id}`;
}

function _normalizeCriterionId(sc, ruleId, tags = []) {
  if (sc) return sc;
  if (Array.isArray(tags) && tags.includes('best-practice')) return BEST_PRACTICE_ID;
  const guide = ruleId && rulesGuide[ruleId];
  if (guide && guide.wcagLevel === 'best-practice') return BEST_PRACTICE_ID;
  return null;
}

function _criterionName(sc, ruleId, fallbackName = null) {
  if (!sc) return null;
  if (sc === BEST_PRACTICE_ID) {
    const guide = rulesGuide[ruleId];
    return (guide && guide.title) || fallbackName || BEST_PRACTICE_NAME;
  }
  return WCAG_NAMES[sc] || null;
}

function _criterionLevel(sc) {
  if (!sc || sc === BEST_PRACTICE_ID) return null;
  return WCAG_LEVEL[sc] || null;
}

function _suggestedFix(sc, ruleId) {
  if (sc && sc !== BEST_PRACTICE_ID) {
    const yamlFix = _enRules[sc] && _enRules[sc].suggested_fix;
    if (yamlFix) return yamlFix;
  }
  const guide = rulesGuide[ruleId];
  return (guide && guide.fixTip) || null;
}

/**
 * Returns a flat, element-wise array of findings — one entry per failing /
 * incomplete *node* (element), one entry per passing *rule*.
 *
 * Finding shape:
 * {
 *   source:        "axe",
 *   rule_id:       "image-alt",
 *   wcag_sc:       "1.1.1"  | null,
 *   criterion_name: "Non-text Content" | null,
 *   level:         "A" | "AA" | "AAA" | null,
 *   severity:      "critical" | "high" | "medium" | "low" | null,
 *   status:        "fail" | "pass" | "needs_review",
 *   reason:        "...",
 *   suggested_fix: "...",
 *   help_url:      "https://...",
 *   element: {
 *     html:       "<img src='...'>",
 *     element_id: "logo" | null,
 *     tag:        "IMG" | null,
 *     target:     ["#logo"] | [],
 *     page_url:   null   // filled by caller
 *   } | null
 * }
 *
 * @param {object} axeResults - Raw result from axe.run()
 * @param {string} pageUrl    - URL of the page (for element.page_url)
 * @returns {Array<object>}
 */
function mapResultsFlat(axeResults, pageUrl = null) {
  const findings = [];

  const IMPACT_TO_SEVERITY = {
    critical: 'critical',
    serious:  'high',
    moderate: 'medium',
    minor:    'low',
  };

  function extractIdFromTarget(target) {
    if (!Array.isArray(target) || target.length === 0) return null;
    const sel = target[0];
    if (typeof sel !== 'string') return null;
    const m = sel.match(/#([\w-]+)/);
    return m ? m[1] : null;
  }

  function extractTag(html) {
    if (!html) return null;
    const m = html.match(/^<(\w+)/);
    return m ? m[1].toUpperCase() : null;
  }

  function cleanReason(summary, fallback) {
    if (summary) return summary.replace(/^Fix (?:any|all) of the following:\s*/i, '').trim();
    return fallback || '';
  }

  // ── violations → one finding per node ────────────────────────────────────
  for (const rule of axeResults.violations) {
    const sc  = _normalizeCriterionId(extractSuccessCriteriaId(rule.tags, rule.id), rule.id, rule.tags);
    const sev = IMPACT_TO_SEVERITY[rule.impact] || null;
    for (const node of (rule.nodes || [])) {
      const html = (node.html || '').slice(0, 600);
      findings.push({
        source:         'axe',
        rule_id:        rule.id,
        wcag_sc:        sc,
        criterion_name: _criterionName(sc, rule.id, rule.description || null),
        level:          _criterionLevel(sc),
        severity:       sev,
        status:         'fail',
        reason:         cleanReason(node.failureSummary, rule.help),
        suggested_fix:  _suggestedFix(sc, rule.id),
        help_url:       rule.helpUrl,
        element: {
          html:       html,
          element_id: node.element_id || extractIdFromTarget(node.target) || null,
          tag:        extractTag(html),
          target:     node.target || [],
          page_url:   pageUrl,
        },
      });
    }
  }

  // ── incomplete → one finding per node ────────────────────────────────────
  for (const rule of (axeResults.incomplete || [])) {
    const sc  = _normalizeCriterionId(extractSuccessCriteriaId(rule.tags, rule.id), rule.id, rule.tags);
    const sev = IMPACT_TO_SEVERITY[rule.impact] || null;
    for (const node of (rule.nodes || [])) {
      const html = (node.html || '').slice(0, 600);
      findings.push({
        source:         'axe',
        rule_id:        rule.id,
        wcag_sc:        sc,
        criterion_name: _criterionName(sc, rule.id, rule.description || null),
        level:          _criterionLevel(sc),
        severity:       sev,
        status:         'needs_review',
        reason:         cleanReason(node.failureSummary, rule.help),
        suggested_fix:  _suggestedFix(sc, rule.id),
        help_url:       rule.helpUrl,
        element: {
          html:       html,
          element_id: node.element_id || extractIdFromTarget(node.target) || null,
          tag:        extractTag(html),
          target:     node.target || [],
          page_url:   pageUrl,
        },
      });
    }
  }

  // ── passes → one finding per rule (not per element — too verbose) ─────────
  for (const rule of axeResults.passes) {
    const sc = _normalizeCriterionId(extractSuccessCriteriaId(rule.tags, rule.id), rule.id, rule.tags);
    findings.push({
      source:         'axe',
      rule_id:        rule.id,
      wcag_sc:        sc,
      criterion_name: _criterionName(sc, rule.id, rule.description || null),
      level:          _criterionLevel(sc),
      severity:       null,
      status:         'pass',
      reason:         rule.help,
      suggested_fix:  null,
      help_url:       rule.helpUrl,
      element:        null,
    });
  }

  // Sort: fail → needs_review → pass
  const ORDER = { fail: 0, needs_review: 1, pass: 2 };
  findings.sort((a, b) => (ORDER[a.status] ?? 3) - (ORDER[b.status] ?? 3));

  return findings;
}

/**
 * Converts grouped custom-check output into flat findings.
 *
 * Input shape:
 * [
 *   {
 *     successCriteriaId: "2.4.7",
 *     rules: [{ ruleId, impact, status, reason, helpUrl, ... }]
 *   }
 * ]
 *
 * Output shape matches mapResultsFlat findings.
 *
 * @param {Array<object>} customResults
 * @param {string} pageUrl
 * @returns {Array<object>}
 */
function mapCustomResultsFlat(customResults, pageUrl = null) {
  const findings = [];

  const IMPACT_TO_SEVERITY = {
    critical: 'critical',
    serious:  'high',
    moderate: 'medium',
    minor:    'low',
  };

  const STATUS_MAP = {
    fail: 'fail',
    failed: 'fail',
    pass: 'pass',
    passed: 'pass',
    incomplete: 'needs_review',
    needs_review: 'needs_review',
    warning: 'needs_review',
    info: 'needs_review',
    manual_review: 'needs_review',
  };

  for (const result of (customResults || [])) {
    const sc = _normalizeCriterionId(
      (result && typeof result.successCriteriaId === 'string')
        ? result.successCriteriaId
        : null,
      null,
      []
    );
    const rules = Array.isArray(result && result.rules) ? result.rules : [];

    for (const rule of rules) {
      const rawStatus = (rule && typeof rule.status === 'string')
        ? rule.status.trim().toLowerCase()
        : 'incomplete';
      const status = STATUS_MAP[rawStatus] || 'needs_review';
      const impact = rule && rule.impact ? rule.impact : null;

      findings.push({
        source:         'custom',
        rule_id:        (rule && rule.ruleId) || 'custom-unknown-rule',
        wcag_sc:        sc,
        criterion_name: _criterionName(sc, null, (rule && rule.description) || null),
        level:          _criterionLevel(sc),
        severity:       status === 'pass' ? null : (impact ? (IMPACT_TO_SEVERITY[impact] || null) : null),
        status:         status,
        reason:         (rule && rule.reason) || (rule && rule.description) || '',
        suggested_fix:  status === 'pass' ? null : _suggestedFix(sc, null),
        help_url:       (rule && rule.helpUrl) || null,
        element:        null,
      });
    }
  }

  // Sort: fail → needs_review → pass
  const ORDER = { fail: 0, needs_review: 1, pass: 2 };
  findings.sort((a, b) => (ORDER[a.status] ?? 3) - (ORDER[b.status] ?? 3));

  return findings;
}


module.exports = {
  mapResults,
  mapResultsFlat,
  mapCustomResultsFlat,
  formatSuccessCriterion,
  extractSuccessCriteriaId,
};
