'use strict';

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

  /**
   * Analyzes HTML for accessibility issues.
   *
   * @param {string} html               - Raw HTML string
   * @param {string|null} [criteriaId]  - Optional WCAG SC filter (e.g. "1.1.1")
   * @returns {Promise<Array<object>>} Structured accessibility results
   */
  async analyze(html, criteriaId = null) {
    const { timeoutMs, runOnly } = this._config.axe;
    let browser = null;

    await this._acquireSlot();
    try {
      this._logger.info('Launching Puppeteer browser...');
      browser = await this._puppeteer.launch({
        headless:       this._config.browser.headless,
        executablePath: this._config.browser.executablePath,
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
      await page.addScriptTag({ path: this._axeCorePath });

      this._logger.info('Running axe.run() analysis...');
      const axeResults = await page.evaluate((runOptions) => {
        return new Promise((resolve, reject) => {
          // axe is available as a global after script injection
          // eslint-disable-next-line no-undef
          axe.run(document, { runOnly: runOptions }, (err, results) => {
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
      const customResults = await runStaticChecks(page);
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
  async analyseUrl(url, criteriaId = null) {
    const { timeoutMs, runOnly } = this._config.axe;
    let browser = null;

    await _assertPublicUrl(url);
    await this._acquireSlot();
    try {
      this._logger.info(`Launching Puppeteer browser for URL: ${url}`);
      browser = await this._puppeteer.launch({
        headless:       this._config.browser.headless,
        executablePath: this._config.browser.executablePath,
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

      // Bug 2 fix: enable request interception to block redirect-time SSRF hops.
      await page.setRequestInterception(true);
      _installSsrfInterceptor(page);

      this._logger.info(`Navigating to ${url}...`);
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: timeoutMs });

      this._logger.info('Injecting axe-core...');
      await page.addScriptTag({ path: this._axeCorePath });

      this._logger.info('Running axe.run() analysis...');
      const axeResults = await page.evaluate((runOptions) => {
        return new Promise((resolve, reject) => {
          // eslint-disable-next-line no-undef
          axe.run(document, { runOnly: runOptions }, (err, results) => {
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
      const customResults = await runAll(page);
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
  async analyseUrlFlat(url, level = 'AA') {
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

      // Bug 2 fix: enable request interception to block redirect-time SSRF hops.
      await page.setRequestInterception(true);
      _installSsrfInterceptor(page);

      this._logger.info(`[flat] Navigating to ${url}...`);
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: timeoutMs });

      this._logger.info('[flat] Injecting axe-core...');
      await page.addScriptTag({ path: this._axeCorePath });

      this._logger.info('[flat] Running axe.run()...');
      const axeResults = await page.evaluate((runOptions) => {
        return new Promise((resolve, reject) => {
          // eslint-disable-next-line no-undef
          axe.run(document, { runOnly: runOptions }, (err, results) => {
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
      const customResults = await runAll(page);
      const allCustomFindings = mapCustomResultsFlat(customResults, url);
      const allowedLevels = _allowedLevels(level);
      const customFindings = allCustomFindings.filter(f => !f.level || allowedLevels.has(f.level));
      this._logger.info(`[flat] Custom checks complete — ${customFindings.length} finding(s).`);

      const findings = [...mapResultsFlat(axeResults, url), ...customFindings];
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
