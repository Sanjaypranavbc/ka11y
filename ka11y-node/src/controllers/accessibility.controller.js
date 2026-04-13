'use strict';

const { SsrfGuardError } = require('../services/accessibility.service');

/**
 * AccessibilityController — SRP: handles HTTP requests for accessibility analysis.
 */
class AccessibilityController {
  /**
   * @param {object} accessibilityService - Instance of AccessibilityService
   */
  constructor(accessibilityService, logger) {
    this._service = accessibilityService;
    this._logger  = logger;
  }

  /**
   * @openapi
   * /api/v1/analyze-accessibility:
   *   post:
   *     summary: Analyze HTML for accessibility issues
   *     description: >
   *       Analyzes HTML content for accessibility issues using axe-core and Puppeteer.
   *       Returns a list of rules with their status (fail / pass / incomplete),
   *       impact level, reason, and the mapped WCAG Success Criterion ID (e.g. "1.1.1").
   *
   *
   *       **Important:** The `html` value is a JSON string — use single quotes for
   *       HTML attributes (e.g. `src='logo.png'`) to avoid breaking the JSON.
   *     requestBody:
   *       required: true
   *       content:
   *         application/json:
   *           schema:
   *             type: object
   *             required:
   *               - html
   *             properties:
   *               html:
   *                 type: string
   *                 description: >
   *                   Raw HTML to analyze. Use single quotes for HTML attributes
   *                   to avoid breaking the JSON string.
   *               successCriteriaId:
   *                 type: string
   *                 nullable: true
   *                 description: >
   *                   Optional WCAG Success Criterion filter (e.g. "1.1.1").
   *                   When provided, only rules mapped to that criterion are returned.
   *                   Omit or set to null to return all rules.
   *                 example: "1.1.1"
   *           examples:
   *             image_with_alt:
   *               summary: Image with alt text (passes image-alt)
   *               value:
   *                 html: "<img src='logo.png' alt='Company Name'>"
   *             image_missing_alt:
   *               summary: Image missing alt — filter by SC 1.1.1
   *               value:
   *                 html: "<img src='logo.png'>"
   *                 successCriteriaId: "1.1.1"
   *             filter_311:
   *               summary: Filter by SC 3.1.1 (Language of Page)
   *               value:
   *                 html: "<html><head><title>Test</title></head><body><p>Hello</p></body></html>"
   *                 successCriteriaId: "3.1.1"
   *             full_page:
   *               summary: Full accessible page (no filter)
   *               value:
   *                 html: "<!DOCTYPE html><html lang='en'><head><title>My Page</title></head><body><main><h1>Hello World</h1><p>Welcome to my page.</p></main></body></html>"
   *             form_missing_label:
   *               summary: Form input missing label — filter by SC 4.1.2
   *               value:
   *                 html: "<form><input type='text' placeholder='Enter name'><button type='submit'>Submit</button></form>"
   *                 successCriteriaId: "4.1.2"
   *             button_missing_name:
   *               summary: Button with no accessible name — filter by SC 4.1.2
   *               value:
   *                 html: "<button></button>"
   *                 successCriteriaId: "4.1.2"
   *     responses:
   *       200:
   *         description: Accessibility analysis result grouped by WCAG Success Criterion
   *         content:
   *           application/json:
   *             schema:
   *               type: object
   *               properties:
   *                 results:
   *                   type: array
   *                   items:
   *                     type: object
   *                     properties:
   *                       successCriteriaId:
   *                         type: string
   *                         description: WCAG SC ID or "best-practice"
   *                         example: "1.1.1"
   *                       rules:
   *                         type: array
   *                         items:
   *                           type: object
   *                           properties:
   *                             ruleId:
   *                               type: string
   *                               example: image-alt
   *                             description:
   *                               type: string
   *                             impact:
   *                               type: string
   *                               nullable: true
   *                             status:
   *                               type: string
   *                               description: "fail | pass | incomplete"
   *                             reason:
   *                               type: string
   *                             helpUrl:
   *                               type: string
   *             example:
   *               results:
   *                 - successCriteriaId: "1.1.1"
   *                   rules:
   *                     - ruleId: image-alt
   *                       description: Ensure <img> elements have alternative text or a role of none or presentation
   *                       impact: critical
   *                       status: fail
   *                       reason: Element does not have an alt attribute
   *                       helpUrl: https://dequeuniversity.com/rules/axe/4.11/image-alt?application=axeAPI
   *                 - successCriteriaId: "2.4.2"
   *                   rules:
   *                     - ruleId: document-title
   *                       description: Ensure each HTML document contains a non-empty <title> element
   *                       impact: serious
   *                       status: fail
   *                       reason: Document does not have a non-empty <title> element
   *                       helpUrl: https://dequeuniversity.com/rules/axe/4.11/document-title?application=axeAPI
   *       400:
   *         description: Invalid input — html field missing or JSON is malformed
   *         content:
   *           application/json:
   *             example:
   *               error: Invalid JSON payload
   *               message: "Expected ',' or '}' after property value in JSON at position 23"
   *       500:
   *         description: Internal server error
   *         content:
   *           application/json:
   *             example:
   *               error: Accessibility analysis failed
   *               message: Protocol error — browser context was destroyed
   */
  async analyze(req, res) {
    const { html, successCriteriaId, lang = 'en' } = req.body;

    if (!html || typeof html !== 'string') {
      this._logger.warn('analyze rejected: html field missing or not a string');
      return res.status(400).json({ error: 'html field is required and must be a string' });
    }

    if (successCriteriaId != null && !/^\d+\.\d+\.\d+$/.test(successCriteriaId)) {
      return res.status(400).json({ error: 'successCriteriaId must match format X.Y.Z (e.g. "1.1.1")' });
    }

    try {
      const filter = successCriteriaId ?? null;
      const safeLang = /^[a-z]{2}(-[a-zA-Z]{2,4})?$/.test(lang) ? lang : 'en';
      this._logger.info(`analyze start successCriteriaId=${filter ?? 'none'} lang=${safeLang} htmlLength=${html.length}`);
      const results = await this._service.analyze(html, filter, safeLang);
      this._logger.info(`analyze done results=${results.length}`);
      res.json({ results });
    } catch (err) {
      this._logger.error(`analyze failed: ${err.message}`);
      res.status(500).json({
        error:   'Accessibility analysis failed',
        message: err.message,
      });
    }
  }

