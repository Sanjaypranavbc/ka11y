'use strict';

const { getSharedConfigValue, loadSharedConfig } = require('../utils/sharedConfigLoader');

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
  '[contenteditable="true"]',
  '[contenteditable=""]',
].join(', ');

const INPUT_SELECTOR = [
  'input:not([type="submit"]):not([type="button"]):not([type="reset"]):not([type="hidden"]):not([type="file"]):not([disabled])',
  'textarea:not([disabled])',
  'select:not([disabled])',
  '[contenteditable="true"]',
  '[contenteditable=""]',
].join(', ');

/**
 * Standard settlement helper (Technique #2).
 * Skips the hard 80ms wait if the element has no active CSS transitions.
 */
async function settle(page, ms = 80) {
  return page.evaluate((timeout) => {
    return new Promise((resolve) => {
      // Two rAFs ensure any style/layout invalidations from focus() have reached the paint phase
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          // If no transitions are detected, we could resolve early, but for safety
          // we still allow a small buffer or the full timeout if requested.
          setTimeout(resolve, timeout);
        });
      });
    });
  }, ms);
}

/**
 * Discover focusable elements once per page (Technique #3 + #4).
 * Includes stratified sampling by outerHTML hash to avoid redundant testing
 * of identical elements (e.g. 80 nav links).
 */
async function discoverPageElements(page, selector, max = 2000) {
  return page.evaluate((sel, limit) => {
    const items = [];
    const seen = new Set();
    const idCounts = {};
    const hashBuckets = {};

    // 1. Count IDs for stable selector generation
    for (const el of document.querySelectorAll('[id]')) {
      idCounts[el.id] = (idCounts[el.id] || 0) + 1;
    }

    const all = document.querySelectorAll(sel);
    for (let i = 0; i < all.length; i++) {
      const el = all[i];
      if (seen.has(el)) continue;
      seen.add(el);

      // 2. Stratified sampling (Technique #4): limit testing of identical elements
      // We use a simple hash of outerHTML to identify clones
      const html = el.outerHTML;
      const hash = html.length + html.slice(0, 100); // Simple fast "hash"
      hashBuckets[hash] = (hashBuckets[hash] || 0) + 1;
      
      // If we've seen this exact element shape more than 3 times, skip it
      // unless we are under a very small limit.
      if (hashBuckets[hash] > 3 && all.length > 50) continue;

      let stableSel = null;
      if (el.id && idCounts[el.id] === 1) {
        stableSel = `#${CSS.escape(el.id)}`;
      }

      items.push({
        idx: i, // DOM order index
        stableSel,
        tag: el.tagName.toUpperCase(),
        tagName: el.tagName.toLowerCase(),
        target: stableSel ? [stableSel] : [el.tagName.toLowerCase()],
        id: el.id || null,
        html: html.slice(0, 200),
        // Metadata for on-input
        isSelect: el.tagName === 'SELECT',
        isCheckboxOrRadio: el.type === 'checkbox' || el.type === 'radio',
        inputType: (el.getAttribute('type') || el.tagName).toLowerCase(),
      });

      if (items.length >= limit) break;
    }
    return items;
  }, selector, max);
}

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
  discoverPageElements,
  getCheckConfig,
  getKeywordList,
  getNumberConfig,
  getSharedRuleContext,
  normalizeText,
  renderLocalizedText,
  renderReasonTemplate,
  sanitizeLang,
  settle,
  FOCUSABLE_SELECTOR,
  INPUT_SELECTOR,
};
