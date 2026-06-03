'use strict';

/**
 * rulesLoader.js
 * ==============
 * Loads WCAG rules from the shared i18n/rules.yml and optional locale
 * overlay files (i18n/locales/<lang>.yml).
 *
 * Stable machine fields (level, severity, status) always come from
 * rules.yml — clients filter on these and they must be identical across
 * languages.
 *
 * Translatable fields are overridden per locale:
 *   rules.<id>.name / description / suggested_fix
 *   rules.<id>.reason_templates.<code>
 *   severities.<key>   — display label for a severity machine value
 *   levels.<key>       — display label for a WCAG conformance level
 *   statuses.<key>     — display label for a finding status
 *
 * Results are cached per language after the first load.
 */

const fs   = require('fs');
const path = require('path');
const yaml = require('js-yaml');

const SHARED_I18N_DIR = path.resolve(__dirname, '../../../i18n');
const LOCAL_I18N_DIR = path.resolve(__dirname, '../../i18n');
const DEFAULT_I18N_DIR = fs.existsSync(path.join(SHARED_I18N_DIR, 'rules.yml'))
  ? SHARED_I18N_DIR
  : LOCAL_I18N_DIR;

// Allow Docker override via env var; default resolves to the repo-shared i18n directory.
const I18N_DIR = process.env.A11Y_I18N_DIR || DEFAULT_I18N_DIR;

const DEFAULT_SEVERITY_LABELS_EN = {
  critical: 'Critical',
  high:     'High',
  medium:   'Medium',
  low:      'Low',
  none:     'None',
};

const DEFAULT_LEVEL_LABELS_EN = {
  A:   'Level A',
  AA:  'Level AA',
  AAA: 'Level AAA',
};

const DEFAULT_STATUS_LABELS_EN = {
  pass:         'Pass',
  fail:         'Fail',
  needs_review: 'Needs Review',
  inapplicable: 'Not Applicable',
};

/** @type {Map<string, Record<string, object>>} */
const _cache = new Map();
/** @type {Map<string, object>} */
const _localeCache = new Map();
/** @type {Map<string, object>} */
const _bundleCache = new Map();

/**
 * Safely parse a YAML file. Returns {} on any error so callers never crash.
 * @param {string} filePath
 * @returns {object}
 */
function _loadYaml(filePath) {
  try {
    const raw = fs.readFileSync(filePath, 'utf8');
    return yaml.load(raw) || {};
  } catch (err) {
    // Locale file missing is expected; base missing is a config error.
    if (err.code !== 'ENOENT') {
      process.stderr.write(`[rulesLoader] YAML parse error in ${filePath}: ${err.message}\n`);
    }
    return {};
  }
}

/**
 * Return the merged rules map for a given language.
 *
 * Shape of each entry:
 *   { level, severity, name, description, suggested_fix }
 *
 * @param {string} [lang='en']
 * @returns {Record<string, { level: string, severity: string|null, name: string, description: string, suggested_fix: string }>}
 */
function _sanitizeLang(lang) {
  return String(lang || 'en').replace(/[^a-zA-Z-]/g, '').slice(0, 10) || 'en';
}

function _pick(override, fallback) {
  if (override == null) return fallback || '';
  const s = String(override).trim();
  return s ? s : (fallback || '');
}

function _mergeLabelMap(fallbackEn, base, override) {
  const out = {};
  const keys = new Set([
    ...Object.keys(fallbackEn || {}),
    ...Object.keys(base || {}),
    ...Object.keys(override || {}),
  ]);
  for (const key of keys) {
    out[key] = _pick(
      override && override[key],
      _pick(base && base[key], (fallbackEn || {})[key] || key),
    );
  }
  return out;
}

function _mergeReasonTemplates(baseTemplates, overrideTemplates) {
  const merged = {};
  const keys = new Set([
    ...Object.keys(baseTemplates || {}),
    ...Object.keys(overrideTemplates || {}),
  ]);
  for (const key of keys) {
    merged[key] = _pick((overrideTemplates || {})[key], (baseTemplates || {})[key]);
  }
  return merged;
}

function getRules(lang = 'en') {
  const safeLang = _sanitizeLang(lang);
  if (_cache.has(safeLang)) return _cache.get(safeLang);

  const basePath = path.join(I18N_DIR, 'rules.yml');
  const base     = _loadYaml(basePath);
  const baseRules = base.rules || {};
  const baseTemplatesTop = base.reason_templates || {};

  const localeData  = safeLang === 'en' ? {} : _loadYaml(path.join(I18N_DIR, 'locales', `${safeLang}.yml`));
  const localeRules = (localeData && localeData.rules) || {};
  const localeTemplatesTop = (localeData && localeData.reason_templates) || {};

  // Include synthetic SC ids (e.g. "_generic") that only exist in the
  // top-level reason_templates block so callers can render shared messages.
  const allIds = new Set([
    ...Object.keys(baseRules),
    ...Object.keys(baseTemplatesTop),
    ...Object.keys(localeTemplatesTop),
  ]);

  const merged = {};
  for (const id of allIds) {
    const rule = baseRules[id] || {};
    const override = localeRules[id] || {};
    // Merge reason templates from both nested form (rules.X.reason_templates)
    // and top-level form (reason_templates.X), with locale > base and top > nested.
    const nestedBase = rule.reason_templates || {};
    const nestedOverride = override.reason_templates || {};
    const topBase = baseTemplatesTop[id] || {};
    const topOverride = localeTemplatesTop[id] || {};
    const allKeys = new Set([
      ...Object.keys(nestedBase),
      ...Object.keys(nestedOverride),
      ...Object.keys(topBase),
      ...Object.keys(topOverride),
    ]);
    const reasonTemplates = {};
    for (const key of allKeys) {
      reasonTemplates[key] = _pick(
        topOverride[key],
        _pick(nestedOverride[key], _pick(topBase[key], nestedBase[key])),
      );
    }
    merged[id] = {
      level:            rule.level || null,
      severity:         rule.severity == null ? null : rule.severity,
      name:             _pick(override.name,          rule.name),
      description:      _pick(override.description,   rule.description),
      suggested_fix:    _pick(override.suggested_fix, rule.suggested_fix),
      reason_templates: reasonTemplates,
    };
  }

  _cache.set(safeLang, merged);
  return merged;
}