  /**
   * @openapi
   * /api/v1/analyse-url:
   *   post:
   *     summary: Analyse a live URL for accessibility issues
   *     description: >
   *       Crawls the given URL using Puppeteer, injects axe-core into the loaded page,
   *       and returns WCAG accessibility results in the same format as /analyze-accessibility.
   *     requestBody:
   *       required: true
   *       content:
   *         application/json:
   *           schema:
   *             type: object
   *             required:
   *               - url
   *             properties:
   *               url:
   *                 type: string
   *                 description: Fully-qualified URL to crawl and analyse (http or https).
   *                 example: "https://example.com"
   *               successCriteriaId:
   *                 type: string
   *                 nullable: true
   *                 description: >
   *                   Optional WCAG Success Criterion filter (e.g. "1.1.1").
   *                   Omit or set to null to return all rules.
   *                 example: "1.1.1"
   *           examples:
   *             basic_url:
   *               summary: Analyse a public URL
   *               value:
   *                 url: "https://example.com"
   *             url_with_filter:
   *               summary: Analyse and filter by SC 1.1.1
   *               value:
   *                 url: "https://example.com"
   *                 successCriteriaId: "1.1.1"
   *     responses:
   *       200:
   *         description: Accessibility analysis result grouped by WCAG Success Criterion
   *         content:
   *           application/json:
   *             schema:
   *               type: object
   *               properties:
   *                 url:
   *                   type: string
   *                   description: The URL that was analysed
   *                 results:
   *                   type: array
   *                   items:
   *                     type: object
   *                     properties:
   *                       successCriteriaId:
   *                         type: string
   *                         description: WCAG SC ID or "best-practice"
   *                         example: "1.1.1"
   *                       rules:
   *                         type: array
   *                         items:
   *                           type: object
   *                           properties:
   *                             ruleId:
   *                               type: string
   *                             description:
   *                               type: string
   *                             impact:
   *                               type: string
   *                               nullable: true
   *                             status:
   *                               type: string
   *                               description: "fail | pass | incomplete"
   *                             reason:
   *                               type: string
   *                             helpUrl:
   *                               type: string
   *       400:
   *         description: Invalid input — url field missing or not a valid http/https URL
   *         content:
   *           application/json:
   *             example:
   *               error: url field is required and must be a valid http or https URL
   *       500:
   *         description: Internal server error (navigation failure, timeout, etc.)
   *         content:
   *           application/json:
   *             example:
   *               error: URL accessibility analysis failed
   *               message: net::ERR_NAME_NOT_RESOLVED
   */
  async analyseUrlFlat(req, res) {
    const { url, level = 'AA', lang = 'en' } = req.body;

    if (!url || typeof url !== 'string') {
      return res.status(400).json({ error: 'url field is required and must be a string' });
    }

    let parsedUrl;
    try { parsedUrl = new URL(url); } catch {
      return res.status(400).json({ error: 'url field must be a valid http or https URL' });
    }
    if (parsedUrl.protocol !== 'http:' && parsedUrl.protocol !== 'https:') {
      return res.status(400).json({ error: 'url field must be a valid http or https URL' });
    }

    const wcagLevel = ['A', 'AA', 'AAA'].includes(level) ? level : 'AA';

    try {
      const safeLang = /^[a-z]{2}(-[a-zA-Z]{2,4})?$/.test(lang) ? lang : 'en';
      this._logger.info(`analyseUrlFlat start url=${url} level=${wcagLevel} lang=${safeLang}`);
      const findings = await this._service.analyseUrlFlat(url, wcagLevel, safeLang);
      this._logger.info(`analyseUrlFlat done findings=${findings.length}`);
      res.json({ url, findings });
    } catch (err) {
      // Bug 4 fix: SSRF guard failures are caused by invalid/private URLs submitted by the
      // client — they are not server faults. Return 400 so clients classify them correctly
      // and retry logic / monitoring treats them as bad input rather than server instability.
      if (err instanceof SsrfGuardError) {
        this._logger.warn(`analyseUrlFlat rejected (SSRF guard): ${err.message}`);
        return res.status(400).json({ error: 'Invalid URL', message: err.message });
      }
      if (/ERR_CERT_/i.test(err.message || '')) {
        this._logger.warn(`analyseUrlFlat rejected (TLS certificate): ${err.message}`);
        return res.status(502).json({ error: 'Target TLS certificate invalid', message: err.message });
      }
      this._logger.error(`analyseUrlFlat failed: ${err.message}`);
      res.status(500).json({ error: 'URL flat analysis failed', message: err.message });
    }
  }

