'use strict';

const { getCriteria, CANNOT_AUTOMATE_SC, MANUAL_ONLY_REASON } = require('../utils/wcag22Manifest');

/**
 * WcagService — orchestrates a full WCAG compliance analysis for a URL
 * and maps results back to the complete WCAG 2.1 / 2.2 criteria manifest.
 *
 * Relies on AccessibilityService for the actual Puppeteer + axe-core + custom
 * checks execution. This layer only shapes the response for the UI.
 */
class WcagService {
  /**
   * @param {object} accessibilityService  Instance of AccessibilityService
   * @param {object} logger
   */
  constructor(accessibilityService, logger) {
    this._svc    = accessibilityService;
    this._logger = logger;
  }

  /**
   * Run a full WCAG compliance analysis on a live URL.
   *
   * @param {string} url
   * @param {object} opts
   * @param {'2.1'|'2.2'} opts.wcagVersion
   * @param {string}       opts.lang
   * @returns {Promise<object>}
   */
  async analyseUrl(url, { wcagVersion = '2.2', lang = 'en' } = {}) {
    this._logger.info(`WcagService.analyseUrl start url=${url} wcag=${wcagVersion} lang=${lang}`);

    // Run full axe-core + all custom checks (no SC filter → get everything)
    const rawResults = await this._svc.analyseUrl(url, null, lang);

    // Index results by successCriteriaId for O(1) lookup
    const bySC         = {};
    const bestPractice = [];

    for (const group of (rawResults || [])) {
      const { successCriteriaId, rules } = group;
      if (!successCriteriaId || successCriteriaId === 'best-practice') {
        bestPractice.push(...(rules || []));
      } else {
        bySC[successCriteriaId] = rules || [];
      }
    }

    // Build criteria list from manifest — scaffold every SC then fill results
    const manifest = getCriteria(wcagVersion);
    const criteria = manifest.map(c => this._buildCriterion(c, bySC[c.sc]));
    const summary  = this._buildSummary(criteria, manifest.length);

    this._logger.info(
      `WcagService.analyseUrl done checked=${summary.checked} ` +
      `fail=${summary.failed} needs_review=${summary.needsReview} pass=${summary.passed}`
    );

    return {
      url,
      wcagVersion,
      analyzedAt: new Date().toISOString(),
      summary,
      criteria,
      bestPractice: bestPractice.map(r => ({
        ruleId:  r.ruleId,
        status:  r.status,
        impact:  r.impact || null,
        reason:  r.reason  || '',
        helpUrl: r.helpUrl || null,
      })),
    };
  }

  // ── private helpers ───────────────────────────────────────────────────────

  _buildCriterion(manifest, rules) {
    const base = {
      sc:        manifest.sc,
      name:      manifest.name,
      level:     manifest.level,
      principle: manifest.principle,
    };

    if (CANNOT_AUTOMATE_SC.has(manifest.sc)) {
      return {
        ...base,
        status:   'manual_only',
        reason:   MANUAL_ONLY_REASON[manifest.sc] || 'Requires human evaluation',
        sources:  [],
        findings: [],
      };
    }

    if (!rules || rules.length === 0) {
      return { ...base, status: 'not_checked', sources: [], findings: [] };
    }

    return {
      ...base,
      status:   this._deriveStatus(rules),
      sources:  this._deriveSources(rules),
      findings: rules.map(r => ({
        ruleId:  r.ruleId,
        status:  r.status,
        impact:  r.impact  || null,
        reason:  r.reason  || '',
        helpUrl: r.helpUrl || null,
      })),
    };
  }

  _deriveStatus(rules) {
    if (rules.some(r => r.status === 'fail'))                                    return 'fail';
    if (rules.some(r => r.status === 'incomplete'))                              return 'needs_review';
    if (rules.every(r => r.status === 'not_applicable'))                         return 'not_applicable';
    if (rules.every(r => r.status === 'pass' || r.status === 'not_applicable'))  return 'pass';
    if (rules.every(r => r.status === 'pass'))                                   return 'pass';
    return 'needs_review';
  }

  _deriveSources(rules) {
    const s = new Set();
    for (const r of rules) {
      s.add(r.ruleId && r.ruleId.startsWith('custom-') ? 'custom' : 'axe');
    }
    return [...s];
  }

  _buildSummary(criteria, total) {
    let checked = 0, passed = 0, failed = 0, needsReview = 0, notChecked = 0, manualOnly = 0, notApplicable = 0;
    for (const c of criteria) {
      switch (c.status) {
        case 'manual_only':    manualOnly++;    break;
        case 'not_checked':    notChecked++;    break;
        case 'not_applicable': notApplicable++; break;
        case 'pass':           checked++; passed++;      break;
        case 'fail':           checked++; failed++;      break;
        default:               checked++; needsReview++; break;
      }
    }
    return { total, checked, passed, failed, needsReview, notChecked, notApplicable, manualOnly };
  }
}

module.exports = WcagService;
