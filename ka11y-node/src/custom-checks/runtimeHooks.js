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
 *   listenersOf(el) — G90 / SCR2 / SCR20 / SCR35 / G202  event types registered on an element
 *                     through addEventListener (mouse-only vs keyboard handlers)
 *   docListeners    — G217 (keydown on document/window), G213 (devicemotion/orientation),
 *                     G215 (touch/pointer gesture handlers), G142 (non-passive touch handlers
 *                     that call preventDefault and can block pinch-zoom)
 *   audioContexts   — G171  Web Audio API contexts created without user activation
 *   canvasTextOf(c) — C22   text drawn on a <canvas> via fillText/strokeText (images of text)
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
      docListeners: [], audioContexts: [],
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

    // addEventListener registry — the only way to see handlers that are not inline on* attributes.
    try {
      const LISTENERS = new WeakMap();
      const ELEMENT_TYPES = /^(click|dblclick|mousedown|mouseup|mouseover|mouseout|mouseenter|mouseleave|pointerdown|pointerup|pointermove|touchstart|touchend|touchmove|keydown|keyup|keypress|focus|blur|focusin|focusout|change|input|drag|dragstart|dragend|drop|wheel|contextmenu)$/;
      const DOC_TYPES = /^(keydown|keyup|keypress|touchstart|touchmove|touchend|gesturestart|gesturechange|wheel|devicemotion|deviceorientation|deviceorientationabsolute|pointerdown|pointermove|mousemove|scroll|beforeunload|unload)$/;
      R.listenersOf = function (el) {
        const s = LISTENERS.get(el);
        return s ? Array.from(s) : [];
      };
      R.hasListener = function (el, re) {
        const s = LISTENERS.get(el);
        if (!s) return false;
        for (const t of s) if (re.test(t)) return true;
        return false;
      };
      const proto = window.EventTarget && window.EventTarget.prototype;
      if (proto && typeof proto.addEventListener === 'function') {
        const origAdd = proto.addEventListener;
        proto.addEventListener = function (type, fn, opts) {
          try {
            const t = String(type);
            if (this && window.Element && this instanceof window.Element) {
              if (ELEMENT_TYPES.test(t)) {
                let s = LISTENERS.get(this);
                if (!s) { s = new Set(); LISTENERS.set(this, s); }
                s.add(t);
              }
            } else if (this === window || this === document || (document.body && this === document.body) || (document.documentElement && this === document.documentElement)) {
              if (DOC_TYPES.test(t)) {
                const passive = !!(opts && typeof opts === 'object' && opts.passive);
                let snippet = '';
                try { snippet = typeof fn === 'function' ? Function.prototype.toString.call(fn).slice(0, 240) : ''; } catch (_) { /* ignore */ }
                push(R.docListeners, {
                  target: this === window ? 'window' : this === document ? 'document' : this === document.body ? 'body' : 'html',
                  type: t, passive, preventsDefault: /preventDefault/.test(snippet), snippet, at: rel(),
                }, 400);
              }
            }
          } catch (_) { /* ignore */ }
          return origAdd.apply(this, arguments);
        };
      }
    } catch (_) { /* ignore */ }

    // Canvas text — fillText/strokeText calls per canvas (C22 images of text on canvas).
    try {
      const CANVAS_TEXT = new WeakMap();
      R.canvasTextOf = function (canvas) { return CANVAS_TEXT.get(canvas) || ''; };
      const cp = window.CanvasRenderingContext2D && window.CanvasRenderingContext2D.prototype;
      for (const name of ['fillText', 'strokeText']) {
        if (!cp || typeof cp[name] !== 'function') continue;
        const orig = cp[name];
        cp[name] = function (text) {
          try {
            const c = this.canvas;
            if (c) { const prev = CANVAS_TEXT.get(c) || ''; if (prev.length < 400) CANVAS_TEXT.set(c, (prev + ' ' + String(text)).trim()); }
          } catch (_) { /* ignore */ }
          return orig.apply(this, arguments);
        };
      }
    } catch (_) { /* ignore */ }

    // Web Audio API — sounds started by script without user activation (G171).
    try {
      for (const name of ['AudioContext', 'webkitAudioContext']) {
        const Orig = window[name];
        if (typeof Orig !== 'function') continue;
        const Wrapped = function () {
          try { push(R.audioContexts, { at: rel(), userActivated: active() }, 20); } catch (_) { /* ignore */ }
          return new Orig(...arguments);
        };
        Wrapped.prototype = Orig.prototype;
        window[name] = Wrapped;
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