/**
 * Return a fully merged i18n bundle (rules + label maps) for a language.
 * @param {string} [lang='en']
 */
function getBundle(lang = 'en') {
  const safeLang = _sanitizeLang(lang);
  if (_bundleCache.has(safeLang)) return _bundleCache.get(safeLang);

  const basePath = path.join(I18N_DIR, 'rules.yml');
  const base     = _loadYaml(basePath);

  const localeData = safeLang === 'en' ? {} : _loadYaml(path.join(I18N_DIR, 'locales', `${safeLang}.yml`));

  const bundle = {
    lang: safeLang,
    rules: getRules(safeLang),
    severities: _mergeLabelMap(DEFAULT_SEVERITY_LABELS_EN, base.severities, localeData.severities),
    levels:     _mergeLabelMap(DEFAULT_LEVEL_LABELS_EN,    base.levels,     localeData.levels),
    statuses:   _mergeLabelMap(DEFAULT_STATUS_LABELS_EN,   base.statuses,   localeData.statuses),
  };
  _bundleCache.set(safeLang, bundle);
  return bundle;
}

function getSeverityLabels(lang = 'en') { return { ...getBundle(lang).severities }; }
function getLevelLabels(lang = 'en')    { return { ...getBundle(lang).levels }; }
function getStatusLabels(lang = 'en')   { return { ...getBundle(lang).statuses }; }

function getSeverityLabel(value, lang = 'en') {
  if (value == null) return null;
  const map = getBundle(lang).severities;
  return map[String(value)] || String(value);
}

function getLevelLabel(value, lang = 'en') {
  if (value == null) return null;
  const map = getBundle(lang).levels;
  return map[String(value)] || String(value);
}

function getStatusLabel(value, lang = 'en') {
  if (value == null) return null;
  const map = getBundle(lang).statuses;
  return map[String(value)] || String(value);
}

/**
 * Render a localized reason for a WCAG SC by template code.
 * Placeholders use {name} interpolation; missing placeholders render empty.
 *
 * Falls back to the English template if the locale has no override, then
 * to the supplied fallback string.
 */
function renderRuleReason(wcagSc, code, params = {}, lang = 'en', fallback = '') {
  const safeLang = _sanitizeLang(lang);
  const rule = getRules(safeLang)[String(wcagSc)];
  let template = rule && rule.reason_templates ? rule.reason_templates[String(code)] : '';

  if (!template && safeLang !== 'en') {
    const enRule = getRules('en')[String(wcagSc)];
    template = enRule && enRule.reason_templates ? enRule.reason_templates[String(code)] : '';
  }

  // Fall back to the shared `_generic` block so every SC participates in
  // localization even when it doesn't define its own templates.
  if (!template) {
    const generic = getRules(safeLang)['_generic'];
    template = generic && generic.reason_templates ? generic.reason_templates[String(code)] : '';
  }
  if (!template && safeLang !== 'en') {
    const enGeneric = getRules('en')['_generic'];
    template = enGeneric && enGeneric.reason_templates ? enGeneric.reason_templates[String(code)] : '';
  }

  if (!template) return fallback;

  // Ensure callers always have access to {wcag_sc} in _generic templates.
  const merged = Object.assign({ wcag_sc: String(wcagSc) }, params || {});

  return template.replace(/\{([a-zA-Z0-9_]+)\}/g, (_, key) => {
    const v = merged[key];
    return v == null ? '' : String(v);
  });
}

function getLocaleData(lang = 'en') {
  const safeLang = String(lang || 'en').replace(/[^a-zA-Z-]/g, '').slice(0, 10) || 'en';
  if (_localeCache.has(safeLang)) return _localeCache.get(safeLang);
  if (safeLang === 'en') {
    const empty = {};
    _localeCache.set(safeLang, empty);
    return empty;
  }

  const localePath = path.join(I18N_DIR, 'locales', `${safeLang}.yml`);
  const locale = _loadYaml(localePath);
  _localeCache.set(safeLang, locale);
  return locale;
}

function getAxeRuleLocales(lang = 'en') {
  const locale = getLocaleData(lang);
  return locale && typeof locale.axe_rules === 'object' ? locale.axe_rules : {};
}

/**
 * Returns all rules as a sorted array for API responses.
 *
 * @param {string} [lang='en']
 * @returns {Array<{ id: string, level: string, severity: string|null, name: string, description: string, suggested_fix: string }>}
 */
function getRulesArray(lang = 'en') {
  const rules = getRules(lang);
  return Object.entries(rules)
    .map(([id, rule]) => ({ id, ...rule }))
    .sort((a, b) => {
      const pa = a.id.split('.').map(Number);
      const pb = b.id.split('.').map(Number);
      for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
        const diff = (pa[i] || 0) - (pb[i] || 0);
        if (diff !== 0) return diff;
      }
      return 0;
    });
}

module.exports = {
  getRules,
  getRulesArray,
  getAxeRuleLocales,
  getLocaleData,
  getBundle,
  getSeverityLabels,
  getLevelLabels,
  getStatusLabels,
  getSeverityLabel,
  getLevelLabel,
  getStatusLabel,
  renderRuleReason,
};
