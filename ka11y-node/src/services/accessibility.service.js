'use strict';

const dns = require('dns').promises;
const { mapResults, mapResultsFlat } = require('../utils/axeResultMapper');

const _PRIVATE_IP_RE = [
  /^127\./,
  /^10\./,
  /^172\.(1[6-9]|2\d|3[01])\./,
  /^192\.168\./,
  /^169\.254\./,
  /^::1$/,
  /^fc[0-9a-f]{2}:/i,
  /^fe80:/i,
];

async function _assertPublicUrl(url) {
  const { hostname } = new URL(url);
  let addresses;
  try {
    addresses = await dns.resolve4(hostname);
  } catch {
    throw new Error(`SSRF guard: DNS resolution failed for ${hostname}`);
  }
  for (const ip of addresses) {
    if (_PRIVATE_IP_RE.some(re => re.test(ip))) {
      throw new Error(`SSRF guard: ${hostname} resolves to private IP ${ip}`);
    }
  }
}

const MAX_CONCURRENT = parseInt(process.env.PUPPETEER_MAX_CONCURRENT) || 3;

/**
 * Map a WCAG conformance level string to axe-core tag arrays.
 * "A"   → Level A tags only
 * "AA"  → Level A + AA tags (default)
 * "AAA" → Level A + AA + AAA tags
 */
function _tagsForLevel(level) {
  const tags = ['wcag2a', 'wcag21a', 'best-practice'];
  if (level === 'AA' || level === 'AAA') tags.push('wcag2aa', 'wcag21aa');
  if (level === 'AAA') tags.push('wcag2aaa');
  return tags;
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
          axe.run(document, runOptions, (err, results) => {
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

      return mapResults(axeResults, criteriaId);
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

      this._logger.info(`Navigating to ${url}...`);
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: timeoutMs });

      this._logger.info('Injecting axe-core...');
      await page.addScriptTag({ path: this._axeCorePath });

      this._logger.info('Running axe.run() analysis...');
      const axeResults = await page.evaluate((runOptions) => {
        return new Promise((resolve, reject) => {
          // eslint-disable-next-line no-undef
          axe.run(document, runOptions, (err, results) => {
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

      return mapResults(axeResults, criteriaId);
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

      this._logger.info(`[flat] Navigating to ${url}...`);
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: timeoutMs });

      this._logger.info('[flat] Injecting axe-core...');
      await page.addScriptTag({ path: this._axeCorePath });

      this._logger.info('[flat] Running axe.run()...');
      const axeResults = await page.evaluate((runOptions) => {
        return new Promise((resolve, reject) => {
          // eslint-disable-next-line no-undef
          axe.run(document, runOptions, (err, results) => {
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

      return mapResultsFlat(axeResults, url);
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
