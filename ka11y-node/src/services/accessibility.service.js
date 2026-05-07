'use strict';

const fs = require('fs');
const path = require('path');
const dns = require('dns').promises;
const { mapResults, mapResultsFlat, mapCustomResultsFlat } = require('../utils/axeResultMapper');
const { runAll, runStaticChecks, mergeWithAxe } = require('../custom-checks/index');

// Bug 3 fix: expanded from narrow RFC-1918/loopback/link-local set to include all
// non-public ranges matched by the Python-side guard (0.0.0.0/8, shared-address
// 100.64/10, TEST-NET documentation ranges, and multicast/reserved space).
const _PRIVATE_IP_RE = [
  /^127\./,                                       // IPv4 loopback (127.0.0.0/8)
  /^0\./,                                         // "this" network (0.0.0.0/8)
  /^10\./,                                        // RFC-1918 class A (10.0.0.0/8)
  /^172\.(1[6-9]|2\d|3[01])\./,                  // RFC-1918 class B (172.16.0.0/12)
  /^192\.168\./,                                  // RFC-1918 class C (192.168.0.0/16)
  /^169\.254\./,                                  // IPv4 link-local (169.254.0.0/16)
  /^100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\./,   // Shared address space (100.64.0.0/10)
  /^192\.0\.2\./,                                 // TEST-NET-1 (192.0.2.0/24)
  /^198\.51\.100\./,                              // TEST-NET-2 (198.51.100.0/24)
  /^203\.0\.113\./,                               // TEST-NET-3 (203.0.113.0/24)
  /^(22[4-9]|23\d)\./,                           // Multicast (224.0.0.0/4)
  /^::1$/,                                        // IPv6 loopback
  /^::ffff:127\./i,                               // IPv4-mapped IPv6 loopback
  /^::ffff:10\./i,                                // IPv4-mapped RFC-1918 class A
  /^::ffff:172\.(1[6-9]|2\d|3[01])\./i,          // IPv4-mapped RFC-1918 class B
  /^::ffff:192\.168\./i,                          // IPv4-mapped RFC-1918 class C
  /^::ffff:169\.254\./i,                          // IPv4-mapped link-local
  /^f[cd][0-9a-f]{2}:/i,                          // IPv6 unique-local (fc00::/7)
  /^fe80:/i,                                      // IPv6 link-local (fe80::/10)
];

// Bug 4 fix: typed error so controllers can distinguish client input failures
// (bad URL / private IP) from internal server errors and return 400 vs 500.
class SsrfGuardError extends Error {
  constructor(msg) {
    super(msg);
    this.name = 'SsrfGuardError';
  }
}

async function _assertPublicUrl(url) {
  const { hostname } = new URL(url);
  let addresses;
  try {
    // Resolve both IPv4 and IPv6 addresses.
    // lookup() honours system resolver policy and returns all families.
    addresses = await dns.lookup(hostname, { all: true, verbatim: true });
  } catch {
    throw new SsrfGuardError(`SSRF guard: DNS resolution failed for ${hostname}`);
  }
  if (!Array.isArray(addresses) || addresses.length === 0) {
    throw new SsrfGuardError(`SSRF guard: DNS resolution returned no addresses for ${hostname}`);
  }
  for (const { address: ip } of addresses) {
    if (_PRIVATE_IP_RE.some(re => re.test(ip))) {
      throw new SsrfGuardError(`SSRF guard: ${hostname} resolves to blocked IP ${ip}`);
    }
  }
}

// Bug 2 fix: block SSRF via redirect-time hops. Install this interceptor on every
// Puppeteer page used for live-URL analysis so that even if the initial DNS check
// passes, a server-side redirect to a private IP is blocked before the browser follows it.
function _installSsrfInterceptor(page) {
  page.on('request', (request) => {
    try {
      const { hostname } = new URL(request.url());
      if (_PRIVATE_IP_RE.some(re => re.test(hostname))) {
        request.abort('addressunreachable');
        return;
      }
    } catch { /* invalid URL — let the request continue and fail naturally */ }
    request.continue();
  });
}

