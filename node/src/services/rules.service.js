'use strict';

const { formatSuccessCriterion } = require('../utils/axeResultMapper');

/**
 * RulesService — SRP: retrieves and groups axe-core rules by WCAG success criterion.
 *
 * All external dependencies are injected via the constructor (DIP).
 */
class RulesService {
  /**
   * @param {object} axe                - axe-core library
   * @param {object} wcagCriteriaNames  - SC ID → human name lookup map
   * @param {object} logger             - Logger instance
   */
  constructor(axe, wcagCriteriaNames, logger) {
    this._axe                = axe;
    this._wcagCriteriaNames  = wcagCriteriaNames;
    this._logger             = logger;
  }

  /**
   * Returns axe-core rules grouped and sorted by WCAG success criterion.
   *
   * @param {Array<string>} tags - axe-core tags to filter by
   * @returns {object} Structured rules response
   */
  getRules(tags) {
    this._logger.info(`Fetching rules for tags: ${tags.join(', ')}`);

    const allRules = this._axe.getRules(tags);
    const grouped  = {};

    for (const rule of allRules) {
      const criterion = formatSuccessCriterion(rule.tags);
      if (!criterion) continue;

      const scId = criterion.replace('WCAG ', '');

      if (!grouped[scId]) {
        grouped[scId] = [];
      }

      grouped[scId].push({
        rule_id:     rule.ruleId,
        description: rule.description,
        help_url:    rule.helpUrl,
      });
    }

    const sortedCriteria = Object.keys(grouped)
      .sort((a, b) => {
        const pa = a.split('.').map(Number);
        const pb = b.split('.').map(Number);
        for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
          if ((pa[i] || 0) !== (pb[i] || 0)) return (pa[i] || 0) - (pb[i] || 0);
        }
        return 0;
      })
      .reduce((acc, key) => {
        acc[key] = {
          name:  this._wcagCriteriaNames[key] || 'Unknown',
          rules: grouped[key],
        };
        return acc;
      }, {});

    return {
      ruleslist:   Object.keys(sortedCriteria).length,
      standard:    'WCAG 2.1',
      total_rules: allRules.length,
      criteria:    sortedCriteria,
    };
  }
}

module.exports = RulesService;
