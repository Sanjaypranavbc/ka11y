/**
 * @fileoverview Violation object factory for WCAG 2.5.1 Pointer Gestures.
 *
 * Produces a canonical violation record from raw finding + escape-hatch data.
 * All consumers of the audit module receive objects of this shape.
 */

const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/pointer-gestures';

/**
 * @typedef {Object} ViolationRecord
 * @property {string}   ruleId                  - Always "wcag-2.5.1-pointer-gestures"
 * @property {string}   wcag                    - "2.5.1"
 * @property {string}   wcagLevel               - "AA"
 * @property {string}   wcagVersion             - "2.2"
 * @property {string}   impact                  - "serious"
 * @property {string}   layer                   - "dom-pattern" | "library-detected" | "axe-rule"
 * @property {string}   pageUrl
 * @property {string}   pageLang
 * @property {string}   category                - Selector bank category name
 * @property {string|null} element              - outerHTML excerpt (may be null for library-only)
 * @property {string}   selector
 * @property {{ x: number, y: number, width: number, height: number }|null} boundingBox
 * @property {boolean}  escapeHatchFound
 * @property {string[]} escapeHatchEvidence
 * @property {string[]} gestureLibrariesDetected
 * @property {string}   message
 * @property {"violation"|"warning"} severity
 * @property {string}   helpUrl
 * @property {string}   timestamp               - ISO 8601 timestamp
 */

/**
 * Constructs a canonical violation object from raw finding + validation data.
 *
 * @param {Object} p
 * @param {import('./dom-inspector.js').DOMFinding} p.finding
 * @param {{ hasAlternative: boolean, evidence: string[] }} p.escapeHatch
 * @param {Set<string>} p.detectedLibraries
 * @param {string}  p.pageUrl
 * @param {string}  p.pageLang
 * @param {"dom-pattern"|"library-detected"|"axe-rule"} p.layer
 * @returns {ViolationRecord}
 */
export function buildViolation({ finding, escapeHatch, detectedLibraries, pageUrl, pageLang, layer }) {
  const libs = [...(detectedLibraries || [])];

  const message = escapeHatch.hasAlternative
    ? `Gesture-dependent widget detected (${finding.category}) — single-pointer alternative present but verify manually`
    : `Gesture-dependent widget detected (${finding.category}) — no single-pointer alternative found`;

  return {
    ruleId:                   'wcag-2.5.1-pointer-gestures',
    wcag:                     '2.5.1',
    wcagLevel:                'AA',
    wcagVersion:              '2.2',
    impact:                   'serious',
    layer:                    layer,
    pageUrl:                  pageUrl,
    pageLang:                 pageLang,
    category:                 finding.category,
    element:                  finding.outerHTML || null,
    selector:                 finding.selector,
    boundingBox:              finding.boundingBox || null,
    escapeHatchFound:         escapeHatch.hasAlternative,
    escapeHatchEvidence:      escapeHatch.evidence || [],
    gestureLibrariesDetected: libs,
    message,
    severity:                 escapeHatch.hasAlternative ? 'warning' : 'violation',
    helpUrl:                  HELP_URL,
    timestamp:                new Date().toISOString(),
  };
}
