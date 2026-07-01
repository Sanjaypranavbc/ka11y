'use strict';

const fs = require('fs');
const path = require('path');
const dns = require('dns').promises;
const { mapResults, mapResultsFlat, mapCustomResultsFlat, axeRuleIdsForCriteria } = require('../utils/axeResultMapper');
const { generateReport } = require('../utils/reportGenerator');
const { StageTimings, NULL_TIMINGS } = require('../utils/stageTimings');
const { runAll, runStaticChecks, mergeWithAxe } = require('../custom-checks/index');
const { boundedBfs } = require('../utils/crawl');
const { canonicalizeUrl } = require('../utils/canonicalUrl');

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

/**
 * Pick the axe runOnly for a request. When a single WCAG SC is requested, run
 * only the axe rules mapped to it (`{ type: 'rule', values: [...] }`) so axe does
 * not waste time on unrelated rules. Falls back to `defaultRunOnly` when the
 * criterion has no axe rules (custom-check-only SC) or when none is requested.
 */
function _runOnlyForCriteria(criteriaId, defaultRunOnly) {
  if (!criteriaId) return defaultRunOnly;
  const ruleIds = axeRuleIdsForCriteria(criteriaId);
  return ruleIds.length ? { type: 'rule', values: ruleIds } : defaultRunOnly;
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
    this._puppeteer = puppeteer;
    this._axeCorePath = axeCorePath;
    this._logger = logger;
    this._config = config;
    this._activeCount = 0;
    this._waitQueue = [];
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

        // @accesslint/core is optional — skip gracefully if not installed
        try {
          const alDir = require('path').dirname(require.resolve('@accesslint/core'));
          const alIifePath = require('path').join(alDir, 'index.iife.js');
          await page.addScriptTag({ path: alIifePath });
        } catch (alErr) {
          this._logger.debug(`${prefix}@accesslint/core not available, skipping: ${alErr.message}`);
        }

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
   * Runs axe.run() in the browser context with a Node-side timeout.
   *
   * Bug fix (§7.3): the previous Promise.race + setTimeout pattern resolved
   * on timeout but never cancelled the in-flight axe.run, so when the outer
   * caller closed the browser the still-pending evaluate would surface a
   * "Target closed" or "Execution context was destroyed" error as an
   * unhandled rejection. We now:
   *   1. Set a window.__ka11yAxeAbort flag so callers / future axe versions
   *      can cooperate with cancellation.
   *   2. Always clear the timer on settle (try/finally).
   *   3. Attach a noop catch to the still-pending evaluate so the eventual
   *      "Target closed" rejection is silently absorbed.
   *
   * @param {object} page                 - Puppeteer page
   * @param {object} runOnly              - axe runOnly options
   * @param {number} [timeoutMs]          - Override timeout (default: config.axe.timeoutMs || 90000)
   * @param {string} [logPrefix='']       - Optional log prefix
   * @returns {Promise<object>} axe results
   */
  async _runAxeWithTimeout(page, runOnly, timeoutMs, logPrefix = '') {
    const prefix = logPrefix ? `${logPrefix} ` : '';
    const effectiveTimeoutMs = Number.isFinite(timeoutMs) && timeoutMs > 0
      ? timeoutMs
      : (this._config.axe.timeoutMs || 90_000);

    // Best-effort: set the abort flag in browser context. Tolerate failure
    // so test mocks that don't care about extra evaluate calls still work.
    try {
      await page.evaluate(() => { window.__ka11yAxeAbort = false; });
    } catch (_) { /* page may not be ready or mock not configured — ignore */ }

    let timeoutHandle;

    const axeRunPromise = page.evaluate((runOptions) => {
      return new Promise((resolve, reject) => {
        // eslint-disable-next-line no-undef
        axe.run(document, {
          runOnly: runOptions,
          resultTypes: ['violations', 'passes', 'incomplete'],
        }, (err, results) => {
          if (err) reject(err);
          else resolve(results);
        });
      });
    }, runOnly);

    const timeoutPromise = new Promise((_, reject) => {
      timeoutHandle = setTimeout(async () => {
        // Signal cancellation to the browser context (best effort).
        try {
          await page.evaluate(() => {
            try { window.__ka11yAxeAbort = true; } catch (_) { }
            // eslint-disable-next-line no-undef
            if (typeof axe !== 'undefined' && typeof axe._abortAll === 'function') {
              try { axe._abortAll(); } catch (_) { }
            }
          });
        } catch (e) {
          this._logger.debug(`${prefix}Could not signal axe abort: ${e.message}`);
        }
        reject(new Error(`${prefix}axe.run timed out after ${effectiveTimeoutMs}ms`));
      }, effectiveTimeoutMs);
    });

    try {
      return await Promise.race([axeRunPromise, timeoutPromise]);
    } finally {
      clearTimeout(timeoutHandle);
      // Silently absorb the eventual rejection of the still-pending evaluate
      // when the outer caller closes the browser. Without this, "Target
      // closed" surfaces as an unhandled rejection.
      axeRunPromise.catch((e) => {
        const msg = (e && e.message) || '';
        if (msg.includes('Target closed') ||
          msg.includes('Execution context was destroyed') ||
          msg.includes('Session closed')) {
          this._logger.debug(`${prefix}Late axe.run rejection after browser closed: ${msg}`);
        } else {
          this._logger.debug(`${prefix}Late axe.run rejection: ${msg}`);
        }
      });
    }
  }

  /**
   * Enriches axe violation/incomplete nodes with bounding box (and optionally
   * a per-element screenshot) while the Puppeteer page is still open.
   * Mutates nodes in-place so mapResults / mapResultsFlat can pass the data through.
   *
   * @param {object} page         - Puppeteer page
   * @param {object} axeResults   - Raw axe.run() output
   * @param {object} [opts]
   * @param {boolean} [opts.screenshots=false] - Also capture element screenshots
   */
  async _enrichViolationNodes(page, axeResults, opts = {}) {
    const withScreenshots = opts.screenshots === true;
    const categories = [
      ...(axeResults.violations || []),
      ...(axeResults.incomplete || []),
    ];
    for (const rule of categories) {
      for (const node of (rule.nodes || [])) {
        const selector = Array.isArray(node.target) ? node.target[0] : null;
        if (!selector || typeof selector !== 'string') continue;
        try {
          const el = await page.$(selector);
          if (!el) continue;
          node.boundingBox = await el.boundingBox();
          if (withScreenshots && node.boundingBox) {
            node.screenshot = await el.screenshot({ encoding: 'base64' }).catch(() => null);
          }
        } catch (e) {
          this._logger.debug(`Element enrichment skipped for "${selector}": ${e.message}`);
        }
      }
    }
    return axeResults;
  }

  /**
   * Analyses a URL and returns a self-contained HTML accessibility report.
   * Captures the full page screenshot and per-element screenshots for all violations.
   *
   * @param {string} url   - Fully-qualified URL
   * @param {string} lang  - Output language code
   * @returns {Promise<string>} Self-contained HTML report
   */
  async analyseUrlReport(url, lang = 'en') {
    const { timeoutMs, runOnly } = this._config.axe;
    let browser = null;

    await _assertPublicUrl(url);
    await this._acquireSlot();
    try {
      this._logger.info(`[report] Launching browser for URL: ${url}`);
      browser = await this._puppeteer.launch({
        headless: this._config.browser.headless,
        executablePath: this._config.browser.executablePath,
        ignoreHTTPSErrors: this._config.browser.ignoreHTTPSErrors,
        args: this._config.browser.args,
      });

      const page = await browser.newPage();
      page.setDefaultTimeout(timeoutMs);
      page.setDefaultNavigationTimeout(timeoutMs);
      await page.setBypassCSP(true);
      await page.setViewport({ width: 1280, height: 800 });

      page.on('console', (msg) => {
        if (msg.type() === 'error') {
          this._logger.debug(`[report] Browser console [error]: ${msg.text()}`);
        }
      });

      await page.setRequestInterception(true);
      _installSsrfInterceptor(page);

      const POST_NAV_SETTLE_MS = parseInt(process.env.POST_NAV_SETTLE_MS) || 1000;
      this._logger.info(`[report] Navigating to ${url}...`);
      await page.goto(url, { waitUntil: 'load', timeout: timeoutMs });
      await new Promise(r => setTimeout(r, POST_NAV_SETTLE_MS));

      const pageWidth = await page.evaluate(() => document.documentElement.scrollWidth).catch(() => 1280);

      await this._injectAxe(page, '[report]');
      await this._configureAxeLocale(page, lang, '[report]');

      const axeResults = await this._runAxeWithTimeout(page, runOnly, timeoutMs, '[report]');
      this._logger.info(
        `[report] axe.run() — violations: ${axeResults.violations.length}, ` +
        `incomplete: ${(axeResults.incomplete || []).length}`
      );

      await this._enrichViolationNodes(page, axeResults, { screenshots: true });

      const pageScreenshot = await page.screenshot({ encoding: 'base64', fullPage: true }).catch((e) => {
        this._logger.warn(`[report] Full-page screenshot failed: ${e.message}`);
        return null;
      });

      let customResults = [];
      try {
        customResults = await runAll(page, { lang });
      } catch (e) {
        this._logger.warn(`[report] Custom checks failed: ${e.message}`);
      }

      const findings = [
        ...mapResultsFlat(axeResults, url, lang),
        ...mapCustomResultsFlat(customResults, url, lang),
      ];

      const ORDER = { fail: 0, needs_review: 1, pass: 2 };
      findings.sort((a, b) => (ORDER[a.status] ?? 3) - (ORDER[b.status] ?? 3));

      this._logger.info(`[report] Generating HTML report — ${findings.length} finding(s).`);
      return generateReport({ url, findings, pageScreenshot, pageWidth });
    } catch (err) {
      this._logger.error(`[report] Error: ${err.message}`);
      throw err;
    } finally {
      if (browser) {
        await browser.close();
        this._logger.info('[report] Browser closed.');
      }
      this._releaseSlot();
    }
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
        headless: this._config.browser.headless,
        executablePath: this._config.browser.executablePath,
        ignoreHTTPSErrors: this._config.browser.ignoreHTTPSErrors,
        args: this._config.browser.args,
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
      // When a single criterion is requested, run only the axe rules mapped to it.
      const axeRunOnly = _runOnlyForCriteria(criteriaId, runOnly);
      const axeResults = await this._runAxeWithTimeout(page, axeRunOnly, timeoutMs);

      this._logger.info('Running AccessLint sequentially...');
      const accessLintResults = await page.evaluate(() => {
        // Immediately run AccessLint natively
        if (!window.AccessLint) return null;
        const alResRaw = window.AccessLint.runAudit(document);
        
        // Sanitize out live HTML elements because Puppeteer cannot serialize them to JSON
        return {
          ...alResRaw,
          violations: (alResRaw.violations || []).map(v => {
            const { element, source, ...safeProps } = v;
            return safeProps;
          })
        };
      });

      this._logger.info(
        `axe.run() complete — violations: ${axeResults.violations.length}, ` +
        `passes: ${axeResults.passes.length}, ` +
        `incomplete: ${(axeResults.incomplete || []).length}`
      );

      this._logger.info('Running static custom checks...');
      // Push the criterion into the runner so only the relevant check executes
      // (preserves lang for full audits where no criterion is filtered).
      const customResults = await runStaticChecks(page, criteriaId != null ? criteriaId : { lang });
      this._logger.info(`Custom checks complete — ${customResults.length} SC(s) returned.`);

      return mergeWithAxe(mapResults(axeResults, criteriaId, accessLintResults), customResults);
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
        headless: this._config.browser.headless,
        executablePath: this._config.browser.executablePath,
        ignoreHTTPSErrors: this._config.browser.ignoreHTTPSErrors,
        args: this._config.browser.args,
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
      // 'load' fires once the DOM + subresources are ready, which is enough for
      // axe + custom checks. 'networkidle2' waits for analytics/ad network
      // connections to go quiet — that can add 10–30 s on news/SPA sites with
      // no benefit to the accessibility scan. A short fixed settle gives JS
      // frameworks time to finish their first render without the open-ended wait.
      const POST_NAV_SETTLE_MS = parseInt(process.env.POST_NAV_SETTLE_MS) || 500;
      await page.goto(url, { waitUntil: 'load', timeout: timeoutMs });
      // Wait for DOM to stop mutating (SPA hydration), capped at POST_NAV_SETTLE_MS
      await page.waitForFunction((maxMs) => new Promise(resolve => {
        const deadline = Date.now() + maxMs;
        let timer;
        const obs = new MutationObserver(() => {
          clearTimeout(timer);
          if (Date.now() >= deadline) { obs.disconnect(); resolve(true); return; }
          timer = setTimeout(() => { obs.disconnect(); resolve(true); }, 150);
        });
        obs.observe(document.body || document.documentElement, { childList: true, subtree: true, attributes: true });
        timer = setTimeout(() => { obs.disconnect(); resolve(true); }, Math.min(150, maxMs));
      }), { timeout: POST_NAV_SETTLE_MS + 500 }, POST_NAV_SETTLE_MS).catch(() => {});

      this._logger.info('Injecting axe-core...');
      await this._injectAxe(page);
      await this._configureAxeLocale(page, lang);

      this._logger.info('Running axe.run() analysis...');
      const axeRunOnly = _runOnlyForCriteria(criteriaId, runOnly);
      const axeResults = await this._runAxeWithTimeout(page, axeRunOnly, timeoutMs);

      this._logger.info('Running AccessLint sequentially...');
      const accessLintResults = await page.evaluate(() => {
        // Immediately run AccessLint natively
        if (!window.AccessLint) return null;
        const alResRaw = window.AccessLint.runAudit(document);
        
        // Sanitize out live HTML elements because Puppeteer cannot serialize them to JSON
        return {
          ...alResRaw,
          violations: (alResRaw.violations || []).map(v => {
            const { element, source, ...safeProps } = v;
            return safeProps;
          })
        };
      });

      this._logger.info(
        `axe.run() complete — violations: ${axeResults.violations.length}, ` +
        `passes: ${axeResults.passes.length}, ` +
        `incomplete: ${(axeResults.incomplete || []).length}`
      );

      this._logger.info('Running all custom checks (static + interactive)...');
      const customResults = await runAll(page, criteriaId != null ? criteriaId : { lang });
      this._logger.info(`Custom checks complete — ${customResults.length} SC(s) returned.`);

      return mergeWithAxe(mapResults(axeResults, criteriaId, accessLintResults), customResults);
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
  async analyseUrlFlat(url, level = 'AA', lang = 'en', options = {}) {
    const {
      maxDepth = 0,
      maxPages = 50,
      internalLinks = true,
      successCriteriaId = null,
      // Optional per-request timing collector. When set, every per-page step
      // (navigate, axe, custom checks, mapping) appends a row. The route
      // handler builds the collector from `jobId` in the request body so the
      // Python caller can mirror these rows into its own JSONL.
      timings = NULL_TIMINGS,
      // R-1: snapshot-fed mode. When the Python caller has already built a
      // universal snapshot it forwards the discovered page URLs here. We then
      // visit exactly that set with no further BFS and no time-budget cliff —
      // the snapshot is the source of truth, the same way the Python image
      // crawler treats it (see crawler.py snapshot_fed mode). Empty array =
      // fall back to the legacy boundedBfs path so existing callers are
      // unchanged.
      discoveredUrls = [],
    } = options;
    const { timeoutMs } = this._config.axe;
    let browser = null;

    await _assertPublicUrl(url);
    await this._acquireSlot();
    try {
      this._logger.info(
        `[flat] Launching browser for URL: ${url} level=${level} ` +
        `maxDepth=${maxDepth} internalLinks=${internalLinks} maxPages=${maxPages}`
      );
      browser = await this._puppeteer.launch({
        headless: this._config.browser.headless,
        executablePath: this._config.browser.executablePath,
        ignoreHTTPSErrors: this._config.browser.ignoreHTTPSErrors,
        args: this._config.browser.args,
      });

      // Single browser is reused across all crawled pages (one Chromium, many
      // pages) so deep crawls don't spawn a process per URL.
      const allFindings = [];
      const seen = new Set(); // cross-page dedup of identical findings

      // Per-page audit closure shared by both the snapshot-fed and BFS paths.
      const auditOne = async (pageUrl, depth) => {
        const { findings, links } = await this._auditPageFlat(
          browser, pageUrl, level, lang, successCriteriaId, { timings, depth }
        );
        for (const f of findings) {
          // Dedup across pages by (pageUrl, ruleId, selector, status).
          const key = `${f.pageUrl || pageUrl}|${f.ruleId || f.rule_id || ''}|${f.selector || f.target || ''}|${f.status}`;
          if (seen.has(key)) continue;
          seen.add(key);
          allFindings.push(f);
        }
        return links;
      };

      let pagesCrawled = 0;
      if (Array.isArray(discoveredUrls) && discoveredUrls.length > 0) {
        // R-1: snapshot-fed mode. Visit exactly the URLs Python's snapshot
        // discovered — no BFS, no time budget, mirrors Python's image_crawler
        // snapshot_fed behaviour. Each page is still capped by perPageMs via
        // the per-page custom-checks budget inside _auditPageFlat.
        this._logger.info(
          `[flat][crawl] snapshot-fed: ${discoveredUrls.length} URL(s) ` +
          `from caller; skipping BFS`
        );
        for (const pageUrl of discoveredUrls) {
          try {
            await auditOne(pageUrl, 0);
            pagesCrawled++;
          } catch (err) {
            this._logger.warn(
              `[flat][crawl] snapshot-fed page failed: ${pageUrl} — ${err.message}`
            );
          }
        }
        // Surface a budget-style row to the timing log so the Python summary
        // can show snapshot-fed-mode coverage alongside image_crawl_budget.
        timings.record({
          stage: 'axe_core',
          sub_stage: 'axe_crawl_budget',
          duration_ms: 0,
          item_count: pagesCrawled,
          status: 'ok',
          extra: {
            discovered: discoveredUrls.length,
            audited: pagesCrawled,
            clipped: Math.max(0, discoveredUrls.length - pagesCrawled),
            snapshot_fed: true,
          },
        });
      } else {
        // Legacy independent BFS path. Used when the caller didn't supply
        // discoveredUrls (e.g. single-page audits or direct Node calls).
        pagesCrawled = await boundedBfs({
          baseUrl: url,
          maxDepth,
          maxPages,
          internalLinksOnly: internalLinks,
          // Keep the whole crawl under the Python caller's HTTP timeout so a deep
          // crawl returns partial findings instead of the caller timing out and
          // discarding everything; per-page cap keeps the loop responsive.
          maxTotalMs: this._config.axe.flatCrawlBudgetMs,
          perPageMs: this._config.axe.flatPerPageMs,
          log: (msg) => this._logger.info(`[flat][crawl] ${msg}`),
          visit: auditOne,
        });
        // D-5: surface BFS clip status in the timing log so the Python summary
        // can show why Node only audited N of M pages without grepping logs.
        timings.record({
          stage: 'axe_core',
          sub_stage: 'axe_crawl_budget',
          duration_ms: 0,
          item_count: pagesCrawled,
          status: 'ok',
          extra: {
            audited: pagesCrawled,
            max_pages: maxPages,
            max_depth: maxDepth,
            time_budget_ms: this._config.axe.flatCrawlBudgetMs,
            snapshot_fed: false,
          },
        });
      }
      const ORDER = { fail: 0, needs_review: 1, pass: 2 };
      allFindings.sort((a, b) => (ORDER[a.status] ?? 3) - (ORDER[b.status] ?? 3));
      this._logger.info(
        `[flat] done: ${allFindings.length} finding(s) across ${pagesCrawled} page(s).`
      );
      return allFindings;
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

  /**
   * Audit ONE page (axe + custom checks) and return flat findings plus the
   * in-page hrefs (for the crawler to follow). Tags every finding with
   * `pageUrl` so multi-page reports attribute findings to the right page.
   *
   * @param {import('puppeteer').Browser} browser  Shared browser instance.
   * @param {string} url
   * @param {string} level
   * @param {string} lang
   * @param {string|null} successCriteriaId  Optional SC filter.
   * @returns {Promise<{findings: object[], links: string[]}>}
   */
  async _auditPageFlat(browser, url, level = 'AA', lang = 'en', successCriteriaId = null, opts = {}) {
    const { timeoutMs } = this._config.axe;
    const runOnly = { type: 'tag', values: _tagsForLevel(level) };
    // Per-page timing collector. NULL_TIMINGS when the caller didn't supply
    // one — every `record` / `time` call becomes a no-op then.
    const timings = opts.timings || NULL_TIMINGS;
    const depth = (opts.depth == null) ? null : opts.depth;

    const page = await browser.newPage();
    try {
      page.setDefaultTimeout(timeoutMs);
      page.setDefaultNavigationTimeout(timeoutMs);
      await page.setBypassCSP(true);

      page.on('console', (msg) => {
        if (msg.type() === 'error') {
          this._logger.debug(`Browser console [${msg.type()}]: ${msg.text()}`);
        }
      });

      // Block redirect-time SSRF hops.
      await page.setRequestInterception(true);
      _installSsrfInterceptor(page);

      this._logger.info(`[flat] Navigating to ${url}...`);
      const POST_NAV_SETTLE_MS = parseInt(process.env.POST_NAV_SETTLE_MS) || 1000;
      await timings.time(
        { stage: 'axe_core', sub_stage: 'page_navigate', page_url: url, depth },
        async () => {
          await page.goto(url, { waitUntil: 'load', timeout: timeoutMs });
          await new Promise(r => setTimeout(r, POST_NAV_SETTLE_MS));
        },
      );

      // Stamp findings with the URL the page actually resolved to, not the URL
      // we were asked to visit. A snapshot-fed child can be discovered as
      // ``/worldwide`` yet 301 to ``/worldwide.html`` (or vice-versa); when the
      // same page is audited directly the user passes the resolved form. Using
      // the requested URL split that one page's findings across two page_url
      // buckets, so a child page lost the half of its findings that came from
      // the other engine. ``page.url()`` collapses both to one identity. Fall
      // back to the requested URL if the browser reports nothing usable.
      let resolvedUrl = url;
      try {
        if (typeof page.url === 'function') {
          resolvedUrl = canonicalizeUrl(page.url()) || url;
        }
      } catch (e) {
        this._logger.debug(`[flat] page.url() read failed for ${url}: ${e.message}`);
      }

      await timings.time(
        { stage: 'axe_core', sub_stage: 'inject_axe', page_url: url, depth },
        async () => {
          await this._injectAxe(page, '[flat]');
          await this._configureAxeLocale(page, lang, '[flat]');
        },
      );

      const axeResults = await timings.time(
        { stage: 'axe_core', sub_stage: 'axe_run', page_url: url, depth },
        () => this._runAxeWithTimeout(page, runOnly, timeoutMs, '[flat]'),
      );
      this._logger.info(
        `[flat] axe.run() ${url} — violations: ${axeResults.violations.length}, ` +
        `passes: ${axeResults.passes.length}, ` +
        `incomplete: ${(axeResults.incomplete || []).length}`
      );

      // Per-page custom-checks budget. Kept modest so one page can't dominate a
      // multi-page crawl's overall time budget (see boundedBfs maxTotalMs).
      // The budget is now handed to runAll which splits it between the static
      // and interactive phases — previously a single Promise.race over runAll
      // forfeited *all* completed work when the timer fired, so on heavy deep
      // pages we lost focus-visible / focus-appearance / on-focus / on-input
      // / keyboard-trap findings entirely. Splitting preserves partial work.
      const customChecksTimeoutMs = this._config.axe.customChecksTimeoutMs;
      let customResults = [];
      try {
        customResults = await timings.time(
          { stage: 'axe_core', sub_stage: 'custom_checks', page_url: url, depth },
          () => runAll(page, { lang, timeoutMs: customChecksTimeoutMs }),
        );
      } catch (err) {
        this._logger.warn(`[flat] Custom checks failed for ${url}: ${err.message}`);
      }

      const mappingStart = process.hrtime.bigint();
      const allCustomFindings = mapCustomResultsFlat(customResults, resolvedUrl, lang);
      const allowedLevels = _allowedLevels(level);
      let customFindings = allCustomFindings.filter(f => !f.level || allowedLevels.has(f.level));

      let findings = [...mapResultsFlat(axeResults, resolvedUrl, lang), ...customFindings];
      timings.record({
        stage: 'axe_core',
        sub_stage: 'result_mapping',
        page_url: url,
        depth,
        duration_ms: Number(process.hrtime.bigint() - mappingStart) / 1e6,
        item_count: findings.length,
      });

      // Optional SC filter (now honoured in flat mode too).
      if (successCriteriaId) {
        findings = findings.filter(
          f => (f.successCriteriaId || f.success_criteria_id || f.wcag_sc) === successCriteriaId
        );
      }

      // Ensure every finding records the page it came from (multi-page reports).
      for (const f of findings) {
        if (!f.pageUrl) f.pageUrl = resolvedUrl;
      }

      // Collect same-page hrefs for the crawler to consider.
      let links = [];
      try {
        links = await page.$$eval('a[href]', els => els.map(e => e.href));
      } catch {
        links = [];
      }

      return { findings, links };
    } finally {
      try {
        await page.close();
      } catch (e) {
        this._logger.debug(`[flat] page close raised for ${url}: ${e.message}`);
      }
    }
  }
}

module.exports = AccessibilityService;
module.exports.SsrfGuardError = SsrfGuardError;
