'use strict';

/**
 * WCAG 2.5.1 Pointer Gestures — integration test suite.
 *
 * Uses Jest + Puppeteer.  The audit module is ESM; it is loaded via dynamic
 * import() which Node.js supports in CommonJS files.
 *
 * Replace ENGLISH_TEST_URL and JAPANESE_TEST_URL with real URLs before running.
 * The tests are skipped automatically when the URL placeholders are unchanged.
 *
 * Run:
 *   npx jest tests/sc-2.5.1.spec.js --testTimeout=30000
 */

const puppeteer = require('puppeteer');

/* ── Placeholder URLs — replace before running ─────────────────────────── */
const ENGLISH_TEST_URL  = 'https://REPLACE_WITH_ENGLISH_URL';
const JAPANESE_TEST_URL = 'https://REPLACE_WITH_JAPANESE_URL';

const IS_EN_CONFIGURED  = !ENGLISH_TEST_URL.includes('REPLACE');
const IS_JA_CONFIGURED  = !JAPANESE_TEST_URL.includes('REPLACE');

/* ── Shared browser state ───────────────────────────────────────────────── */
let browser;
let auditPointerGestures;
let injectGestureDetector;

beforeAll(async () => {
  // Skip setup unless at least one test URL is configured — avoids ESM dynamic import
  // overhead when running unit tests in CI or locally without integration targets.
  if (!IS_EN_CONFIGURED && !IS_JA_CONFIGURED) {
    console.warn('Skipping WCAG 2.5.1 integration tests — URLs not configured');
    return;
  }

  auditPointerGestures = require('../src/audits/wcag-2.5.1/index.js').auditPointerGestures;
  injectGestureDetector = require('../src/audits/wcag-2.5.1/gesture-listener-detector.js').injectGestureDetector;

  browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });
}, 20000);

afterAll(async () => {
  if (browser) await browser.close();
});

/* ── Helper ─────────────────────────────────────────────────────────────── */

/**
 * Prints a summary table of violations to the console.
 *
 * @param {Array<Object>} violations
 */
function logSummaryTable(violations) {
  if (violations.length === 0) {
    console.log('  (no violations)');
    return;
  }
  console.log(
    ['  selector', 'layer', 'escapeHatchFound']
      .map(h => h.padEnd(40))
      .join(' | ')
  );
  console.log('  ' + '-'.repeat(100));
  for (const v of violations) {
    const cols = [
      String(v.selector || '').slice(0, 38).padEnd(40),
      String(v.layer    || '').padEnd(40),
      String(v.escapeHatchFound).padEnd(40),
    ];
    console.log('  ' + cols.join(' | '));
  }
}

/* ── Tests ──────────────────────────────────────────────────────────────── */

describe('WCAG 2.5.1 Pointer Gestures', () => {

  test('English page: all gesture widgets must have a single-pointer escape hatch', async () => {
    if (!IS_EN_CONFIGURED) {
      console.warn('  Skipping: ENGLISH_TEST_URL not configured');
      return;
    }

    const page = await browser.newPage();
    try {
      /* Inject gesture detector BEFORE navigation so it intercepts all scripts. */
      await injectGestureDetector(page);

      const violations = await auditPointerGestures(page, {
        url:  ENGLISH_TEST_URL,
        lang: 'en',
      });

      console.log('\n── WCAG 2.5.1 English violations ──');
      logSummaryTable(violations);

      const unresolved = violations.filter(v => !v.escapeHatchFound);
      expect(unresolved).toHaveLength(0);
    } finally {
      await page.close();
    }
  }, 30000);

  test('Japanese page: all gesture widgets must have a single-pointer escape hatch', async () => {
    if (!IS_JA_CONFIGURED) {
      console.warn('  Skipping: JAPANESE_TEST_URL not configured');
      return;
    }

    const page = await browser.newPage();
    try {
      await injectGestureDetector(page);

      const violations = await auditPointerGestures(page, {
        url:  JAPANESE_TEST_URL,
        lang: 'ja',
      });

      console.log('\n── WCAG 2.5.1 Japanese violations ──');
      logSummaryTable(violations);

      const unresolved = violations.filter(v => !v.escapeHatchFound);
      expect(unresolved).toHaveLength(0);
    } finally {
      await page.close();
    }
  }, 30000);

});
