/**
 * @fileoverview Runtime gesture-listener detection via addEventListener monkey-patch.
 *
 * The init script is injected BEFORE any page script runs so it intercepts every
 * addEventListener call, including those made by third-party gesture libraries.
 * Results accumulate in window.__gestureRegistry and are read back after navigation
 * via extractGestureRegistry().
 */

/**
 * Self-contained IIFE that monkey-patches addEventListener.
 * This function body is serialised to a string and executed in the browser; it
 * must contain NO import statements, require() calls, or references to Node.js APIs.
 */
function gestureDetectorInitScript() {
  /* Initialise registry only once (safe if script is injected multiple times). */
  if (window.__gestureRegistry) return;

  const GESTURE_EVENTS = new Set([
    'touchstart', 'touchmove', 'touchend', 'touchcancel',
    'pointerdown', 'pointermove', 'pointerup', 'pointercancel',
    'MSPointerDown', 'MSPointerMove',
  ]);
  const CLICK_ALT_EVENTS = new Set(['click', 'keydown', 'keyup', 'keypress']);

  window.__gestureRegistry = [];

  /**
   * WeakMap stores per-element registry entries so they can be updated across
   * multiple addEventListener calls without searching the array each time.
   */
  const _elMap = new WeakMap();

  /**
   * Builds a stable CSS selector for a DOM element without relying on
   * document.querySelector round-trips (which would cause re-entrancy issues
   * during the early-inject phase before the full DOM is ready).
   *
   * @param {Element} el
   * @returns {string}
   */
  function selectorOf(el) {
    if (!el || el.nodeType !== 1) return '';
    try {
      if (el.id) return '#' + CSS.escape(el.id);
    } catch (_) {
      if (el.id) return '#' + el.id.replace(/[^\w-]/g, '\\$&');
    }

    const segments = [];
    let node = el;
    while (node && node.nodeType === 1 && node !== document.documentElement) {
      const tag = node.tagName.toLowerCase();
      let seg = tag;
      try {
        if (node.id) {
          seg = '#' + CSS.escape(node.id);
          segments.unshift(seg);
          break;
        }
      } catch (_) { /* ignore */ }
      /* nth-of-type to disambiguate siblings */
      const parent = node.parentElement;
      if (parent) {
        const sameTag = Array.from(parent.children).filter(c => c.tagName === node.tagName);
        if (sameTag.length > 1) seg += ':nth-of-type(' + (sameTag.indexOf(node) + 1) + ')';
      }
      segments.unshift(seg);
      node = node.parentElement;
    }
    return segments.join(' > ') || el.tagName.toLowerCase();
  }

  /**
   * Wraps an addEventListener implementation so that gesture-event registrations
   * are recorded in __gestureRegistry while the original call is always forwarded.
   * This design is safe even if a page script later overrides addEventListener
   * again — each layer still calls its predecessor.
   *
   * @param {Function} original - The addEventListener implementation to wrap
   * @returns {Function}
   */
  function wrapAEL(original) {
    return function patchedAddEventListener(type, listener, opts) {
      /* Always delegate to the original first — never break normal behaviour. */
      original.call(this, type, listener, opts);

      const isGesture  = GESTURE_EVENTS.has(type);
      const isClickAlt = CLICK_ALT_EVENTS.has(type);
      if (!isGesture && !isClickAlt) return;

      /* Resolve the actual DOM element; window maps to documentElement for
         selector purposes since window itself has no CSS selector. */
      const el = (this === window || this === globalThis)
        ? document.documentElement
        : this instanceof EventTarget ? this : null;
      if (!el || typeof el.nodeType === 'undefined') return;

      let entry = _elMap.get(el);
      if (!entry) {
        entry = { selector: selectorOf(el), events: [], hasClickAlternative: false };
        _elMap.set(el, entry);
        window.__gestureRegistry.push(entry);
      }

      if (isGesture && !entry.events.includes(type)) entry.events.push(type);
      if (isClickAlt) entry.hasClickAlternative = true;
    };
  }

  /* Patch window.addEventListener */
  window.addEventListener = wrapAEL(window.addEventListener.bind(window));

  /* Patch EventTarget.prototype.addEventListener (covers all elements and objects). */
  EventTarget.prototype.addEventListener = wrapAEL(EventTarget.prototype.addEventListener);
}

/**
 * Injects the gesture-detector monkey-patch into the page before any page scripts
 * run.  Must be called before page.goto() / page.navigate().
 *
 * Supports both Playwright (page.addInitScript) and Puppeteer
 * (page.evaluateOnNewDocument); the correct API is detected automatically.
 *
 * @param {Object} page - A Playwright or Puppeteer Page instance
 * @returns {Promise<void>}
 */
export async function injectGestureDetector(page) {
  if (typeof page.addInitScript === 'function') {
    await page.addInitScript(gestureDetectorInitScript);
  } else if (typeof page.evaluateOnNewDocument === 'function') {
    await page.evaluateOnNewDocument(gestureDetectorInitScript);
  } else {
    throw new Error(
      'injectGestureDetector: page object has neither addInitScript (Playwright) ' +
      'nor evaluateOnNewDocument (Puppeteer).'
    );
  }
}

/**
 * Reads window.__gestureRegistry from the navigated page and returns only
 * entries that registered at least one gesture event.
 *
 * Call this after the page has finished loading (post-goto).
 *
 * @param {Object} page - A Playwright or Puppeteer Page instance
 * @returns {Promise<Array<{selector: string, events: string[], hasClickAlternative: boolean}>>}
 */
export async function extractGestureRegistry(page) {
  return page.evaluate(() =>
    (window.__gestureRegistry || []).filter(e => e.events.length > 0)
  );
}
