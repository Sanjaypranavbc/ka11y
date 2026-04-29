/**
 * @fileoverview axe-core custom rule for WCAG 2.5.1 Pointer Gestures.
 *
 * The evaluate function must run inside the browser page context — axe-core
 * serialises it to a string and reconstructs it with new Function() before
 * injecting it via axe.configure(). As a result:
 *   • No import statements or Node.js APIs may appear inside the function body.
 *   • All input data is threaded through axe's `options` object (injected at
 *     configure-time by auditPointerGestures in index.js).
 */

/**
 * Evaluates the page body for gesture-only widgets that lack a single-pointer
 * alternative (escape hatch).  Called by axe-core with `this` bound to the
 * check context object, which provides this.data() for result storage.
 *
 * @param {Element} _node      - DOM element matched by the rule selector (body)
 * @param {Object}  options    - Check options injected by axe.configure()
 * @param {Object}  options.enSelectors - English selector bank
 * @param {Object}  options.jaSelectors - Japanese selector bank
 * @returns {boolean} true = no violations found; false = violations found
 */
function pointerGesturesEvaluate(_node, options) {
  const lang = (document.documentElement.lang || '').toLowerCase();
  const isJapanese = lang.startsWith('ja');
  const bank = isJapanese ? options.jaSelectors : options.enSelectors;

  const ALT_SEL        = 'button, [role="button"], a[href], input[type="button"], input[type="submit"]';
  const NAV_ARIA_SEL   = '[aria-controls], [aria-label], [aria-describedby]';
  const NAV_PATTERN    = /prev|next|forward|back|left|right|slide|scroll|navigate|arrow/i;

  const violations = [];

  // ── Gesture library global detection (window-level) ──────────────────────
  if (Array.isArray(bank.gestureLibraryGlobals)) {
    for (const globalName of bank.gestureLibraryGlobals) {
      if (typeof window[globalName] !== 'undefined') {
        violations.push({
          selector: 'window.' + globalName,
          matchedCategory: 'gestureLibraryGlobals',
          element: null,
          escapeHatchFound: false,
          escapeHatchPartial: false,
        });
      }
    }
  }

  // ── CSS selector categories ───────────────────────────────────────────────
  const categories = ['carousels', 'dragDrop', 'mapEmbeds', 'gestureWidgets'];
  const seen = new Set(); // prevent double-counting the same DOM element

  for (const category of categories) {
    const selectors = bank[category] || [];
    for (const sel of selectors) {
      let matches;
      try {
        matches = document.querySelectorAll(sel);
      } catch (_) {
        continue; // silently skip syntactically invalid selectors
      }

      for (const el of matches) {
        if (seen.has(el)) continue;
        seen.add(el);

        const parent = el.parentElement;

        // Escape hatch — button/link inside or beside the element
        const hasInternalAlt = !!el.querySelector(ALT_SEL);
        const hasParentAlt   = !!(parent && parent.querySelector(ALT_SEL) !== el
          ? parent.querySelector(ALT_SEL)
          : null);

        // Escape hatch — ARIA navigation hints
        const hasAriaHint =
          !!(el.querySelector(NAV_ARIA_SEL)) ||
          !!(parent && parent.querySelector(NAV_ARIA_SEL));

        // Escape hatch — prev/next sibling controls
        const siblings = parent ? Array.from(parent.children) : [];
        const hasSiblingControls = siblings.some(s => {
          if (s === el || !s.matches(ALT_SEL)) return false;
          const label = ((s.getAttribute('aria-label') || '') + ' ' + (s.textContent || '')).toLowerCase();
          const cls   = (s.className || '').toLowerCase();
          return NAV_PATTERN.test(label) || NAV_PATTERN.test(cls);
        });

        const escapeHatchPartial = hasInternalAlt || hasParentAlt || hasAriaHint;
        const escapeHatchFound   = escapeHatchPartial || hasSiblingControls;

        if (!escapeHatchFound) {
          violations.push({
            selector: sel,
            matchedCategory: category,
            element: el.outerHTML.slice(0, 200),
            escapeHatchFound: false,
            escapeHatchPartial,
          });
        }
      }
    }
  }

  if (violations.length === 0) return true;

  this.data({ violations, lang: lang || 'en' }); // stored for result extraction
  return false;
}

/** @type {{ id: string, evaluate: Function }} axe-core check definition */
export const pointerGesturesCheck = {
  id: 'pointer-gestures-2-5-1-check',
  evaluate: pointerGesturesEvaluate,
};

/** @type {Object} axe-core rule definition for WCAG 2.5.1 Pointer Gestures */
export const pointerGesturesRule = {
  id: 'pointer-gestures-2-5-1',
  selector: 'body',
  tags: ['wcag2.5.1', 'wcag22aa', 'pointer-gestures'],
  any: ['pointer-gestures-2-5-1-check'],
};
