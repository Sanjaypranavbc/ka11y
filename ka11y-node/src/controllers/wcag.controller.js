'use strict';

const { SsrfGuardError } = require('../services/accessibility.service');

/**
 * WcagController — handles POST /api/v1/analyse-url-demo.
 * Validates input then delegates to WcagService.
 */
class WcagController {
  constructor(wcagService, logger) {
    this._service = wcagService;
    this._logger  = logger;
  }

  /**
   * @openapi
   * /api/v1/analyse-url-wcag:
   *   post:
   *     summary: Full WCAG 2.1 / 2.2 compliance analysis for a URL
   *     description: >
   *       Crawls the given URL with Puppeteer, runs axe-core + all custom checks,
   *       and returns results mapped to every criterion in the requested WCAG version.
   *       Criteria with no automated check are returned as "not_checked".
   *       Criteria that cannot be automated at all are returned as "manual_only".
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
   *                 example: "https://example.com"
   *               wcagVersion:
   *                 type: string
   *                 enum: ["2.1", "2.2"]
   *                 default: "2.2"
   *               lang:
   *                 type: string
   *                 default: "en"
   *                 example: "en"
   *               maxDepth:
   *                 type: integer
   *                 default: 0
   *                 minimum: 0
   *                 maximum: 10
   *                 description: >
   *                   Extra pages to scan from the site's sitemap.xml, on top
   *                   of the given URL. 0 = scan only the given URL. 1 = scan
   *                   the given URL plus 1 more page from the sitemap, etc.
   *     responses:
   *       200:
   *         description: Full WCAG compliance report
   *       400:
   *         description: Invalid or private URL
   *       500:
   *         description: Server or browser error
   */
  async analyseUrl(req, res) {
    const { url, wcagVersion = '2.2', lang = 'en', maxDepth = 0 } = req.body;

    if (!url || typeof url !== 'string') {
      return res.status(400).json({ error: 'url field is required and must be a string' });
    }

    let parsed;
    try { parsed = new URL(url); } catch {
      return res.status(400).json({ error: 'url must be a valid http or https URL' });
    }
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return res.status(400).json({ error: 'url must be a valid http or https URL' });
    }

    const depthNum = Number(maxDepth);
    if (!Number.isInteger(depthNum) || depthNum < 0 || depthNum > 10) {
      return res.status(400).json({ error: 'maxDepth must be an integer between 0 and 10' });
    }

    const version  = ['2.1', '2.2'].includes(wcagVersion) ? wcagVersion : '2.2';
    const safeLang = /^[a-z]{2}(-[a-zA-Z]{2,4})?$/.test(lang) ? lang : 'en';

    try {
      const result = await this._service.analyseUrl(url, { wcagVersion: version, lang: safeLang, maxDepth: depthNum });
      res.json(result);
    } catch (err) {
      if (err instanceof SsrfGuardError) {
        this._logger.warn(`wcag analyseUrl rejected (SSRF): ${err.message}`);
        return res.status(400).json({ error: 'Invalid URL', message: err.message });
      }
      if (/ERR_CERT_/i.test(err.message || '')) {
        return res.status(502).json({ error: 'Target TLS certificate invalid', message: err.message });
      }
      this._logger.error(`wcag analyseUrl failed: ${err.message}`);
      res.status(500).json({ error: 'Analysis failed', message: err.message });
    }
  }
}

module.exports = WcagController;
