/**
 * @fileoverview Gesture library fingerprinting for WCAG 2.5.1 Pointer Gestures.
 *
 * Detects gesture-capable JavaScript libraries loaded on the page by checking:
 *   1. Known window-global variable names injected by each library.
 *   2. Script `src` attribute substrings in document.scripts.
 */

/** @type {Array<{global: string, name: string}>} window-global → library name */
const GLOBAL_CHECKS = [
  { global: 'Hammer',    name: 'hammer.js'    },
  { global: 'interact',  name: 'interact.js'  },
  { global: 'ZingTouch', name: 'zingtouch'    },
  { global: 'Swiper',    name: 'swiper'       },
  { global: 'Flickity',  name: 'flickity'     },
  { global: 'Sortable',  name: 'sortablejs'   },
  { global: 'TouchSwipe',name: 'touchswipe'   },
  { global: 'Embla',     name: 'embla'        },
];

/** Inline evaluation for GSAP Draggable (requires extra property check). */
const GSAP_CHECK = {
  expr: `typeof window.Draggable !== 'undefined' && typeof window.Draggable.create === 'function'`,
  name: 'gsap-draggable',
};

/** Slick check: may expose a global OR just add DOM classes. */
const SLICK_CHECK = {
  expr: `typeof window.Slick !== 'undefined' || !!document.querySelector('.slick-slider')`,
  name: 'slick',
};

/** Script `src` substrings that identify gesture libraries. */
const SCRIPT_SRC_PATTERNS = [
  { pattern: 'hammer',     name: 'hammer.js'   },
  { pattern: 'interact.js',name: 'interact.js' },
  { pattern: 'zingtouch',  name: 'zingtouch'   },
  { pattern: 'zing',       name: 'zingtouch'   },
  { pattern: 'draggable',  name: 'gsap-draggable' },
  { pattern: 'swiper',     name: 'swiper'      },
  { pattern: 'flickity',   name: 'flickity'    },
  { pattern: 'sortable',   name: 'sortablejs'  },
  { pattern: 'slick',      name: 'slick'       },
  { pattern: 'embla',      name: 'embla'       },
  { pattern: 'touchswipe', name: 'touchswipe'  },
];

/**
 * Detects gesture libraries loaded on the page via window-global checks and
 * script tag `src` attribute scanning.
 *
 * @param {import('@playwright/test').Page|Object} page - Playwright/Puppeteer Page object
 * @returns {Promise<Set<string>>} Set of detected library name strings
 */
export async function detectGestureLibraries(page) {
  const detected = new Set();

  try {
    /** @type {string[]} */
    const fromPage = await page.evaluate((globals, gsapExpr, gsapName, slickExpr, slickName, srcPatterns) => {
      const found = [];

      /* ── Window global checks ──────────────────────────────────────────── */
      for (const { global: g, name } of globals) {
        try {
          if (typeof window[g] !== 'undefined') found.push(name);
        } catch (_) { /* sandboxed — skip */ }
      }

      /* ── GSAP Draggable ────────────────────────────────────────────────── */
      try {
        // eslint-disable-next-line no-new-func
        if (new Function('return ' + gsapExpr)()) found.push(gsapName);
      } catch (_) { /* ignore */ }

      /* ── Slick (global or DOM class) ───────────────────────────────────── */
      try {
        // eslint-disable-next-line no-new-func
        if (new Function('return ' + slickExpr)()) found.push(slickName);
      } catch (_) { /* ignore */ }

      /* ── Script src attribute scan ─────────────────────────────────────── */
      const scripts = Array.from(document.scripts);
      for (const script of scripts) {
        const src = (script.src || '').toLowerCase();
        if (!src) continue;
        for (const { pattern, name } of srcPatterns) {
          if (src.includes(pattern)) found.push(name);
        }
      }

      return found;
    }, GLOBAL_CHECKS, GSAP_CHECK.expr, GSAP_CHECK.name, SLICK_CHECK.expr, SLICK_CHECK.name, SCRIPT_SRC_PATTERNS);

    for (const name of fromPage) detected.add(name);
  } catch (err) {
    console.warn('[wcag-2.5.1] detectGestureLibraries skipped:', err.message);
  }

  return detected;
}
