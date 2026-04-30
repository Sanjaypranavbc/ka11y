/**
 * @fileoverview DOM inspection layer for WCAG 2.5.1 Pointer Gestures.
 *
 * Queries the live page for elements matching every selector in the bank,
 * extracts metadata for each matched element, and deduplicates results.
 */

/**
 * @typedef {'carousels'|'draggable'|'mapEmbeds'|'touchGestureWidgets'|'pathBasedInteractions'} Category
 *
 * @typedef {Object} DOMFinding
 * @property {Category}   category    - Selector bank category that matched
 * @property {string}     selector    - Computed unique CSS path for the element
 * @property {string}     outerHTML   - outerHTML truncated to 300 characters
 * @property {{ x: number, y: number, width: number, height: number }|null} boundingBox
 * @property {string}     rawSelector - Raw selector string from the bank that matched
 */

const MAX_HTML_LENGTH = 300;
const CATEGORIES      = ['carousels', 'draggable', 'mapEmbeds', 'touchGestureWidgets', 'pathBasedInteractions'];

/* Pre-serialised body of the CSS-path helper (injected into page.evaluate via new Function). */
const CSS_PATH_FN_BODY = `
  if (!el || el.nodeType !== 1) return '';
  try { if (el.id) return '#' + CSS.escape(el.id); } catch (_) { if (el.id) return '#' + el.id; }
  const parts = [];
  let node = el;
  while (node && node.nodeType === 1 && node !== document.documentElement) {
    const tag = node.tagName.toLowerCase();
    let part = tag;
    try { if (node.id) { parts.unshift('#' + CSS.escape(node.id)); break; } } catch (_) {}
    const parent = node.parentElement;
    if (parent) {
      const siblings = Array.from(parent.children).filter(c => c.tagName === node.tagName);
      if (siblings.length > 1) part += ':nth-of-type(' + (siblings.indexOf(node) + 1) + ')';
    }
    parts.unshift(part);
    node = node.parentElement;
  }
  return parts.join(' > ') || el.tagName.toLowerCase();
`.trim();

/**
 * Queries every selector in the bank against the live page, collecting metadata
 * for each matched element.  Duplicate DOM elements (same computed CSS path) are
 * kept only once.
 *
 * @param {import('@playwright/test').Page|Object} page - Playwright/Puppeteer Page object
 * @param {import('./multilingual-selectors.js').SelectorBank} selectorBank
 * @returns {Promise<DOMFinding[]>}
 */
export async function inspectPage(page, selectorBank) {
  /** @type {DOMFinding[]} */
  const findings = [];
  /** @type {Set<string>} dedup by computed CSS path */
  const seen = new Set();

  for (const category of CATEGORIES) {
    const selectors = selectorBank[category];
    if (!Array.isArray(selectors) || selectors.length === 0) continue;

    for (const rawSelector of selectors) {
      let elements;
      try {
        elements = await page.$$(rawSelector);
      } catch (err) {
        console.warn(`[wcag-2.5.1] dom-inspector: invalid selector "${rawSelector}":`, err.message);
        continue;
      }

      for (const element of elements) {
        try {
          /* Compute a stable CSS path for the element by injecting helper into browser. */
          const cssPath = await page.evaluate(
            (node, fnBody) => {
              // eslint-disable-next-line no-new-func
              const cssPathOf = new Function('el', fnBody);
              return cssPathOf(node);
            },
            element,
            CSS_PATH_FN_BODY,
          ).catch(() => null);

          if (!cssPath) continue;
          if (seen.has(cssPath)) continue;
          seen.add(cssPath);

          const outerHTML = await page.evaluate(
            (node, max) => (node.outerHTML || '').slice(0, max),
            element,
            MAX_HTML_LENGTH,
          ).catch(() => '');

          const boundingBox = await element.boundingBox().catch(() => null);

          findings.push({ category, selector: cssPath, outerHTML, boundingBox, rawSelector });
        } catch (err) {
          console.warn(`[wcag-2.5.1] dom-inspector: element skipped for "${rawSelector}":`, err.message);
        }
      }
    }
  }

  return findings;
}
