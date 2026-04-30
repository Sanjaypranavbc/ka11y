/**
 * @fileoverview Report adapter for WCAG 2.5.1 Pointer Gestures audit results.
 *
 * Converts the structured object returned by auditPointerGestures() into a flat
 * array of report-compatible objects that can be fed directly into the project's
 * existing report builder.
 */

/**
 * @typedef {Object} ReportItem
 * @property {string}  id        - Unique item id, e.g. "wcag-2.5.1-0"
 * @property {string}  rule      - "2.5.1 Pointer Gestures"
 * @property {string}  level     - "AA"
 * @property {"violation"|"warning"} severity
 * @property {string}  url       - Page URL
 * @property {string}  lang      - Detected page language
 * @property {string|null} element  - outerHTML excerpt
 * @property {string}  selector
 * @property {string}  message
 * @property {string}  helpUrl
 * @property {Object}  details
 * @property {string}  details.category
 * @property {boolean} details.escapeHatchFound
 * @property {string[]} details.escapeHatchEvidence
 * @property {string[]} details.gestureLibraries
 * @property {string}  details.layer
 * @property {{ x: number, y: number, width: number, height: number }|null} details.boundingBox
 */

/**
 * Adapts the result returned by auditPointerGestures() into a flat array of
 * report-compatible objects.  Both violations and warnings are included.
 *
 * @param {Object} auditResult - Result object from auditPointerGestures()
 * @returns {ReportItem[]}
 */
export function adaptToReportFormat(auditResult) {
  if (!auditResult || typeof auditResult !== 'object') return [];

  const allItems = [
    ...(auditResult.violations || []),
    ...(auditResult.warnings   || []),
  ];

  return allItems.map((item, index) => ({
    id:       `wcag-2.5.1-${index}`,
    rule:     '2.5.1 Pointer Gestures',
    level:    'AA',
    severity: item.severity,
    url:      item.pageUrl,
    lang:     item.pageLang,
    element:  item.element  || null,
    selector: item.selector || 'N/A',
    message:  item.message,
    helpUrl:  item.helpUrl,
    details: {
      category:            item.category,
      escapeHatchFound:    item.escapeHatchFound,
      escapeHatchEvidence: item.escapeHatchEvidence || [],
      gestureLibraries:    item.gestureLibrariesDetected || [],
      layer:               item.layer,
      boundingBox:         item.boundingBox || null,
    },
  }));
}
