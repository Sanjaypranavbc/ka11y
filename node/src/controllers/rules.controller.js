'use strict';

const config = require('../config/app.config');

/**
 * RulesController — SRP: handles HTTP requests for listing axe-core rules.
 */
class RulesController {
  /**
   * @param {object} rulesService - Instance of RulesService
   */
  constructor(rulesService, logger) {
    this._service = rulesService;
    this._logger  = logger;
  }

  /**
   * @openapi
   * /rules:
   *   get:
   *     description: Retrieves axe-core rules grouped by WCAG success criterion.
   *     parameters:
   *       - in: query
   *         name: tags
   *         schema:
   *           type: string
   *         description: Comma-separated tags (e.g. wcag2a,wcag21aa).
   *     responses:
   *       200:
   *         description: Success
   *         content:
   *           application/json:
   *             schema:
   *               type: object
   *       500:
   *         description: Internal server error
   */
  getRules(req, res) {
    const tags = req.query.tags
      ? req.query.tags.split(',')
      : config.axe.defaultTags;

    try {
      const data = this._service.getRules(tags);
      this._logger.info(`getRules tags=[${tags.join(',')}] returned ${Object.keys(data).length} criteria`);
      res.json(data);
    } catch (err) {
      this._logger.error(`getRules failed: ${err.message}`);
      res.status(500).json({
        error:   'Failed to retrieve rules',
        message: err.message,
      });
    }
  }
}

module.exports = RulesController;
