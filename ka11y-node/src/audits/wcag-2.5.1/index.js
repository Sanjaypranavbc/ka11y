/**
 * @fileoverview WCAG 2.5.1 Pointer Gestures — three-layer audit orchestrator.
 *
 * Layer "dom-pattern"     — CSS selector matching against the selector bank.
 * Layer "library-detected"— Gesture library fingerprinting with no DOM findings.
 * Layer "axe-rule"        — Custom axe-core rule for attribute-based detection.
 *
 * Usage:
 *   const { auditPointerGestures } = require('./src/audits/wcag-2.5.1/index.js');
 *   const result = await auditPointerGestures(page, { pageUrl, runAxeRule: true });
 */



const path = require('path');

const { getSelectorBank } = require('./multilingual-selectors.js');
const { detectGestureLibraries } = require('./gesture-library-detector.js');
const { inspectPage } = require('./dom-inspector.js');
const { validateEscapeHatch } = require('./escape-hatch-validator.js');
const { buildViolation } = require('./violation-builder.js');
const { pointerGestureRule, pointerGestureCheck } = require('./axe-rule-pointer-gestures.js');

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const _require  = createRequire(import.meta.url);

/* Resolve absolute path to bundled axe-core (used as fallback for addScriptTag). */
let _resolvedAxePath;
try {
  _resolvedAxePath = _require.resolve('axe-core/axe.min.js');
} catch (_) {
  _resolvedAxePath = path.join(__dirname, '..', '..', 'node_modules', 'axe-core', 'axe.min.js');
}

/* ── Internal helpers ───────────────────────────────────────────────────── */

/**
 * Detects the page language from the DOM.
 *
 * @param {Object} page
 * @returns {Promise<string>}
 */
async function _detectLang(page) {
  try {
    return await page.evaluate(() =>
      document.documentElement.lang ||
      document.querySelector('meta[http-equiv="content-language"]')?.content ||
      'en',
    );
  } catch (_) {
    return 'en';
  }
}

/**
 * Returns true if the page object is already closed / unusable.
 *
 * @param {Object} page
 * @returns {boolean}
 */
function _isClosed(page) {
  /* Playwright: page.isClosed() — Puppeteer: page._closed */
  if (typeof page.isClosed === 'function') return page.isClosed();
  if (page._closed === true) return true;
  return false;
}

/* ── Empty result factory ────────────────────────────────────────────────── */

/**
 * @param {string} pageUrl
 * @returns {Object}
 */
function _emptyResult(pageUrl) {
  return {
    pageUrl,
    pageLang: 'en',
    gestureLibrariesDetected: [],
    domFindingsCount: 0,
    violations: [],
    warnings:   [],
    summary: {
      total: 0, violations: 0, warnings: 0,
      layers: { domPattern: 0, libraryDetected: 0, axeRule: 0 },
    },
  };
}

/* ── Public API ─────────────────────────────────────────────────────────── */

/**
 * Runs the full WCAG 2.5.1 Pointer Gestures audit against a navigated page.
 *
 * The caller is responsible for navigating the page to the target URL before
 * calling this function.  If the page is already closed or an early step fails,
 * an empty result is returned gracefully.
 *
 * @param {import('@playwright/test').Page|Object} page - Playwright/Puppeteer Page object
 * @param {Object}  [options={}]
 * @param {string}  [options.pageUrl]        - URL string for the current page (metadata only)
 * @param {boolean} [options.runAxeRule=true] - Whether to run the custom axe-core rule
 * @param {string}  [options.axeScriptPath]  - Path to axe-core script for injection
 * @returns {Promise<Object>} Structured audit result
 */
