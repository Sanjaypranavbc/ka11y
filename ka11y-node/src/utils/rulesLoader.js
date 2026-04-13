'use strict';

/**
 * rulesLoader.js
 * ==============
 * Loads WCAG rules from the shared i18n/rules.yml and optional locale
 * overlay files (i18n/locales/<lang>.yml).
 *
 * Non-translatable fields (level, severity) always come from rules.yml.
 * Translatable fields (name, description, suggested_fix) are overridden
 * by the locale file when present and non-empty.
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
const I18N_DIR = process.env.KA11Y_I18N_DIR || DEFAULT_I18N_DIR;

/** @type {Map<string, Record<string, object>>} */
const _cache = new Map();
/** @type {Map<string, object>} */
const _localeCache = new Map();

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
function getRules(lang = 'en') {
  const safeLang = String(lang || 'en').replace(/[^a-zA-Z-]/g, '').slice(0, 10) || 'en';
  if (_cache.has(safeLang)) return _cache.get(safeLang);

  const basePath = path.join(I18N_DIR, 'rules.yml');
  const base     = _loadYaml(basePath);
  const baseRules = base.rules || {};

  if (safeLang === 'en') {
    _cache.set('en', baseRules);
    return baseRules;
  }

  const localePath = path.join(I18N_DIR, 'locales', `${safeLang}.yml`);
  const locale     = _loadYaml(localePath);
  const localeRules = locale.rules || {};

  // Merge: non-translatable fields always from base; text fields from locale if non-empty.
  const merged = {};
  for (const [id, rule] of Object.entries(baseRules)) {
    const override = localeRules[id] || {};
    merged[id] = {
      level:         rule.level,
      severity:      rule.severity,
      name:          (override.name          && override.name.trim())          || rule.name,
      description:   (override.description   && override.description.trim())   || rule.description,
      suggested_fix: (override.suggested_fix && override.suggested_fix.trim()) || rule.suggested_fix,
    };
  }

  _cache.set(safeLang, merged);
  return merged;
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

module.exports = { getRules, getRulesArray, getAxeRuleLocales, getLocaleData };
