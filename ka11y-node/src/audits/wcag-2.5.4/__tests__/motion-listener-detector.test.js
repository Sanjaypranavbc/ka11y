'use strict';

/**
 * Unit tests for the WCAG 2.5.4 motion-listener detector.
 *
 * Simulates the page object surface (Playwright/Puppeteer) without launching
 * a real browser. The init script is captured and executed in a JSDOM-ish
 * sandbox to verify it instruments addEventListener correctly.
 */

const {
  injectMotionDetector,
  extractMotionRegistry,
} = require('../motion-listener-detector.js');

function makePlaywrightPage() {
  return {
    _initScript: null,
    addInitScript(fn) { this._initScript = fn; },
  };
}

function makePuppeteerPage() {
  return {
    _initScript: null,
    evaluateOnNewDocument(fn) { this._initScript = fn; },
  };
}

function makeRegistryPage(registry) {
  return {
    evaluate(fn) {
      const window = { __motionRegistry: registry };
      return Promise.resolve(fn.call({ window }));
    },
  };
}

describe('motion-listener-detector', () => {
  test('injectMotionDetector uses addInitScript on Playwright pages', async () => {
    const page = makePlaywrightPage();
    await injectMotionDetector(page);
    expect(typeof page._initScript).toBe('function');
  });

  test('injectMotionDetector falls back to evaluateOnNewDocument on Puppeteer pages', async () => {
    const page = makePuppeteerPage();
    await injectMotionDetector(page);
    expect(typeof page._initScript).toBe('function');
  });

  test('injectMotionDetector throws when neither API is available', async () => {
    await expect(injectMotionDetector({})).rejects.toThrow(/addInitScript|evaluateOnNewDocument/);
  });

  test('extractMotionRegistry returns the captured registry', async () => {
    const captured = [
      { target: 'window', type: 'devicemotion', stack: '', timestamp: 1 },
    ];
    // Stub `page.evaluate` so the function passed in sees a `window` containing
    // our captured registry (mirrors what Playwright would do in the browser).
    const page = {
      evaluate(fn) {
        const sandboxWindow = { __motionRegistry: captured };
        return Promise.resolve(
          (new Function('window', `return (${fn.toString()})();`))(sandboxWindow)
        );
      },
    };
    await expect(extractMotionRegistry(page)).resolves.toEqual(captured);
  });

  test('extractMotionRegistry tolerates evaluation failures', async () => {
    const page = { evaluate: () => Promise.reject(new Error('detached frame')) };
    await expect(extractMotionRegistry(page)).resolves.toEqual([]);
  });

  test('init script intercepts addEventListener("devicemotion") and records the call', async () => {
    // Build a page-side sandbox: the script body expects `window` to expose
    // addEventListener and a few primitives.
    const page = makePlaywrightPage();
    await injectMotionDetector(page);

    const sandbox = {
      __motionRegistry: undefined,
      addEventListener: function () { /* original — no-op for the test */ },
    };
    sandbox.window = sandbox; // self-ref used inside the IIFE

    // Execute the injected script with `window` bound to the sandbox.
    const script = page._initScript;
    (new Function('window', `(${script.toString()})()`))(sandbox);

    // Now simulate framework code wiring a devicemotion listener.
    sandbox.addEventListener('devicemotion', () => {});
    sandbox.addEventListener('deviceorientation', () => {});
    sandbox.addEventListener('click', () => {}); // should NOT be captured

    expect(Array.isArray(sandbox.__motionRegistry)).toBe(true);
    expect(sandbox.__motionRegistry).toHaveLength(2);
    const types = sandbox.__motionRegistry.map(e => e.type);
    expect(types).toEqual(expect.arrayContaining(['devicemotion', 'deviceorientation']));
    expect(types).not.toContain('click');
  });
});
