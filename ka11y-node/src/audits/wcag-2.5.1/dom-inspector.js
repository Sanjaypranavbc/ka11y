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
 * @property {boolean}    hasCustomTouchAction - True if element has a non-default touch-action
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
 * Queries every selector in the bank against the live page in a SINGLE
 * page.evaluate round trip, collecting metadata for each matched element.
 * Duplicate DOM elements (same computed CSS path) are kept only once,
 * preferring the first category in CATEGORIES order.
 *
 * @param {import('@playwright/test').Page|Object} page - Playwright/Puppeteer Page object
 * @param {import('./multilingual-selectors.js').SelectorBank} selectorBank
 * @returns {Promise<DOMFinding[]>}
 */
async function inspectPage(page, selectorBank) {
  let result;
  try {
    result = await page.evaluate(
      ({ banks, categoriesOrder, fnBody, maxHtml }) => {
        // eslint-disable-next-line no-new-func
        const cssPathOf = new Function('el', fnBody);
        const invalid   = [];
        // Map: cssPath → element data. First insert wins, preserving CATEGORIES order.
        const seen = new Map();

        for (const category of categoriesOrder) {
          const selectorList = banks[category];
          if (!Array.isArray(selectorList) || selectorList.length === 0) continue;

          for (const rawSelector of selectorList) {
            let nodes;
            try {
              nodes = document.querySelectorAll(rawSelector);
            } catch (e) {
              invalid.push({ rawSelector, message: e && e.message });
              continue;
            }
            for (const node of nodes) {
              const cssPath = cssPathOf(node);
              if (!cssPath || seen.has(cssPath)) continue;
              const rect = node.getBoundingClientRect();
              seen.set(cssPath, {
                category,
                rawSelector,
                cssPath,
                outerHTML: (node.outerHTML || '').slice(0, maxHtml),
                touchAction: window.getComputedStyle(node).touchAction,
                boundingBox: rect && {
                  x: rect.x,
                  y: rect.y,
                  width: rect.width,
                  height: rect.height,
                },
              });
            }
          }
        }
        return { elements: Array.from(seen.values()), invalid };
      },
      {
        banks: selectorBank,
        categoriesOrder: CATEGORIES,
        fnBody: CSS_PATH_FN_BODY,
        maxHtml: MAX_HTML_LENGTH,
      },
    );
  } catch (err) {
    console.warn('[wcag-2.5.1] dom-inspector: evaluate threw:', err.message);
    return [];
  }

  for (const inv of result.invalid || []) {
    console.warn(`[wcag-2.5.1] dom-inspector: invalid selector "${inv.rawSelector}":`, inv.message);
  }

  /** @type {DOMFinding[]} */
  const findings = [];
  for (const item of result.elements || []) {
    const hasCustomTouchAction =
      item.touchAction === 'none' ||
      item.touchAction === 'pan-y' ||
      item.touchAction === 'pan-x';
    findings.push({
      category:    item.category,
      selector:    item.cssPath,
      outerHTML:   item.outerHTML || '',
      boundingBox: item.boundingBox || null,
      rawSelector: item.rawSelector,
      hasCustomTouchAction,
    });
  }
  return findings;
}
module.exports = { inspectPage };
