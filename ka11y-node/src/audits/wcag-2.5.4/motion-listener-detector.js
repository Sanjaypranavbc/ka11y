/**
 * @fileoverview Runtime motion-listener detection via addEventListener monkey-patch.
 *
 * The init script is injected BEFORE any page script runs so it intercepts every
 * addEventListener call, including those made by third-party motion libraries
 * (shake.js, gyroscape, framework-wired sensor handlers).
 *
 * Without this layer, framework-wired listeners are invisible because
 * `window.addEventListener('devicemotion', …)` does NOT set
 * `window.ondevicemotion` to a function — the runtime property scan in
 * `motion-event-detector.js` would miss them.
 *
 * Results accumulate in `window.__motionRegistry` and are read back after
 * navigation via `extractMotionRegistry()`.
 */

const MOTION_EVENTS = ['devicemotion', 'deviceorientation', 'deviceorientationabsolute'];

/**
 * Self-contained IIFE that monkey-patches addEventListener on `window`.
 * Serialised to a string and executed in the browser; MUST NOT reference Node APIs.
 */
function motionDetectorInitScript() {
  if (window.__motionRegistry) return;

  const MOTION_EVENTS = new Set([
    'devicemotion', 'deviceorientation', 'deviceorientationabsolute'
  ]);

  window.__motionRegistry = [];

  const origWindowAdd = window.addEventListener;
  window.addEventListener = function (type, listener, options) {
    try {
      if (typeof type === 'string' && MOTION_EVENTS.has(type)) {
        let stack = '';
        try { stack = (new Error()).stack || ''; } catch (_) {}
        window.__motionRegistry.push({
          target: 'window',
          type: type,
          // First two stack frames are this patched function and the caller;
          // skip frame 0 to point at the caller site.
          stack: stack.split('\n').slice(2, 5).join('\n').trim(),
          timestamp: Date.now(),
        });
      }
    } catch (_) { /* never let instrumentation break the page */ }
    return origWindowAdd.call(window, type, listener, options);
  };

  // Also intercept Permissions / iOS opt-in calls — strong signal even if a
  // listener is never actually attached (some apps probe for support first).
  if (typeof window.DeviceMotionEvent !== 'undefined' &&
      typeof window.DeviceMotionEvent.requestPermission === 'function') {
    const origReq = window.DeviceMotionEvent.requestPermission;
    window.DeviceMotionEvent.requestPermission = function () {
      try {
        window.__motionRegistry.push({
          target: 'DeviceMotionEvent',
          type: 'requestPermission',
          stack: '',
          timestamp: Date.now(),
        });
      } catch (_) {}
      return origReq.apply(this, arguments);
    };
  }
}

/**
 * Inject the detector before navigation. Supports Playwright (`addInitScript`)
 * and Puppeteer (`evaluateOnNewDocument`).
 *
 * @param {import('playwright').Page|Object} page
 */
async function injectMotionDetector(page) {
  if (typeof page.addInitScript === 'function') {
    await page.addInitScript(motionDetectorInitScript);
    return;
  }
  if (typeof page.evaluateOnNewDocument === 'function') {
    await page.evaluateOnNewDocument(motionDetectorInitScript);
    return;
  }
  throw new Error(
    'injectMotionDetector: page object has neither addInitScript (Playwright) ' +
    'nor evaluateOnNewDocument (Puppeteer).'
  );
}

/**
 * Read the registry back after navigation. Returns [] if the detector was not
 * injected or if the page has no registry (e.g. cross-origin frame).
 *
 * @param {import('playwright').Page|Object} page
 * @returns {Promise<Array<{ target: string, type: string, stack: string, timestamp: number }>>}
 */
async function extractMotionRegistry(page) {
  try {
    return await page.evaluate(() => {
      const reg = window.__motionRegistry;
      window.__motionRegistry = [];
      return Array.isArray(reg) ? reg : [];
    });
  } catch (_) {
    return [];
  }
}

module.exports = {
  injectMotionDetector,
  extractMotionRegistry,
  MOTION_EVENTS,
};
