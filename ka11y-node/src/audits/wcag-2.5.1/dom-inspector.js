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
async function inspectPage(page, selectorBank) {
  /** @type {DOMFinding[]} */
  const findings = [];
  /** @type {Set<string>} dedup by computed CSS path (across all categories) */
  const seen = new Set();

  for (const category of CATEGORIES) {
    const selectors = selectorBank[category];
    if (!Array.isArray(selectors) || selectors.length === 0) continue;

    /* ONE round-trip per category: server-side iterates every selector,
       computes cssPath + outerHTML + touch-action + boundingBox inline.
       Drops the previous N-element × 3-evaluate pattern from
       O(matches × 3) IPC calls to O(categories) calls — a 1000×+ reduction
       on heavy pages. */
    let batch;
    try {
      batch = await page.evaluate(
        ({ selectorList, fnBody, maxHtml }) => {
          // eslint-disable-next-line no-new-func
          const cssPathOf = new Function('el', fnBody);
          const out = [];
          const invalid = [];
          for (const rawSelector of selectorList) {
            let nodes;
            try {
              nodes = document.querySelectorAll(rawSelector);
            } catch (e) {
              invalid.push({ rawSelector, message: e && e.message });
              continue;
            }
            for (const node of nodes) {
              const rect = node.getBoundingClientRect();
              out.push({
                rawSelector,
                cssPath: cssPathOf(node),
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
          return { elements: out, invalid };
        },
        { selectorList: selectors, fnBody: CSS_PATH_FN_BODY, maxHtml: MAX_HTML_LENGTH },
      );
    } catch (err) {
      console.warn(`[wcag-2.5.1] dom-inspector: evaluate threw for category "${category}":`, err.message);
      continue;
    }

    for (const inv of batch.invalid || []) {
      console.warn(`[wcag-2.5.1] dom-inspector: invalid selector "${inv.rawSelector}":`, inv.message);
    }

    for (const item of batch.elements || []) {
      const cssPath = item.cssPath;
      if (!cssPath || seen.has(cssPath)) continue;
      seen.add(cssPath);
      const hasCustomTouchAction =
        item.touchAction === 'none' ||
        item.touchAction === 'pan-y' ||
        item.touchAction === 'pan-x';
      findings.push({
        category,
        selector: cssPath,
        outerHTML: item.outerHTML || '',
        boundingBox: item.boundingBox || null,
        rawSelector: item.rawSelector,
        hasCustomTouchAction,
      });
    }
  }

  return findings;
}
module.exports = { inspectPage };
