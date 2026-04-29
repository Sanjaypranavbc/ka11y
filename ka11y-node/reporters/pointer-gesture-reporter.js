/**
 * @fileoverview Thin reporter adapter for WCAG 2.5.1 Pointer Gestures violations.
 *
 * Plug into an existing reporter chain by passing the array returned by
 * auditPointerGestures() to formatViolations() and selecting the desired format.
 */

/**
 * Formats a violations array for output or downstream consumption.
 *
 * @param {Array<Object>} violations
 *   Array returned by auditPointerGestures() from audits/wcag-2.5.1/index.js.
 * @param {"json"|"flat"|"grouped-by-lang"} reportFormat
 *   Output format:
 *   - "flat"           — returns the violations array as-is (no transformation)
 *   - "json"           — returns a JSON string with 2-space indent
 *   - "grouped-by-lang"— returns a plain object keyed by the `lang` field value
 * @returns {Array<Object>|string|Object}
 * @throws {Error} If reportFormat is not one of the three recognised values.
 */
export function formatViolations(violations, reportFormat) {
  switch (reportFormat) {
    case 'flat':
      return violations;

    case 'json':
      return JSON.stringify(violations, null, 2);

    case 'grouped-by-lang': {
      const groups = Object.create(null);
      for (const v of violations) {
        const key = v.lang || 'unknown';
        if (!groups[key]) groups[key] = [];
        groups[key].push(v);
      }
      return groups;
    }

    default:
      throw new Error(
        `formatViolations: unknown reportFormat "${reportFormat}". ` +
        'Valid values are "json", "flat", or "grouped-by-lang".'
      );
  }
}
