'use strict';

const { getSharedConfigValue, loadSharedConfig } = require('../utils/sharedConfigLoader');

function sanitizeLang(lang = 'en') {
  const safe = String(lang || 'en').replace(/[^a-zA-Z-]/g, '').slice(0, 10);
  return safe || 'en';
}

function getSharedRuleContext(context = {}) {
  const config = context && context.config ? context.config : loadSharedConfig();
  return {
    ...context,
    config,
    lang: sanitizeLang(context && context.lang ? context.lang : 'en'),
  };
}

function getCheckConfig(checkKey, context = {}) {
  const sharedContext = getSharedRuleContext(context);
  return getSharedConfigValue(['checks', checkKey], {}, sharedContext.config) || {};
}

/**
 * Normalize half-width katakana (ｶﾀｶﾅ) to full-width (カタカナ) via NFKC
 * so that Japanese keyword lists match mixed-encoding input.
 */
function normalizeText(text) {
  return typeof text === 'string' ? text.normalize('NFKC') : text;
}

function _normalizeStringList(values) {
  if (!Array.isArray(values)) return [];
  return values
    .map((value) => normalizeText(String(value || '').trim()))
    .filter(Boolean);
}

function getKeywordList(checkKey, assetKey, context = {}) {
  const config = getCheckConfig(checkKey, context);
  const raw = config && config[assetKey];

  if (Array.isArray(raw)) return _normalizeStringList(raw);
  if (!raw || typeof raw !== 'object') return [];

  const merged = [];
  for (const value of Object.values(raw)) {
    merged.push(..._normalizeStringList(value));
  }
  return Array.from(new Set(merged));
}

function getNumberConfig(checkKey, key, fallback, context = {}) {
  const config = getCheckConfig(checkKey, context);
  const raw = config && config[key];
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function escapeForRegex(value) {
  return String(value || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function buildKeywordPattern(keywords) {
  const unique = Array.from(new Set(_normalizeStringList(keywords)));
  if (unique.length === 0) return null;
  return unique
    .sort((a, b) => b.length - a.length)
    .map(escapeForRegex)
    .join('|');
}

function _pickLocalizedValue(raw, lang = 'en') {
  if (typeof raw === 'string') return raw;
  if (!raw || typeof raw !== 'object') return null;

  const exact = raw[lang];
  if (typeof exact === 'string' && exact.trim()) return exact.trim();

  const baseLang = lang.split('-')[0];
  const base = raw[baseLang];
  if (typeof base === 'string' && base.trim()) return base.trim();

  const fallback = raw.en;
  if (typeof fallback === 'string' && fallback.trim()) return fallback.trim();

  for (const value of Object.values(raw)) {
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return null;
}

function renderLocalizedText(raw, params = {}, context = {}, fallback = '') {
  const sharedContext = getSharedRuleContext(context);
  const template = _pickLocalizedValue(raw, sharedContext.lang);

  if (!template) return fallback;

  return template.replace(/\{([a-zA-Z0-9_]+)\}/g, (_, token) => {
    const value = params[token];
    return value == null ? '' : String(value);
  });
}

function renderReasonTemplate(checkKey, reasonCode, params = {}, context = {}, fallback = '') {
  const sharedContext = getSharedRuleContext(context);
  const templates = getCheckConfig(checkKey, sharedContext).reason_templates || {};
  const rawTemplate = templates[reasonCode];
  return renderLocalizedText(rawTemplate, params, sharedContext, fallback);
}

module.exports = {
  buildKeywordPattern,
  getCheckConfig,
  getKeywordList,
  getNumberConfig,
  getSharedRuleContext,
  normalizeText,
  renderLocalizedText,
  renderReasonTemplate,
  sanitizeLang,
};
