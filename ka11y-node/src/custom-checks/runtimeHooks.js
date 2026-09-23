'use strict';

/**
 * Runtime hooks installed into the audited page BEFORE any page script runs
 * (via page.evaluateOnNewDocument). They record behaviour that static DOM
 * inspection cannot see and that several WCAG techniques depend on:
 *
 *   matchMedia      — SCR40  prefers-reduced-motion handled in JS
 *   timers          — G198 / SCR1 / SCR16 / G5  long setTimeout/setInterval (time limits)
 *   orientationLock — G214  screen.orientation.lock() called at runtime
 *   ariaNotify      — ARIA27 ariaNotify() status announcements
 *   mediaPlay       — G171  media.play() triggered by script without user activation
 *   windowOpen      — G201 / SCR24  window.open() at load / without user activation
 *
 * Everything is best-effort and wrapped in try/catch so a hook can never break
 * the page under test. Checks read `window.__ka11yRuntime` inside page.evaluate
 * and must tolerate its absence (unit tests, HTML-string audits, older callers).
 */

const HOOK_KEY = '__ka11yRuntime';

function runtimeHookScript() {
  try {
    if (window.__ka11yRuntime) return;
    const R = {
      matchMedia: [], timers: [], orientationLock: [], ariaNotify: [], mediaPlay: [], windowOpen: [],
      loadedAt: null,
    };
    Object.defineProperty(window, '__ka11yRuntime', { value: R, writable: false, configurable: true, enumerable: false });
    const t0 = Date.now();
    const rel = () => Date.now() - t0;
    const active = () => !!(navigator.userActivation && navigator.userActivation.isActive);
    const push = (arr, item, cap) => { if (arr.length < cap) arr.push(item); };

    // matchMedia — record queries so checks can see prefers-reduced-motion handling in scripts.
    const origMM = window.matchMedia;
    if (typeof origMM === 'function') {
      window.matchMedia = function (q) {
        try { push(R.matchMedia, { query: String(q), at: rel() }, 300); } catch (_) { /* ignore */ }
        return origMM.apply(this, arguments);
      };
    }

    // Timers — only long delays matter for time-limit techniques (≥ 1 s).
    const wrapTimer = (name) => {
      const orig = window[name];
      if (typeof orig !== 'function') return;
      window[name] = function (fn, delay) {
        try {
          const d = Number(delay) || 0;
          if (d >= 1000) {
            const snippet = typeof fn === 'function'
              ? Function.prototype.toString.call(fn).slice(0, 300)
              : String(fn).slice(0, 300);
            push(R.timers, { kind: name, delay: d, snippet, at: rel() }, 300);
          }
        } catch (_) { /* ignore */ }
        return orig.apply(this, arguments);
      };
    };
    wrapTimer('setTimeout');
    wrapTimer('setInterval');

    // screen.orientation.lock()
    try {
      const so = window.screen && window.screen.orientation;
      if (so && typeof so.lock === 'function') {
        const origLock = so.lock.bind(so);
        Object.defineProperty(so, 'lock', {
          configurable: true,
          value: function (o) {
            try { push(R.orientationLock, { orientation: String(o), at: rel() }, 50); } catch (_) { /* ignore */ }
            return origLock(o);
          },
        });
      }
    } catch (_) { /* ignore */ }

    // ariaNotify() — Chromium's experimental status-announcement API.
    const wrapNotify = (proto, label) => {
      try {
        if (proto && typeof proto.ariaNotify === 'function') {
          const orig = proto.ariaNotify;
          proto.ariaNotify = function (msg) {
            try { push(R.ariaNotify, { message: String(msg).slice(0, 200), target: label, at: rel() }, 100); } catch (_) { /* ignore */ }
            return orig.apply(this, arguments);
          };
        }
      } catch (_) { /* ignore */ }
    };
    wrapNotify(window.Element && window.Element.prototype, 'element');
    wrapNotify(window.Document && window.Document.prototype, 'document');

    // HTMLMediaElement.play()
    try {
      const mp = window.HTMLMediaElement && window.HTMLMediaElement.prototype;
      if (mp && typeof mp.play === 'function') {
        const origPlay = mp.play;
        mp.play = function () {
          try {
            push(R.mediaPlay, {
              tag: this.tagName ? this.tagName.toLowerCase() : 'media',
              muted: !!this.muted,
              src: String(this.currentSrc || this.src || '').slice(0, 200),
              at: rel(),
              userActivated: active(),
            }, 100);
          } catch (_) { /* ignore */ }
          return origPlay.apply(this, arguments);
        };
      }
    } catch (_) { /* ignore */ }

    // window.open()
    try {
      const origOpen = window.open;
      if (typeof origOpen === 'function') {
        window.open = function (url, target) {
          try { push(R.windowOpen, { url: String(url || '').slice(0, 200), target: String(target || ''), at: rel(), userActivated: active() }, 100); } catch (_) { /* ignore */ }
          return origOpen.apply(this, arguments);
        };
      }
    } catch (_) { /* ignore */ }

    window.addEventListener('load', () => { R.loadedAt = rel(); }, { once: true });
  } catch (_) { /* never break the page under test */ }
}

/**
 * Install the hooks on a Puppeteer page. Must be called before goto()/setContent().
 * Returns true when installed, false when the page object does not support it
 * (mocks, non-Puppeteer callers).
 */
async function installRuntimeHooks(page) {
  if (!page || typeof page.evaluateOnNewDocument !== 'function') return false;
  await page.evaluateOnNewDocument(runtimeHookScript);
  return true;
}

module.exports = { HOOK_KEY, installRuntimeHooks, runtimeHookScript };
