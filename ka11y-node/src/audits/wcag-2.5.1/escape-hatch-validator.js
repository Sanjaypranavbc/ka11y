/**
 * @fileoverview Per-element escape hatch validation for WCAG 2.5.1 Pointer Gestures.
 *
 * An "escape hatch" is any single-pointer or keyboard alternative that allows
 * a user to perform the same action as a gesture without needing multi-touch
 * or a path-based gesture.
 */

/**
 * @typedef {Object} EscapeHatchResult
 * @property {boolean}  hasAlternative - true if any single-pointer alternative was found
 * @property {string[]} evidence       - human-readable descriptions of each found alternative
 */

/**
 * Checks whether a gesture-dependent element (or its nearest DOM context)
 * provides a single-pointer or keyboard alternative.
 *
 * Checks performed (all inside a single page.evaluate call):
 *   1. Click handler on the element (onclick attribute or property)
 *   2. Keyboard event handler on the element or within 3 ancestor levels
 *   3. ARIA pointer alternative (aria-controls or aria-haspopup present)
 *   4. Adjacent control buttons within 2 DOM levels (sibling or parent-sibling)
 *   5. Tab-focusable element (tabIndex >= 0) on the element or a sibling
 *
 * @param {import('@playwright/test').Page|Object} page - Playwright/Puppeteer Page object
 * @param {string} elementSelector                      - CSS selector for the element to check
 * @returns {Promise<EscapeHatchResult>}
 */
async function validateEscapeHatch(page, elementSelector) {
  try {
    return await page.evaluate((selector) => {
      const el = document.querySelector(selector);
      if (!el) return { hasAlternative: false, evidence: [] };

      const evidence = [];
      const ALT_BTN  = 'button, [role="button"], [aria-label], input[type="button"]';

      /* ── Check 1: Click handler on the element ───────────────────────── */
      if (typeof el.onclick === 'function' || el.getAttribute('onclick')) {
        evidence.push('Click handler present on element');
      }

      /* ── Check 2: Keyboard handler on element or up to 3 ancestors ───── */
      const KBD_ATTRS = ['onkeydown', 'onkeypress', 'onkeyup'];
      let node = el;
      for (let depth = 0; depth <= 3; depth++) {
        if (!node) break;
        for (const attr of KBD_ATTRS) {
          if (node.getAttribute(attr) || typeof node[attr] === 'function') {
            evidence.push(`Keyboard handler (${attr}) on ${depth === 0 ? 'element' : `ancestor (depth ${depth})`}`);
          }
        }
        node = node.parentElement;
      }

      /* ── Check 3: ARIA pointer alternative ───────────────────────────── */
      if (el.getAttribute('aria-controls')) {
        evidence.push(`aria-controls="${el.getAttribute('aria-controls')}" present`);
      }
      if (el.getAttribute('aria-haspopup')) {
        evidence.push(`aria-haspopup="${el.getAttribute('aria-haspopup')}" present`);
      }

      /* ── Check 4: Adjacent control buttons within 2 DOM levels ─────────
         Check (a) children of the element, (b) siblings, (c) parent's siblings */
      
      function checkButtonSemantics(btn) {
        const label = ((btn.textContent || '') + ' ' + (btn.getAttribute('aria-label') || '') + ' ' + (btn.getAttribute('title') || '')).toLowerCase();
        const SEMANTIC_MATCH = /next|prev|forward|back|zoom|\+|-|left|right|up|down|次へ|前へ|ズーム|拡大|縮小|進む|戻る/i;
        if (SEMANTIC_MATCH.test(label)) {
          return ` (High quality: semantically matches gesture action)`;
        }
        return '';
      }

      const internalBtn = el.querySelector(ALT_BTN);
      if (internalBtn) {
        evidence.push(`Child <${internalBtn.tagName.toLowerCase()}> provides a pointer alternative${checkButtonSemantics(internalBtn)}`);
      }

      const parent = el.parentElement;
      if (parent) {
        const siblingBtns = Array.from(parent.querySelectorAll(ALT_BTN))
          .filter(s => !el.contains(s) && s !== el);
        if (siblingBtns.length > 0) {
          evidence.push(`Sibling <${siblingBtns[0].tagName.toLowerCase()}> found in parent${checkButtonSemantics(siblingBtns[0])}`);
        }

        /* parent's parent siblings (grandparent context) */
        const grandparent = parent.parentElement;
        if (grandparent) {
          const unclesBtns = Array.from(grandparent.querySelectorAll(ALT_BTN))
            .filter(s => !parent.contains(s) && s !== parent);
          if (unclesBtns.length > 0) {
            evidence.push(`Button found in grandparent context: <${unclesBtns[0].tagName.toLowerCase()}>${checkButtonSemantics(unclesBtns[0])}`);
          }
        }
      }

      /* ── Check 5: Tab-focusable element or sibling ───────────────────── */
      if (el.tabIndex >= 0) {
        evidence.push('Element is tab-focusable (tabIndex >= 0)');
      } else if (parent) {
        const focusableSibling = Array.from(parent.children)
          .find(c => c !== el && c.tabIndex >= 0);
        if (focusableSibling) {
          evidence.push(`Sibling <${focusableSibling.tagName.toLowerCase()}> is tab-focusable`);
        }
      }

      return { hasAlternative: evidence.length > 0, evidence };
    }, elementSelector);
  } catch (err) {
    console.warn(`[wcag-2.5.1] validateEscapeHatch failed for "${elementSelector}":`, err.message);
    return { hasAlternative: false, evidence: [] };
  }
}
module.exports = { validateEscapeHatch };
