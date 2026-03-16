'use strict';

const rulesGuide = require('../utils/rulesGuide');

const ALL_RULES = Object.entries(rulesGuide).map(([ruleId, data]) => ({ ruleId, ...data }));

/**
 * RulesGuideController — serves testing guidance for axe-core rules.
 */
class RulesGuideController {
  constructor(logger) {
    this._logger = logger;
  }

  /**
   * @openapi
   * /rules-guide:
   *   get:
   *     summary: Get testing guidance for all axe-core rules
   *     description: >
   *       Returns a list of all axe-core rules with human-readable guidance,
   *       manual testing steps, fail/pass HTML examples, and remediation tips.
   *       Optionally filter by WCAG level or success criteria ID.
   *     parameters:
   *       - in: query
   *         name: wcagLevel
   *         schema:
   *           type: string
   *           enum: [A, AA, AAA, best-practice]
   *         description: Filter rules by WCAG level (A, AA, AAA, best-practice)
   *         example: A
   *       - in: query
   *         name: successCriteriaId
   *         schema:
   *           type: string
   *         description: Filter rules by WCAG Success Criterion ID (e.g. "1.1.1")
   *         example: "1.1.1"
   *     responses:
   *       200:
   *         description: List of rules with guidance
   *         content:
   *           application/json:
   *             schema:
   *               type: object
   *               properties:
   *                 total:
   *                   type: integer
   *                   description: Number of rules returned
   *                 rules:
   *                   type: array
   *                   items:
   *                     $ref: '#/components/schemas/RuleGuide'
   */
  getAll(req, res) {
    const { wcagLevel, successCriteriaId } = req.query;

    let rules = ALL_RULES;

    if (wcagLevel) {
      rules = rules.filter(r => r.wcagLevel === wcagLevel);
    }
    if (successCriteriaId) {
      rules = rules.filter(r => r.successCriteriaId === successCriteriaId);
    }

    this._logger.info(`getAll rules wcagLevel=${wcagLevel ?? 'any'} successCriteriaId=${successCriteriaId ?? 'any'} → ${rules.length} rules`);
    res.json({ total: rules.length, rules });
  }

  /**
   * @openapi
   * /rules-guide/{ruleId}:
   *   get:
   *     summary: Get testing guidance for a specific axe-core rule
   *     description: Returns detailed guidance, examples, and fix tips for one rule.
   *     parameters:
   *       - in: path
   *         name: ruleId
   *         required: true
   *         schema:
   *           type: string
   *         description: axe-core rule ID (e.g. "image-alt", "color-contrast")
   *         example: image-alt
   *     responses:
   *       200:
   *         description: Rule guidance
   *         content:
   *           application/json:
   *             schema:
   *               $ref: '#/components/schemas/RuleGuide'
   *       404:
   *         description: Rule not found
   *         content:
   *           application/json:
   *             example:
   *               error: Rule not found
   *               message: No guidance entry found for rule "unknown-rule"
   */
  getOne(req, res) {
    const { ruleId } = req.params;
    const entry = rulesGuide[ruleId];

    if (!entry) {
      this._logger.warn(`getOne ruleId="${ruleId}" not found`);
      return res.status(404).json({
        error:   'Rule not found',
        message: `No guidance entry found for rule "${ruleId}"`,
      });
    }

    this._logger.info(`getOne ruleId="${ruleId}" found`);
    res.json({ ruleId, ...entry });
  }
}

/**
 * @openapi
 * components:
 *   schemas:
 *     RuleGuide:
 *       type: object
 *       properties:
 *         ruleId:
 *           type: string
 *           description: axe-core rule identifier
 *           example: image-alt
 *         successCriteriaId:
 *           type: string
 *           nullable: true
 *           description: WCAG Success Criterion ID (null for best-practice rules)
 *           example: "1.1.1"
 *         wcagLevel:
 *           type: string
 *           description: WCAG conformance level
 *           enum: [A, AA, AAA, best-practice]
 *           example: A
 *         title:
 *           type: string
 *           description: Short human-readable rule name
 *           example: Image Alternative Text
 *         guidance:
 *           type: string
 *           description: What the rule checks and why it matters
 *         howToTest:
 *           type: string
 *           description: Manual and automated testing steps
 *         failExample:
 *           type: string
 *           description: Minimal HTML that triggers the violation
 *           example: "<img src='logo.png'>"
 *         passExample:
 *           type: string
 *           description: Corrected HTML that passes the rule
 *           example: "<img src='logo.png' alt='Company logo'>"
 *         fixTip:
 *           type: string
 *           description: Concise remediation advice
 */

module.exports = RulesGuideController;