const MAX_CONCURRENT = parseInt(process.env.PUPPETEER_MAX_CONCURRENT) || 3;
const AXE_LOCALE_DIR = path.join(path.dirname(require.resolve('axe-core/package.json')), 'locales');
const AXE_LOCALE_ALIASES = {
  de: 'de',
  da: 'da',
  el: 'el',
  es: 'es',
  eu: 'eu',
  fr: 'fr',
  he: 'he',
  it: 'it',
  ja: 'ja',
  ko: 'ko',
  nl: 'nl',
  no: 'no_NB',
  'no-nb': 'no_NB',
  pl: 'pl',
  pt: 'pt_PT',
  'pt-pt': 'pt_PT',
  'pt-br': 'pt_BR',
  ru: 'ru',
  zh: 'zh_CN',
  'zh-cn': 'zh_CN',
  'zh-tw': 'zh_TW',
};
const AXE_LOCALE_CACHE_CAP = 32;
const _axeLocaleCache = new Map();

/**
 * Map a WCAG conformance level string to axe-core tag arrays.
 * "A"   → Level A tags only
 * "AA"  → Level A + AA tags (default)
 * "AAA" → Level A + AA + AAA tags
 */
function _tagsForLevel(level) {
  const tags = ['wcag2a', 'wcag21a', 'wcag22a', 'best-practice'];
  if (level === 'AA' || level === 'AAA') tags.push('wcag2aa', 'wcag21aa', 'wcag22aa');
  if (level === 'AAA') tags.push('wcag2aaa');
  return tags;
}

function _allowedLevels(level) {
  const levels = new Set(['A']);
  if (level === 'AA' || level === 'AAA') levels.add('AA');
  if (level === 'AAA') levels.add('AAA');
  return levels;
}

function _sanitizeLocaleLang(lang = 'en') {
  return String(lang || 'en').replace(/[^a-zA-Z-]/g, '').toLowerCase();
}

function _loadAxeLocale(lang = 'en') {
  const normalized = _sanitizeLocaleLang(lang);
  if (!normalized || normalized === 'en') return null;

  // LRU: On cache hit, promote the entry to most recently used
  if (_axeLocaleCache.has(normalized)) {
    const cachedValue = _axeLocaleCache.get(normalized);
    _axeLocaleCache.delete(normalized);
    _axeLocaleCache.set(normalized, cachedValue);
    return cachedValue;
  }

  // LRU: On cache miss, determine value, then evict if needed, then insert
  let valueToCache = null;
  const localeId = AXE_LOCALE_ALIASES[normalized] || AXE_LOCALE_ALIASES[normalized.split('-')[0]];

  if (localeId) {
    const localePath = path.join(AXE_LOCALE_DIR, `${localeId}.json`);
    try {
      valueToCache = JSON.parse(fs.readFileSync(localePath, 'utf8'));
    } catch {
      // valueToCache remains null (existing behavior: cache null on error to avoid disk hits)
    }
  }

  // Evict least-recently-used (first entry) when at capacity
  if (_axeLocaleCache.size >= AXE_LOCALE_CACHE_CAP) {
    _axeLocaleCache.delete(_axeLocaleCache.keys().next().value);
  }
  _axeLocaleCache.set(normalized, valueToCache);
  return valueToCache;
}

/**
 * AccessibilityService — SRP: orchestrates a single Puppeteer + axe analysis run.
 *
 * All external dependencies are injected via the constructor (DIP).
 */
class AccessibilityService {
  /**
   * @param {object} puppeteer    - Puppeteer library
   * @param {string} axeCorePath  - Resolved path to the axe-core browser bundle
   * @param {object} logger       - Logger instance
   * @param {object} config       - Application config ({ browser, axe })
   */
  constructor(puppeteer, axeCorePath, logger, config) {
    this._puppeteer    = puppeteer;
    this._axeCorePath  = axeCorePath;
    this._logger       = logger;
    this._config       = config;
    this._activeCount  = 0;
    this._waitQueue    = [];
  }