async function auditPointerGestures(page, options = {}) {
  const {
    pageUrl      = '',
    runAxeRule   = true,
    axeScriptPath = _resolvedAxePath,
  } = options;

  if (_isClosed(page)) return _emptyResult(pageUrl);

  /* ── Step 1: Detect page language ──────────────────────────────────────── */
  const lang = await _detectLang(page);

  /* ── Step 2: Get selector bank ─────────────────────────────────────────── */
  const selectorBank = getSelectorBank(lang);

  /* ── Step 3: Detect gesture libraries ──────────────────────────────────── */
  const detectedLibraries = await detectGestureLibraries(page);

  /* ── Step 4: DOM inspection ─────────────────────────────────────────────── */
  let domFindings = [];
  try {
    domFindings = await inspectPage(page, selectorBank);
  } catch (err) {
    console.warn('[wcag-2.5.1] inspectPage failed:', err.message);
  }

  const allItems = [];

  /* ── Step 5: Validate each DOM finding ──────────────────────────────────── */
  for (const finding of domFindings) {
    const escapeHatch = await validateEscapeHatch(page, finding.selector).catch(
      () => ({ hasAlternative: false, evidence: [] }),
    );

    allItems.push(buildViolation({
      finding,
      escapeHatch,
      detectedLibraries,
      pageUrl,
      pageLang: lang,
      layer:    'dom-pattern',
    }));
  }

  /* ── Step 6: Library-level summary violation ────────────────────────────── */
  if (detectedLibraries.size > 0 && domFindings.length === 0) {
    allItems.push(buildViolation({
      finding: {
        category:    'library-only',
        selector:    'N/A',
        outerHTML:   null,
        boundingBox: null,
        rawSelector: 'N/A',
      },
      escapeHatch:       { hasAlternative: false, evidence: [] },
      detectedLibraries,
      pageUrl,
      pageLang: lang,
      layer:    'library-detected',
    }));
    // Override the message for library-only findings
    allItems[allItems.length - 1].message =
      `Gesture library detected: ${[...detectedLibraries].join(', ')} — manual gesture audit required`;
    allItems[allItems.length - 1].severity = 'warning';
  }

  /* ── Step 7 (optional): axe-core custom rule ──────────────────────────── */
  if (runAxeRule && !_isClosed(page)) {
    try {
      await page.addScriptTag({ path: axeScriptPath });

      const evaluateFnBody = pointerGestureCheck.evaluate.toString()
        .replace(/^function _evaluateBody\([^)]*\)\s*\{/, '')
        .replace(/\}$/, '')
        .trim();

      const axeViolations = await page.evaluate(
        (rule, checkId, evalFnBody, checkMeta, ruleMeta) => {
          // eslint-disable-next-line no-new-func
          const evaluateFn = new Function('node', 'options', evalFnBody);

          axe.configure({
            checks: [{
              id:       checkId,
              evaluate: evaluateFn,
              metadata: checkMeta,
            }],
            rules: [{
              id:       rule.id,
              selector: rule.selector,
              tags:     rule.tags,
              any:      rule.any,
              metadata: ruleMeta,
            }],
          });

          return axe.run(document, {
            runOnly: { type: 'rule', values: [rule.id] },
          }).then(results => results.violations);
        },
        pointerGestureRule,
        pointerGestureCheck.id,
        evaluateFnBody,
        pointerGestureCheck.metadata,
        pointerGestureRule.metadata,
      );

      for (const v of axeViolations) {
        for (const node of v.nodes) {
          const checkData = node.any?.[0]?.data || {};
          allItems.push(buildViolation({
            finding: {
              category:    checkData.gestureAttr || 'gesture-attribute',
              selector:    node.target?.[0] || 'body',
              outerHTML:   checkData.element || node.html || null,
              boundingBox: null,
              rawSelector: node.target?.[0] || 'body',
            },
            escapeHatch:       { hasAlternative: false, evidence: [] },
            detectedLibraries,
            pageUrl,
            pageLang: lang,
            layer:    'axe-rule',
          }));
        }
      }
    } catch (axeErr) {
      console.warn('[wcag-2.5.1] axe-core layer skipped:', axeErr.message);
    }
  }

  /* ── Step 8: Build and return result object ──────────────────────────── */
  const violations = allItems.filter(i => i.severity === 'violation');
  const warnings   = allItems.filter(i => i.severity === 'warning');

  const layers = { domPattern: 0, libraryDetected: 0, axeRule: 0 };
  for (const item of allItems) {
    if (item.layer === 'dom-pattern')      layers.domPattern++;
    else if (item.layer === 'library-detected') layers.libraryDetected++;
    else if (item.layer === 'axe-rule')    layers.axeRule++;
  }

  return {
    pageUrl,
    pageLang:                lang,
    gestureLibrariesDetected: [...detectedLibraries],
    domFindingsCount:         domFindings.length,
    violations,
    warnings,
    summary: {
      total:      allItems.length,
      violations: violations.length,
      warnings:   warnings.length,
      layers,
    },
  };
}

module.exports = {
  auditPointerGestures,
  getSelectorBank,
  detectGestureLibraries,
  validateEscapeHatch,
  buildViolation
};
h }     from './escape-hatch-validator.js';
export { buildViolation }          from './violation-builder.js';
module.exports = { auditPointerGestures };
;
