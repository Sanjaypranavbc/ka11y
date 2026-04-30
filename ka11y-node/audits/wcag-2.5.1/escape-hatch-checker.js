/**
 * @fileoverview Per-element escape hatch verification for WCAG 2.5.1 Pointer Gestures.
 *
 * After Layers 1 and 2 flag candidate elements, this module re-inspects each one
 * inside the live page to reduce false positives before final reporting.
 */

/**
 * Checks whether a gesture-dependent element (or its nearest parent) provides a
 * single-pointer or keyboard alternative — an "escape hatch" in WCAG 2.5.1 terms.
 *
 * Checks performed (in order):
 *   1. Button / link child inside the element
 *   2. Button / link sibling inside the same parent
 *   3. Keyboard event listener registered by the element (from __gestureRegistry)
 *   4. aria-label / aria-describedby on the element referencing navigation
 *   5. aria-label on a child element referencing navigation
 *
 * @param {Object} page     - A Playwright or Puppeteer Page instance
 * @param {string} selector - CSS selector of the flagged gesture element
 * @returns {Promise<{found: boolean, type: string, detail: string}>}
 */
async function checkEscapeHatch(page, selector) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) {
      return { found: false, type: 'element-not-found', detail: `No element matched "${sel}"` };
    }

    const ALT_SEL    = 'button, [role="button"], a[href], input[type="button"], input[type="submit"]';
    const NAV_PATTERN = /prev|next|previous|forward|back|left|right|slide|scroll|navigate|arrow/i;

    // ── Check 1: interactive child inside the element ─────────────────────
    const internalBtn = el.querySelector(ALT_SEL);
    if (internalBtn) {
      return {
        found: true,
        type: 'internal-button',
        detail: `<${internalBtn.tagName.toLowerCase()}> inside element provides a pointer alternative`,
      };
    }

    // ── Check 2: sibling interactive element in the same parent ───────────
    const parent = el.parentElement;
    if (parent) {
      const siblings = Array.from(parent.querySelectorAll(ALT_SEL))
        .filter(s => !el.contains(s) && s !== el);
      if (siblings.length > 0) {
        const s = siblings[0];
        return {
          found: true,
          type: 'sibling-button',
          detail: `Sibling <${s.tagName.toLowerCase()}> in parent provides a pointer alternative`,
        };
      }
    }

    // ── Check 3: keyboard listener registered in __gestureRegistry ────────
    const registry = Array.isArray(window.__gestureRegistry) ? window.__gestureRegistry : [];
    const registryEntry = registry.find(entry => {
      try { return document.querySelector(entry.selector) === el; } catch (_) { return false; }
    });
    if (registryEntry && registryEntry.hasClickAlternative) {
      return {
        found: true,
        type: 'keyboard-listener',
        detail: 'Element has a registered click or keyboard event listener alternative',
      };
    }

    // ── Check 4: aria-label / aria-describedby on the element ─────────────
    const ownLabel = el.getAttribute('aria-label') || '';
    const descId   = el.getAttribute('aria-describedby');
    const descText = descId
      ? (document.getElementById(descId) || {}).textContent || ''
      : '';
    if (NAV_PATTERN.test(ownLabel) || NAV_PATTERN.test(descText)) {
      return {
        found: true,
        type: 'aria-navigation',
        detail: `aria attribute references navigation: "${ownLabel || descText}"`,
      };
    }

    // ── Check 5: aria-label on a navigation child ─────────────────────────
    const labelledChild = el.querySelector('[aria-label], [aria-describedby]');
    if (labelledChild) {
      const childLabel = labelledChild.getAttribute('aria-label') || '';
      if (NAV_PATTERN.test(childLabel)) {
        return {
          found: true,
          type: 'aria-labelled-child',
          detail: `Child element has navigation aria-label: "${childLabel}"`,
        };
      }
    }

    return { found: false, type: 'none', detail: 'No escape hatch detected' };
  }, selector);
}
