'use strict';

const { getCriteria, CANNOT_AUTOMATE_SC, MANUAL_ONLY_REASON } = require('../utils/wcag22Manifest');
const { getSitemapUrls } = require('../utils/sitemap');
const { assertPublicUrl } = require('./accessibility.service');

const STATUS_RANK = { fail: 0, incomplete: 1, pass: 2, not_applicable: 3 };

// Max tabs open at once within the single shared browser used for a
// multi-page (maxDepth > 0) audit. Bounds memory regardless of maxDepth.
const BATCH_CONCURRENCY = parseInt(process.env.WCAG_BATCH_CONCURRENCY) || 5;

// SCs disabled for /analyse-url-wcag only — skipped entirely (axe rules
// disabled at the engine, matching custom checks not run) and excluded from
// the manifest so they don't appear in the response at all.
const DISABLED_SC = [
  '1.1.1',
  '1.4.3',
  '1.4.5',
  '1.4.6',
  '1.4.11',
  '4.1.2',
  '1.2.1',
  '1.2.2',
  '1.2.3',
  '1.2.4',
];

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
   * @param {number}       opts.maxDepth  Extra pages to scan from the site's
   *                                      sitemap.xml on top of `url`. 0 = only
   *                                      `url` itself (default).
   * @returns {Promise<object>}
   */
  async analyseUrl(url, { wcagVersion = '2.2', lang = 'en', maxDepth = 0 } = {}) {
    const depth = Number.isInteger(maxDepth) && maxDepth > 0 ? maxDepth : 0;
    this._logger.info(
      `WcagService.analyseUrl start url=${url} wcag=${wcagVersion} lang=${lang} maxDepth=${depth}`
    );

    const pageUrls = await this._resolvePageUrls(url, depth);

    // Audit every page under ONE shared browser with bounded tab concurrency
    // (see AccessibilityService.analyseUrlsBatch) — a page failing doesn't
    // abort the rest; it's reported in failedPages instead.
    const { results: perPageGroups, failedPages } = await this._svc.analyseUrlsBatch(pageUrls, {
      lang,
      excludeCriteria: DISABLED_SC,
      concurrency: BATCH_CONCURRENCY,
    });

    if (perPageGroups.length === 0) {
      throw new Error(`Analysis failed for all ${pageUrls.length} page(s)`);
    }

    // Index results by successCriteriaId, merging same-ruleId findings across pages.
    const bySC         = {};
    const bestPractice  = [];

    for (const { url: pageUrl, rawResults } of perPageGroups) {
      for (const group of rawResults) {
        const { successCriteriaId, rules } = group;
        const tagged = (rules || []).map(r => ({
          ...r,
          elements: (r.elements || []).map(el => ({ ...el, pageUrl })),
        }));
        if (!successCriteriaId || successCriteriaId === 'best-practice') {
          bestPractice.push(...tagged);
        } else {
          (bySC[successCriteriaId] ||= []).push(...tagged);
        }
      }
    }

    for (const sc of Object.keys(bySC)) {
      bySC[sc] = this._mergeRulesByRuleId(bySC[sc]);
    }

    // Build criteria list from manifest — scaffold every SC then fill results,
    // excluding the disabled SCs entirely (not even shown as "not_checked").
    const manifest = getCriteria(wcagVersion).filter(c => !DISABLED_SC.includes(c.sc));
    const criteria = manifest.map(c => this._buildCriterion(c, bySC[c.sc]));
    const summary  = this._buildSummary(criteria, manifest.length);

    this._logger.info(
      `WcagService.analyseUrl done pages=${perPageGroups.length}/${pageUrls.length} ` +
      `(${failedPages.length} failed) checked=${summary.checked} ` +
      `fail=${summary.failed} needs_review=${summary.needsReview} pass=${summary.passed}`
    );

    return {
      url,
      wcagVersion,
      analyzedAt: new Date().toISOString(),
      maxDepth: depth,
      scannedUrls: perPageGroups.map(g => g.url),
      failedPages,
      summary,
      criteria,
      bestPractice: this._mergeRulesByRuleId(bestPractice).map(r => ({
        ruleId:  r.ruleId,
        status:  r.status,
        impact:  r.impact || null,
        reason:  r.reason  || '',
        helpUrl: r.helpUrl || null,
      })),
    };
  }

  // ── private helpers ───────────────────────────────────────────────────────

  /**
   * Resolve the ordered list of page URLs to scan: `url` itself, plus (when
   * `depth` > 0) up to `depth` more pages pulled from the site's sitemap.xml.
   * Sitemap lookup failures fall back to just `[url]` so a single-page scan
   * never breaks because a site has no sitemap.
   *
   * @param {string} url
   * @param {number} depth
   * @returns {Promise<string[]>}
   */
  async _resolvePageUrls(url, depth) {
    if (depth <= 0) return [url];
    try {
      const sitemapUrls = await getSitemapUrls(url, { assertPublicUrl, logger: this._logger });
      const extra = sitemapUrls.filter(u => u !== url).slice(0, depth);
      return [url, ...extra];
    } catch (err) {
      this._logger.warn(`WcagService: sitemap lookup failed for ${url}: ${err.message}`);
      return [url];
    }
  }

  /**
   * Merge rule results that share a `ruleId` (e.g. found on multiple pages)
   * into one entry: worst status wins (fail > incomplete > pass >
   * not_applicable), elements from every page are concatenated (capped).
   *
   * @param {Array<object>} rules
   * @returns {Array<object>}
   */
  _mergeRulesByRuleId(rules) {
    const MAX_ELEMENTS = 20;
    const byId = new Map();

    for (const rule of rules) {
      const existing = byId.get(rule.ruleId);
      if (!existing) {
        byId.set(rule.ruleId, { ...rule, elements: [...(rule.elements || [])] });
        continue;
      }
      if ((STATUS_RANK[rule.status] ?? 4) < (STATUS_RANK[existing.status] ?? 4)) {
        existing.status  = rule.status;
        existing.reason  = rule.reason;
        existing.impact  = rule.impact;
      }
      existing.elements.push(...(rule.elements || []));
    }

    for (const merged of byId.values()) {
      if (merged.elements.length > MAX_ELEMENTS) merged.elements.length = MAX_ELEMENTS;
    }

    return [...byId.values()];
  }

  _normalizeElement(el) {
    if (!el || typeof el !== 'object') return null;
    // Custom checks may use `snippet` or `outerHTML` instead of `html`
    const html = el.html || el.snippet || el.outerHTML || null;
    // Custom checks may use a plain string `target` like "div#main"
    const rawTarget = el.target;
    const targetArr = Array.isArray(rawTarget) ? rawTarget
      : (typeof rawTarget === 'string' && rawTarget ? [rawTarget] : []);
    const selector = el.selector
      || (typeof rawTarget === 'string' ? rawTarget : null)
      || (targetArr[0] || null);
    return {
      html,
      selector,
      target:       targetArr,
      bounding_box: el.boundingBox || el.bounding_box || null,
      detail:       el.detail || null,
      page_url:     el.pageUrl || el.page_url || null,
    };
  }

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
        ruleId:   r.ruleId,
        status:   r.status,
        impact:   r.impact    || null,
        reason:   r.reason    || '',
        helpUrl:  r.helpUrl   || null,
        elements: (r.elements || []).map(el => this._normalizeElement(el)).filter(Boolean),
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
