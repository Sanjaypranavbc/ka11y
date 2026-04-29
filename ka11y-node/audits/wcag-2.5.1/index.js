/**
 * @fileoverview WCAG 2.5.1 Pointer Gestures — three-layer audit orchestrator.
 *
 * Layer 1 — axe-core custom rule: DOM selector matching with escape hatch checks.
 * Layer 2 — gesture event listener registry: runtime interception of addEventListener.
 * Layer 3 — escape hatch re-validation: per-element verification to reduce FPs from L2.
 *
 * Usage:
 *   import { auditPointerGestures } from './audits/wcag-2.5.1/index.js';
 *   const violations = await auditPointerGestures(page, { url: 'https://example.com' });
 */

import { createRequire } from 'module';
import { fileURLToPath } from 'url';
import path from 'path';

import { enSelectors, jaSelectors }           from './multilingual-selectors.js';
import { pointerGesturesRule, pointerGesturesCheck } from './axe-rule-pointer-gestures.js';
import { injectGestureDetector, extractGestureRegistry } from './gesture-listener-detector.js';
import { checkEscapeHatch }                   from './escape-hatch-checker.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const _require  = createRequire(import.meta.url);

/* Resolve absolute path to the bundled axe-core minified build. */
const AXE_PATH = _require.resolve('axe-core/axe.min.js');

const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/pointer-gestures';

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Constructs a canonical violation object.
 *
 * @param {Object} p
 * @returns {Object}
 */
function makeViolation({
  layer,
  lang,
  element       = null,
  selector,
  escapeHatchFound  = false,
  escapeHatchType   = null,
  message,
}) {
  return {
    ruleId:           'wcag-2.5.1-pointer-gestures',
    impact:           'serious',
    wcag:             '2.5.1',
    layer,
    lang,
    element:          element ? String(element).slice(0, 200) : null,
    selector,
    escapeHatchFound,
    escapeHatchType,
    message,
    helpUrl:          HELP_URL,
  };
}

/**
 * Detects page language, preferring an explicit override.
 *
 * @param {Object} page
 * @param {string} [override]
 * @returns {Promise<string>}
 */
async function detectLang(page, override) {
  if (override) return override;
  try {
    return await page.evaluate(() => document.documentElement.lang || '');
  } catch (_) {
    return '';
  }
}

/**
 * Navigates the page to a URL, handling Playwright ('networkidle') and Puppeteer
 * ('networkidle0') waitUntil option differences.
 *
 * @param {Object} page
 * @param {string} url
 * @returns {Promise<void>}
 */