  _acquireSlot() {
    if (this._activeCount < MAX_CONCURRENT) {
      this._activeCount++;
      return Promise.resolve();
    }
    return new Promise(resolve => this._waitQueue.push(resolve));
  }

  _releaseSlot() {
    if (this._waitQueue.length > 0) {
      this._waitQueue.shift()();
    } else {
      this._activeCount--;
    }
  }

  async _injectAxe(page, logPrefix = '') {
    const prefix = logPrefix ? `${logPrefix} ` : '';
    const waitForAxe = () => page.waitForFunction(
      () => Boolean(globalThis.axe && typeof globalThis.axe.run === 'function'),
      { timeout: 2_000 }
    );

    const INJECT_TIMEOUT_MS = 10_000;
    const tryInject = async () => {
      const injectWithTimeout = (fn) =>
        Promise.race([
          fn(),
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error('axe injection timed out')), INJECT_TIMEOUT_MS)
          ),
        ]);
      await injectWithTimeout(async () => {
        await page.addScriptTag({ path: this._axeCorePath });
        await waitForAxe();
      });
    };

    try {
      await tryInject();
    } catch (err) {
      this._logger.warn(`${prefix}axe-core was not available after injection, retrying once: ${err.message}`);
      try {
        await tryInject();
      } catch {
        throw new Error(
          'axe-core injection failed: globalThis.axe.run was unavailable after script injection'
        );
      }
    }
  }

  async _configureAxeLocale(page, lang = 'en', logPrefix = '') {
    const locale = _loadAxeLocale(lang);
    if (!locale) return;

    const prefix = logPrefix ? `${logPrefix} ` : '';
    await page.evaluate((localePayload) => {
      // eslint-disable-next-line no-undef
      axe.configure({ locale: localePayload });
    }, locale);
    this._logger.info(`${prefix}Configured axe-core locale: ${_sanitizeLocaleLang(lang)}`);
  }

  /**
   * Analyzes HTML for accessibility issues.
   *
   * @param {string} html               - Raw HTML string
   * @param {string|null} [criteriaId]  - Optional WCAG SC filter (e.g. "1.1.1")
   * @returns {Promise<Array<object>>} Structured accessibility results
   */
  async analyze(html, criteriaId = null, lang = 'en') {
    const { timeoutMs, runOnly } = this._config.axe;
    let browser = null;

    await this._acquireSlot();
    try {
      this._logger.info('Launching Puppeteer browser...');
      browser = await this._puppeteer.launch({
        headless:       this._config.browser.headless,
        executablePath: this._config.browser.executablePath,
        ignoreHTTPSErrors: this._config.browser.ignoreHTTPSErrors,
        args:           this._config.browser.args,
      });

      const page = await browser.newPage();
      page.setDefaultTimeout(timeoutMs);
      page.setDefaultNavigationTimeout(timeoutMs);

      page.on('console', (msg) => {
        if (msg.type() === 'error') {
          this._logger.debug(`Browser console [${msg.type()}]: ${msg.text()}`);
        }
      });

      this._logger.info('Loading HTML content into page...');
      await page.setContent(html, { waitUntil: 'domcontentloaded', timeout: timeoutMs });

      this._logger.info('Injecting axe-core...');
      await this._injectAxe(page);
      await this._configureAxeLocale(page, lang);

      this._logger.info('Running axe.run() analysis...');
      const axeResults = await page.evaluate((runOptions) => {
        return new Promise((resolve, reject) => {
          // axe is available as a global after script injection
          // eslint-disable-next-line no-undef
          axe.run(document, { 
            runOnly: runOptions,
            resultTypes: ['violations', 'passes', 'incomplete']
          }, (err, results) => {
            if (err) reject(err);
            else resolve(results);
          });
        });
      }, runOnly);

      this._logger.info(
        `axe.run() complete — violations: ${axeResults.violations.length}, ` +
        `passes: ${axeResults.passes.length}, ` +
        `incomplete: ${(axeResults.incomplete || []).length}`
      );

      this._logger.info('Running static custom checks...');
      const customResults = await runStaticChecks(page, { lang });
      const filteredCustom = criteriaId
        ? customResults.filter(r => r && r.successCriteriaId === criteriaId)
        : customResults;
      this._logger.info(`Custom checks complete — ${filteredCustom.length} SC(s) returned.`);

      return mergeWithAxe(mapResults(axeResults, criteriaId), filteredCustom);
    } catch (err) {
      this._logger.error('Error during accessibility analysis:', err.message);
      throw err;
    } finally {
      if (browser) {
        await browser.close();
        this._logger.info('Browser closed.');
      }
      this._releaseSlot();
    }
  }

  /**
   * Crawls a URL and analyses its accessibility issues.
   *
   * @param {string} url                - Fully-qualified URL to crawl
   * @param {string|null} [criteriaId]  - Optional WCAG SC filter (e.g. "1.1.1")
   * @returns {Promise<Array<object>>} Structured accessibility results
   */
  async analyseUrl(url, criteriaId = null, lang = 'en') {
    const { timeoutMs, runOnly } = this._config.axe;
    let browser = null;

    await _assertPublicUrl(url);
    await this._acquireSlot();
    try {
      this._logger.info(`Launching Puppeteer browser for URL: ${url}`);
      browser = await this._puppeteer.launch({
        headless:       this._config.browser.headless,
        executablePath: this._config.browser.executablePath,
        ignoreHTTPSErrors: this._config.browser.ignoreHTTPSErrors,
        args:           this._config.browser.args,
      });

      const page = await browser.newPage();
      page.setDefaultTimeout(timeoutMs);
      page.setDefaultNavigationTimeout(timeoutMs);
      await page.setBypassCSP(true);

      page.on('console', (msg) => {
        if (msg.type() === 'error') {
          this._logger.debug(`Browser console [${msg.type()}]: ${msg.text()}`);
        }
      });

      // Bug 2 fix: enable request interception to block redirect-time SSRF hops.
      await page.setRequestInterception(true);
      _installSsrfInterceptor(page);

      this._logger.info(`Navigating to ${url}...`);
      // Use networkidle2 for live URL analysis so SPA and lazy JS content is loaded
      // before axe/custom checks run.
      await page.goto(url, { waitUntil: 'networkidle2', timeout: timeoutMs });

      this._logger.info('Injecting axe-core...');
      await this._injectAxe(page);
      await this._configureAxeLocale(page, lang);

      this._logger.info('Running axe.run() analysis...');
      const axeResults = await page.evaluate((runOptions) => {
        return new Promise((resolve, reject) => {
          // eslint-disable-next-line no-undef
          axe.run(document, { 
            runOnly: runOptions,
            resultTypes: ['violations', 'passes', 'incomplete']
          }, (err, results) => {
            if (err) reject(err);
            else resolve(results);
          });
        });
      }, runOnly);

      this._logger.info(
        `axe.run() complete — violations: ${axeResults.violations.length}, ` +
        `passes: ${axeResults.passes.length}, ` +
        `incomplete: ${(axeResults.incomplete || []).length}`
      );

      this._logger.info('Running all custom checks (static + interactive)...');
      const customResults = await runAll(page, { lang });
      const filteredCustom = criteriaId
        ? customResults.filter(r => r && r.successCriteriaId === criteriaId)
        : customResults;
      this._logger.info(`Custom checks complete — ${filteredCustom.length} SC(s) returned.`);

      return mergeWithAxe(mapResults(axeResults, criteriaId), filteredCustom);
    } catch (err) {
      this._logger.error(`Error during URL accessibility analysis: ${err.message}`);
      throw err;
    } finally {
      if (browser) {
        await browser.close();
        this._logger.info('Browser closed.');
      }
      this._releaseSlot();
    }
  }

  /**
   * Like analyseUrl but returns a flat, element-wise findings array
   * (one entry per failing/incomplete element, one per passing rule).
   *
   * @param {string} url - Fully-qualified URL
   * @returns {Promise<Array<object>>} Flat findings array
   */
  async analyseUrlFlat(url, level = 'AA', lang = 'en') {
    const { timeoutMs } = this._config.axe;
    const runOnly = { type: 'tag', values: _tagsForLevel(level) };
    let browser = null;

    await _assertPublicUrl(url);
    await this._acquireSlot();
    try {
      this._logger.info(`[flat] Launching browser for URL: ${url} level=${level}`);
      browser = await this._puppeteer.launch({
        headless:       this._config.browser.headless,
        executablePath: this._config.browser.executablePath,
        ignoreHTTPSErrors: this._config.browser.ignoreHTTPSErrors,
        args:           this._config.browser.args,
      });

      const page = await browser.newPage();
      page.setDefaultTimeout(timeoutMs);
      page.setDefaultNavigationTimeout(timeoutMs);
      await page.setBypassCSP(true);

      page.on('console', (msg) => {
        if (msg.type() === 'error') {
          this._logger.debug(`Browser console [${msg.type()}]: ${msg.text()}`);
        }
      });

      // Bug 2 fix: enable request interception to block redirect-time SSRF hops.
      await page.setRequestInterception(true);
      _installSsrfInterceptor(page);

      this._logger.info(`[flat] Navigating to ${url}...`);
      // Use networkidle2 for parity with audit runner requirements and better JS coverage.
      await page.goto(url, { waitUntil: 'networkidle2', timeout: timeoutMs });

      this._logger.info('[flat] Injecting axe-core...');
      await this._injectAxe(page, '[flat]');
      await this._configureAxeLocale(page, lang, '[flat]');

      this._logger.info('[flat] Running axe.run()...');
      const axeResults = await page.evaluate((runOptions) => {
        return new Promise((resolve, reject) => {
          // eslint-disable-next-line no-undef
          axe.run(document, { 
            runOnly: runOptions,
            resultTypes: ['violations', 'passes', 'incomplete']
          }, (err, results) => {
            if (err) reject(err);
            else resolve(results);
          });
        });
      }, runOnly);

      this._logger.info(
        `[flat] axe.run() complete — violations: ${axeResults.violations.length}, ` +
        `passes: ${axeResults.passes.length}, ` +
        `incomplete: ${(axeResults.incomplete || []).length}`
      );

      this._logger.info('[flat] Running all custom checks (static + interactive)...');
      let customResults = [];
      const customChecksTimeoutMs = 180000; // 3 minutes budget for custom checks
      let timeoutId;
      try {
        const timeoutPromise = new Promise((_, reject) => {
          timeoutId = setTimeout(() => reject(new Error('Custom checks timed out')), customChecksTimeoutMs);
        });
        customResults = await Promise.race([runAll(page, { lang }), timeoutPromise]);
      } catch (err) {
        this._logger.warn(`[flat] Custom checks failed or timed out: ${err.message}`);
      } finally {
        clearTimeout(timeoutId);
      }
      const allCustomFindings = mapCustomResultsFlat(customResults, url, lang);
      const allowedLevels = _allowedLevels(level);
      const customFindings = allCustomFindings.filter(f => !f.level || allowedLevels.has(f.level));
      this._logger.info(`[flat] Custom checks complete — ${customFindings.length} finding(s).`);

      const findings = [...mapResultsFlat(axeResults, url, lang), ...customFindings];
      const ORDER = { fail: 0, needs_review: 1, pass: 2 };
      findings.sort((a, b) => (ORDER[a.status] ?? 3) - (ORDER[b.status] ?? 3));
      return findings;
    } catch (err) {
      this._logger.error(`[flat] Error: ${err.message}`);
      throw err;
    } finally {
      if (browser) {
        await browser.close();
        this._logger.info('[flat] Browser closed.');
      }
      this._releaseSlot();
    }
  }
}

module.exports = AccessibilityService;
module.exports.SsrfGuardError = SsrfGuardError;
