'use strict';

/**
 * HealthController — SRP: handles the /health HTTP endpoint only.
 */
class HealthController {
  constructor(logger) {
    this._logger = logger;
  }

  /**
   * @openapi
   * /api/v1/health:
   *   get:
   *     description: Health check endpoint to verify API uptime.
   *     responses:
   *       200:
   *         description: Success
   *         content:
   *           application/json:
   *             schema:
   *               type: object
   *               properties:
   *                 status:
   *                   type: string
   *                   example: ok
   *                 timestamp:
   *                   type: string
   *                   format: date-time
   */
  getHealth(req, res) {
    res.json({ status: 'ok', timestamp: new Date().toISOString() });
  }
}

module.exports = HealthController;
