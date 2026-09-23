'use strict';

const { auditPointerGestures } = require('../audits/wcag-2.5.1/index.js');
const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '2.5.1';
const RULE_ID = 'custom-pointer-gestures';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/pointer-gestures';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Complex gestures must have a single-pointer alternative';

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);
  const result = await auditPointerGestures(page, { pageUrl: page.url() });

  // G215: for each detected gesture region look for single-pointer alternatives
  // (next/previous, zoom in/out, +/−, rotate, arrow buttons) in or next to it.
  let alternatives = {};
  try {
    const selectors = [...result.violations, ...result.warnings].map(v => v.selector).filter(Boolean).slice(0, 20);
    if (selectors.length) {
      alternatives = await page.evaluate((sels) => {
        const ALT_RE = /next|prev|previous|forward|back|zoom\s*(in|out)?|\+|−|plus|minus|rotate|left|right|up|down|arrow|slide|page|scroll|次|前|拡大|縮小|回転|左|右|上|下/i;
        const nameOf = (el) => [(el.textContent || ''), el.getAttribute('aria-label') || '', el.getAttribute('title') || '', el.className || ''].join(' ');
        const out = {};
        for (const sel of sels) {
          let el = null;
          try { el = document.querySelector(sel); } catch (_) { el = null; }
          if (!el) { out[sel] = null; continue; }
          const scope = [el, el.parentElement, el.parentElement && el.parentElement.parentElement, el.closest('section, figure, article, [class*="carousel" i], [class*="slider" i], [class*="map" i], [class*="gallery" i]')].filter(Boolean);
          let found = 0;
          for (const root of scope) {
            found += Array.from(root.querySelectorAll('button, a[href], [role="button"], input[type="range"]')).filter(c => ALT_RE.test(nameOf(c))).length;
            if (found >= 2) break;
          }
          out[sel] = found;
        }
        return out;
      }, selectors);
    }
  } catch (_) { alternatives = {}; }
  if (alternatives && typeof alternatives === 'object' && !Array.isArray(alternatives)) {
    const withAlt = (v) => v.selector && alternatives[v.selector] >= 2;
    const keepV = result.violations.filter(v => !withAlt(v));
    const movedToWarn = result.violations.filter(withAlt).map(v => ({ ...v, severity: 'warning', message: `${v.message} — single-pointer controls found nearby (G215); verify they cover the whole gesture` }));
    result.violations = keepV;
    result.warnings = [...result.warnings.map(w => withAlt(w) ? { ...w, message: `${w.message} — single-pointer controls found nearby (G215)` } : w), ...movedToWarn];
  }

  const rules = [];

  if (result.summary.total === 0) {
    rules.push({
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: null,
      status: 'pass',
      reason: _t(sharedContext, 'No complex pointer gestures detected on this page.', 'このページでは複雑なポインタージェスチャーは検出されませんでした。'),
      helpUrl: HELP_URL,
    });
  } else {
    // Combine violations and warnings into a single SC report
    const elements = [...result.violations, ...result.warnings].map(v => ({
        html: v.outerHTML || null,
        target: v.selector ? [v.selector] : [],
        tag: v.tag || null,
        reason: v.message,
        severity: v.severity === 'violation' ? 'serious' : 'moderate'
    }));

    const status = result.violations.length > 0 ? 'fail' : 'incomplete';
    const impact = result.violations.length > 0 ? 'serious' : 'moderate';

    rules.push({
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact,
      status,
      reason: _t(sharedContext, '{count} complex gesture(s) detected. Ensure single-pointer alternatives are provided.', '{count} 件の複雑なジェスチャーが検出されました。単一ポインターによる代替手段が提供されていることを確認してください。', { count: result.summary.total }),
      elements,
      helpUrl: HELP_URL,
    });
  }

  return {
    successCriteriaId: SC,
    rules
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