  async analyseUrl(req, res) {
    const { url, successCriteriaId, lang = 'en' } = req.body;

    if (!url || typeof url !== 'string') {
      this._logger.warn('analyseUrl rejected: url field missing or not a string');
      return res.status(400).json({ error: 'url field is required and must be a valid http or https URL' });
    }

    let parsedUrl;
    try {
      parsedUrl = new URL(url);
    } catch {
      this._logger.warn(`analyseUrl rejected: invalid URL "${url}"`);
      return res.status(400).json({ error: 'url field is required and must be a valid http or https URL' });
    }

    if (parsedUrl.protocol !== 'http:' && parsedUrl.protocol !== 'https:') {
      this._logger.warn(`analyseUrl rejected: unsupported protocol "${parsedUrl.protocol}"`);
      return res.status(400).json({ error: 'url field is required and must be a valid http or https URL' });
    }

    if (successCriteriaId != null && !/^\d+\.\d+\.\d+$/.test(successCriteriaId)) {
      return res.status(400).json({ error: 'successCriteriaId must match format X.Y.Z (e.g. "1.1.1")' });
    }

    try {
      const filter = successCriteriaId ?? null;
      const safeLang = /^[a-z]{2}(-[a-zA-Z]{2,4})?$/.test(lang) ? lang : 'en';
      this._logger.info(`analyseUrl start url=${url} successCriteriaId=${filter ?? 'none'} lang=${safeLang}`);
      const results = await this._service.analyseUrl(url, filter, safeLang);
      this._logger.info(`analyseUrl done results=${results.length}`);
      res.json({ url, results });
    } catch (err) {
      if (err instanceof SsrfGuardError) {
        this._logger.warn(`analyseUrl rejected (SSRF guard): ${err.message}`);
        return res.status(400).json({ error: 'Invalid URL', message: err.message });
      }
      if (/ERR_CERT_/i.test(err.message || '')) {
        this._logger.warn(`analyseUrl rejected (TLS certificate): ${err.message}`);
        return res.status(502).json({ error: 'Target TLS certificate invalid', message: err.message });
      }
      this._logger.error(`analyseUrl failed: ${err.message}`);
      res.status(500).json({
        error:   'URL accessibility analysis failed',
        message: err.message,
      });
    }
  }

