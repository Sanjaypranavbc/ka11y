'use strict';

const { mapResults } = require('../utils/axeResultMapper');

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
    this._puppeteer   = puppeteer;
    this._axeCorePath = axeCorePath;
    this._logger      = logger;
    this._config      = config;
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

    try {
      this._logger.info('Launching Puppeteer browser...');
      browser = await this._puppeteer.launch({
        headless: this._config.browser.headless,
        args:     this._config.browser.args,
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

    try {
      this._logger.info(`Launching Puppeteer browser for URL: ${url}`);
      browser = await this._puppeteer.launch({
        headless: this._config.browser.headless,
        args:     this._config.browser.args,
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
    }
  }
}

module.exports = AccessibilityService;
