'use strict';

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
   * /analyze-accessibility:
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
   *         description: Accessibility analysis result
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
   *                       ruleId:
   *                         type: string
   *                         description: axe-core rule identifier
   *                         example: image-alt
   *                       description:
   *                         type: string
   *                         description: Human-readable rule description
   *                         example: Ensure <img> elements have alternative text
   *                       impact:
   *                         type: string
   *                         nullable: true
   *                         description: "Severity: critical | serious | moderate | minor | null"
   *                         example: critical
   *                       status:
   *                         type: string
   *                         description: "Result: fail | pass | incomplete"
   *                         example: fail
   *                       reason:
   *                         type: string
   *                         description: Why the rule failed or passed
   *                         example: Element does not have an alt attribute
   *                       helpUrl:
   *                         type: string
   *                         description: Link to full rule documentation
   *                         example: https://dequeuniversity.com/rules/axe/4.11/image-alt
   *             example:
   *               results:
   *                 - ruleId: image-alt
   *                   description: Ensure <img> elements have alternative text or a role of none or presentation
   *                   impact: critical
   *                   status: fail
   *                   reason: Element does not have an alt attribute
   *                   helpUrl: https://dequeuniversity.com/rules/axe/4.11/image-alt?application=axeAPI
   *                 - ruleId: document-title
   *                   description: Ensure each HTML document contains a non-empty <title> element
   *                   impact: serious
   *                   status: fail
   *                   reason: Document does not have a non-empty <title> element
   *                   helpUrl: https://dequeuniversity.com/rules/axe/4.11/document-title?application=axeAPI
   *                 - ruleId: aria-hidden-body
   *                   description: Ensure aria-hidden="true" is not present on the document body.
   *                   impact: null
   *                   status: pass
   *                   reason: aria-hidden="true" must not be present on the document body
   *                   helpUrl: https://dequeuniversity.com/rules/axe/4.11/aria-hidden-body?application=axeAPI
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
    const { html, successCriteriaId } = req.body;

    if (!html || typeof html !== 'string') {
      this._logger.warn('analyze rejected: html field missing or not a string');
      return res.status(400).json({ error: 'html field is required and must be a string' });
    }

    try {
      const filter = successCriteriaId ?? null;
      this._logger.info(`analyze start successCriteriaId=${filter ?? 'none'} htmlLength=${html.length}`);
      const results = await this._service.analyze(html, filter);
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
}

module.exports = AccessibilityController;