  async analyseRuleUrl(req, res) {
    const { successCriteriaId } = req.params;
    const { url, lang = 'en' } = req.body;

    if (!/^\d+\.\d+\.\d+$/.test(successCriteriaId || '')) {
      return res.status(400).json({ error: 'successCriteriaId must match format X.Y.Z (e.g. "1.1.1")' });
    }

    if (!url || typeof url !== 'string') {
      this._logger.warn('analyseRuleUrl rejected: url field missing or not a string');
      return res.status(400).json({ error: 'url field is required and must be a valid http or https URL' });
    }

    let parsedUrl;
    try {
      parsedUrl = new URL(url);
    } catch {
      this._logger.warn(`analyseRuleUrl rejected: invalid URL "${url}"`);
      return res.status(400).json({ error: 'url field is required and must be a valid http or https URL' });
    }

    if (parsedUrl.protocol !== 'http:' && parsedUrl.protocol !== 'https:') {
      this._logger.warn(`analyseRuleUrl rejected: unsupported protocol "${parsedUrl.protocol}"`);
      return res.status(400).json({ error: 'url field is required and must be a valid http or https URL' });
    }

    try {
      const safeLang = /^[a-z]{2}(-[a-zA-Z]{2,4})?$/.test(lang) ? lang : 'en';
      this._logger.info(`analyseRuleUrl start url=${url} successCriteriaId=${successCriteriaId} lang=${safeLang}`);
      const results = await this._service.analyseUrl(url, successCriteriaId, safeLang);
      this._logger.info(`analyseRuleUrl done results=${results.length}`);
      res.json({ url, successCriteriaId, results });
    } catch (err) {
      if (err instanceof SsrfGuardError) {
        this._logger.warn(`analyseRuleUrl rejected (SSRF guard): ${err.message}`);
        return res.status(400).json({ error: 'Invalid URL', message: err.message });
      }
      if (/ERR_CERT_/i.test(err.message || '')) {
        this._logger.warn(`analyseRuleUrl rejected (TLS certificate): ${err.message}`);
        return res.status(502).json({ error: 'Target TLS certificate invalid', message: err.message });
      }
      this._logger.error(`analyseRuleUrl failed: ${err.message}`);
      res.status(500).json({
        error: 'URL accessibility analysis failed',
        message: err.message,
      });
    }
  }
}

module.exports = AccessibilityController;