async function navigateTo(page, url) {
  try {
    await page.goto(url, { waitUntil: 'networkidle' }); // Playwright
  } catch (playwrightErr) {
    if (!String(playwrightErr).includes('networkidle')) throw playwrightErr;
    await page.goto(url, { waitUntil: 'networkidle0' }); // Puppeteer fallback
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Runs the full WCAG 2.5.1 Pointer Gestures audit against a loaded page.
 *
 * The caller is responsible for:
 *   • Creating the browser/page object.
 *   • Calling injectGestureDetector(page) BEFORE page.goto() when using Layer 2.
 *     (This function does NOT call injectGestureDetector itself, because
 *      addInitScript / evaluateOnNewDocument must be called before navigation.)
 *   • If `options.url` is provided, this function navigates to it; otherwise the
 *     page must already be at the target URL.
 *
 * @param {Object}  page              - Playwright or Puppeteer Page object
 * @param {Object}  [options={}]
 * @param {string}  [options.url]     - Navigate to this URL before auditing
 * @param {string}  [options.lang]    - Override detected page language ('en'|'ja')
 * @param {boolean} [options.injectAxe=true] - Inject axe-core from node_modules
 * @returns {Promise<Array<Object>>}  Unified violations array (deduplicated by selector)
 */
export async function auditPointerGestures(page, options = {}) {
  const { url, lang: langOverride, injectAxe = true } = options;

  if (url) await navigateTo(page, url);

  const detectedLang = await detectLang(page, langOverride);
  const violations   = [];
  const seen         = new Set(); // deduplicates entries across all layers by selector

  // ── Layer 1: axe-core custom rule ──────────────────────────────────────────
  try {
    if (injectAxe) {
      await page.addScriptTag({ path: AXE_PATH });
    }

    /*
     * The evaluate function must be serialised to a string and reconstructed
     * inside the browser via new Function(), because page.evaluate() cannot
     * transfer live function references across the Node↔browser boundary.
     */
    const evaluateFnStr = `(${pointerGesturesCheck.evaluate.toString()})`;

    const axeResults = await page.evaluate(
      (rule, checkId, evalStr, enSel, jaSel) => {
        axe.configure({
          rules: [rule],
          checks: [{
            id:       checkId,
            // eslint-disable-next-line no-new-func
            evaluate: new Function('return ' + evalStr)(),
            options:  { enSelectors: enSel, jaSelectors: jaSel },
          }],
        });
        return axe.run(document, {
          runOnly: { type: 'rule', values: [rule.id] },
        });
      },
      pointerGesturesRule,
      pointerGesturesCheck.id,
      evaluateFnStr,
      enSelectors,
      jaSelectors,
    );

    for (const v of axeResults.violations) {
      for (const node of v.nodes) {
        const checkData   = node.any?.[0]?.data || {};
        const subViolations = Array.isArray(checkData.violations) && checkData.violations.length > 0
          ? checkData.violations
          : [{ selector: (node.target?.[0] || 'body'), element: node.html, matchedCategory: 'unknown' }];

        for (const sv of subViolations) {
          if (seen.has(sv.selector)) continue;
          seen.add(sv.selector);
          violations.push(makeViolation({
            layer:   'layer-1',
            lang:    checkData.lang || detectedLang,
            element: sv.element,
            selector: sv.selector,
            escapeHatchFound: false,
            message: `Gesture-only widget (${sv.matchedCategory}) matched by axe rule — no single-pointer alternative found`,
          }));
        }
      }
    }
  } catch (err) {
    console.warn('[wcag-2.5.1] Layer 1 (axe-core) skipped:', err.message);
  }

  // ── Layer 2: gesture event listener registry ───────────────────────────────
  let layer2Registry = [];
  try {
    layer2Registry = await extractGestureRegistry(page);

    for (const entry of layer2Registry) {
      if (entry.hasClickAlternative) continue; // has a usable alternative
      if (seen.has(entry.selector)) continue;
      seen.add(entry.selector);
      violations.push(makeViolation({
        layer:   'layer-2',
        lang:    detectedLang,
        element: null,
        selector: entry.selector,
        escapeHatchFound: false,
        message: `Element registers gesture events [${entry.events.join(', ')}] with no click/keyboard alternative`,
      }));
    }
  } catch (err) {
    console.warn('[wcag-2.5.1] Layer 2 (gesture registry) skipped:', err.message);
  }

  // ── Layer 3: escape hatch re-validation (Layer 2 violations only) ──────────
  // Layer 1 already performs inline escape hatch checks during axe evaluation.
  // Layer 3 re-checks only Layer 2 results to reduce false positives.
  const layer2ViolationSelectors = layer2Registry
    .filter(e => !e.hasClickAlternative && seen.has(e.selector))
    .map(e => e.selector);

  for (const sel of layer2ViolationSelectors) {
    try {
      const hatch = await checkEscapeHatch(page, sel);
      if (!hatch.found) continue;

      const existing = violations.find(v => v.selector === sel && v.layer === 'layer-2');
      if (existing) {
        existing.escapeHatchFound = true;
        existing.escapeHatchType  = hatch.type;
        existing.layer            = 'layer-3';
        existing.message          = `[Layer 3 re-validated] Escape hatch found (${hatch.type}): ${hatch.detail}`;
      }
    } catch (_) {
      // checkEscapeHatch is best-effort; a failure is non-fatal
    }
  }

  return violations;
}
