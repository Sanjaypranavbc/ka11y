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
    const sc  = extractSuccessCriteriaId(rule.tags, rule.id);
    const sev = IMPACT_TO_SEVERITY[rule.impact] || null;
    for (const node of (rule.nodes || [])) {
      const html = (node.html || '').slice(0, 600);
      findings.push({
        source:         'axe',
        rule_id:        rule.id,
        wcag_sc:        sc,
        criterion_name: sc ? (WCAG_NAMES[sc] || null) : null,
        level:          sc ? (WCAG_LEVEL[sc]  || null) : null,
        severity:       sev,
        status:         'fail',
        reason:         cleanReason(node.failureSummary, rule.help),
        suggested_fix:  SUGGESTED_FIX[sc] || null,
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
    const sc  = extractSuccessCriteriaId(rule.tags, rule.id);
    const sev = IMPACT_TO_SEVERITY[rule.impact] || null;
    for (const node of (rule.nodes || [])) {
      const html = (node.html || '').slice(0, 600);
      findings.push({
        source:         'axe',
        rule_id:        rule.id,
        wcag_sc:        sc,
        criterion_name: sc ? (WCAG_NAMES[sc] || null) : null,
        level:          sc ? (WCAG_LEVEL[sc]  || null) : null,
        severity:       sev,
        status:         'needs_review',
        reason:         cleanReason(node.failureSummary, rule.help),
        suggested_fix:  SUGGESTED_FIX[sc] || null,
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
    const sc = extractSuccessCriteriaId(rule.tags, rule.id);
    findings.push({
      source:         'axe',
      rule_id:        rule.id,
      wcag_sc:        sc,
      criterion_name: sc ? (WCAG_NAMES[sc] || null) : null,
      level:          sc ? (WCAG_LEVEL[sc]  || null) : null,
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

// ── Static metadata tables used by mapResultsFlat ─────────────────────────────

const WCAG_NAMES = {
  '1.1.1': 'Non-text Content',
  '1.2.1': 'Audio-only and Video-only (Prerecorded)',
  '1.2.2': 'Captions (Prerecorded)',
  '1.2.3': 'Audio Description or Media Alternative (Prerecorded)',
  '1.3.1': 'Info and Relationships',
  '1.3.2': 'Meaningful Sequence',
  '1.3.3': 'Sensory Characteristics',
  '1.4.1': 'Use of Color',
  '1.4.2': 'Audio Control',
  '2.1.1': 'Keyboard',
  '2.1.2': 'No Keyboard Trap',
  '2.1.4': 'Character Key Shortcuts',
  '2.2.1': 'Timing Adjustable',
  '2.2.2': 'Pause, Stop, Hide',
  '2.3.1': 'Three Flashes or Below Threshold',
  '2.4.1': 'Bypass Blocks',
  '2.4.2': 'Page Titled',
  '2.4.3': 'Focus Order',
  '2.4.4': 'Link Purpose (In Context)',
  '2.5.1': 'Pointer Gestures',
  '2.5.2': 'Pointer Cancellation',
  '2.5.3': 'Label in Name',
  '2.5.4': 'Motion Actuation',
  '3.1.1': 'Language of Page',
  '3.2.1': 'On Focus',
  '3.2.2': 'On Input',
  '3.3.1': 'Error Identification',
  '3.3.2': 'Labels or Instructions',
  '3.3.7': 'Redundant Entry',
  '4.1.1': 'Parsing',
  '4.1.2': 'Name, Role, Value',
  '1.2.4': 'Captions (Live)',
  '1.2.5': 'Audio Description (Prerecorded)',
  '1.3.4': 'Orientation',
  '1.3.5': 'Identify Input Purpose',
  '1.4.3': 'Contrast (Minimum)',
  '1.4.4': 'Resize Text',
  '1.4.5': 'Images of Text',
  '1.4.10': 'Reflow',
  '1.4.11': 'Non-text Contrast',
  '1.4.12': 'Text Spacing',
  '1.4.13': 'Content on Hover or Focus',
  '2.4.5': 'Multiple Ways',
  '2.4.6': 'Headings and Labels',
  '2.4.7': 'Focus Visible',
  '2.4.11': 'Focus Not Obscured (Minimum)',
  '2.4.13': 'Focus Appearance',
  '2.5.7': 'Dragging Movements',
  '2.5.8': 'Target Size (Minimum)',
  '3.1.2': 'Language of Parts',
  '3.2.3': 'Consistent Navigation',
  '3.2.4': 'Consistent Identification',
  '3.2.6': 'Consistent Help',
  '3.3.3': 'Error Suggestion',
  '3.3.4': 'Error Prevention (Legal, Financial, Data)',
  '3.3.8': 'Accessible Authentication (Minimum)',
  '4.1.3': 'Status Messages',
};

const WCAG_LEVEL = {
  '1.1.1': 'A',  '1.2.1': 'A',  '1.2.2': 'A',  '1.2.3': 'A',
  '1.3.1': 'A',  '1.3.2': 'A',  '1.3.3': 'A',
  '1.4.1': 'A',  '1.4.2': 'A',
  '2.1.1': 'A',  '2.1.2': 'A',  '2.1.4': 'A',
  '2.2.1': 'A',  '2.2.2': 'A',  '2.3.1': 'A',
  '2.4.1': 'A',  '2.4.2': 'A',  '2.4.3': 'A',  '2.4.4': 'A',
  '2.5.1': 'A',  '2.5.2': 'A',  '2.5.3': 'A',  '2.5.4': 'A',
  '3.1.1': 'A',  '3.2.1': 'A',  '3.2.2': 'A',
  '3.3.1': 'A',  '3.3.2': 'A',  '3.3.7': 'A',
  '4.1.1': 'A',  '4.1.2': 'A',
  '1.2.4': 'AA', '1.2.5': 'AA', '1.3.4': 'AA', '1.3.5': 'AA',
  '1.4.3': 'AA', '1.4.4': 'AA', '1.4.5': 'AA',
  '1.4.10': 'AA', '1.4.11': 'AA', '1.4.12': 'AA', '1.4.13': 'AA',
  '2.4.5': 'AA', '2.4.6': 'AA', '2.4.7': 'AA',
  '2.4.11': 'AA', '2.4.13': 'AA',
  '2.5.7': 'AA', '2.5.8': 'AA',
  '3.1.2': 'AA', '3.2.3': 'AA', '3.2.4': 'AA', '3.2.6': 'AA',
  '3.3.3': 'AA', '3.3.4': 'AA', '3.3.8': 'AA',
  '4.1.3': 'AA',
};

const SUGGESTED_FIX = {
  '1.1.1':  "Add a descriptive alt attribute: <img alt='Description of image'>. For decorative images use alt=''.",
  '1.3.1':  "Use semantic HTML (headings, lists, tables). Add appropriate ARIA landmark roles where needed.",
  '1.3.5':  "Add autocomplete attributes: <input autocomplete='email'>.",
  '1.4.1':  "Do not use colour as the only visual means to convey information. Add text labels or patterns.",
  '1.4.2':  "Provide a mechanism to pause or stop auto-playing audio, or ensure it stops within 3 seconds.",
  '1.4.3':  "Ensure text has a contrast ratio of at least 4.5:1 (3:1 for large text ≥ 18pt or bold 14pt).",
  '1.4.4':  "Remove CSS that blocks zoom. Ensure content reflows at 200% zoom without horizontal scrolling.",
  '1.4.11': "Ensure UI components (borders, icons, focus rings) have at least 3:1 contrast against adjacent colours.",
  '1.4.12': "Do not use CSS that prevents line-height, letter-spacing, or word-spacing overrides.",
  '2.1.1':  "Ensure all functionality is operable via keyboard alone. Avoid onclick-only handlers and positive tabindex.",
  '2.1.2':  "Ensure keyboard users can move focus away from any component without requiring specific key sequences.",
  '2.2.2':  "Add a visible Pause/Stop button for any auto-playing content lasting more than 5 seconds.",
  '2.4.1':  "Add a skip link as the first focusable element: <a href='#main'>Skip to main content</a>.",
  '2.4.2':  "Add a descriptive <title> element: <title>Page Name — Site Name</title>.",
  '2.4.3':  "Ensure focus order follows a logical reading order. Remove positive tabindex values.",
  '2.4.4':  "Replace generic link text ('Click here', 'Read more') with descriptive text that makes sense in isolation.",
  '2.4.6':  "Use heading levels (h1–h6) hierarchically to describe page sections. Provide visible labels for form groups.",
  '2.4.7':  "Ensure all focusable elements have a clearly visible focus indicator (outline or border change).",
  '2.5.3':  "Ensure the accessible name (aria-label / aria-labelledby) contains the visible label text verbatim.",
  '2.5.8':  "Increase the target size to at least 24×24 CSS pixels, or add padding so the clickable area reaches that size.",
  '3.1.1':  "Add a lang attribute to <html>: <html lang='en'>.",
  '3.1.2':  "Add lang attributes to inline content in a different language: <span lang='fr'>Bonjour</span>.",
  '3.2.3':  "Keep navigation menus in the same order across all pages of the site.",
  '3.3.1':  "Associate error messages with inputs using aria-describedby or aria-errormessage.",
  '3.3.2':  "Add a visible <label> or aria-label to every form input. Do not rely on placeholder text alone.",
  '4.1.1':  "Remove duplicate id attributes — each id must be unique within a page.",
  '4.1.2':  "Give every interactive element an accessible name, role, and value using native HTML or ARIA attributes.",
  '4.1.3':  "Wrap status messages in a live region: <div role='status' aria-live='polite'>...</div>.",
};

module.exports = { mapResults, mapResultsFlat, formatSuccessCriterion, extractSuccessCriteriaId };
