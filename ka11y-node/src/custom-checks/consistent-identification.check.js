'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '3.2.4';
const RULE_ID = 'custom-consistent-identification';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/consistent-identification';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Components with the same functionality must be identified consistently';

function _t(ctx, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, ctx, en);
}

function _pass(ctx, reason) {
  return {
    successCriteriaId: SC,
    rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'pass', reason, helpUrl: HELP_URL }],
  };
}

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  const data = await page.evaluate(() => {
    const issues = [];

    // ── Check 1: Same icon image used with different accessible names ──────────
    // Collect all <img> with the same src, group their alt texts — inconsistency = fail.
    const imgBySrc = {};
    for (const img of document.querySelectorAll('img[src][alt]')) {
      const src = img.getAttribute('src') || '';
      const alt = (img.getAttribute('alt') || '').trim().toLowerCase();
      const basename = src.split('/').pop().split('?')[0];
      if (!basename) continue;
      if (!imgBySrc[basename]) imgBySrc[basename] = new Set();
      if (alt) imgBySrc[basename].add(alt);
    }
    for (const [basename, alts] of Object.entries(imgBySrc)) {
      if (alts.size > 1) {
        issues.push({
          type: 'inconsistent-img-alt',
          target: `img[src*="${basename}"]`,
          detail: `Image "${basename}" used with ${alts.size} different alt texts: ${[...alts].slice(0, 3).map(a => `"${a}"`).join(', ')}`,
        });
      }
    }

    // ── Check 2: Same SVG icon class used with different aria-labels ─────────
    const svgByClass = {};
    for (const use of document.querySelectorAll('svg use[href],svg use[xlink\\:href]')) {
      const href = (use.getAttribute('href') || use.getAttribute('xlink:href') || '').split('#').pop();
      if (!href) continue;
      const label = (use.closest('[aria-label]') || use.closest('[title]') || use.closest('button') || use.closest('a'))?.getAttribute('aria-label') ||
        use.closest('button')?.textContent?.trim().toLowerCase() || '';
      if (!href || !label) continue;
      if (!svgByClass[href]) svgByClass[href] = new Set();
      svgByClass[href].add(label.toLowerCase());
    }
    for (const [icon, labels] of Object.entries(svgByClass)) {
      if (labels.size > 1) {
        issues.push({
          type: 'inconsistent-svg-label',
          target: `svg use[href="#${icon}"]`,
          detail: `Icon "#${icon}" used with ${labels.size} different labels: ${[...labels].slice(0, 3).map(l => `"${l}"`).join(', ')}`,
        });
      }
    }

    // ── Check 3: Search inputs should all use the same accessible name ─────────
    const searchInputs = Array.from(document.querySelectorAll('input[type="search"],[role="searchbox"],input[name*="search" i],input[placeholder*="search" i],input[placeholder*="検索" i]'));
    if (searchInputs.length > 1) {
      const labels = new Set(searchInputs.map(inp => {
        const id = inp.id;
        const labelEl = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : null;
        return ((labelEl && labelEl.textContent) || inp.getAttribute('aria-label') || inp.getAttribute('placeholder') || '').trim().toLowerCase();
      }).filter(Boolean));
      if (labels.size > 1) {
        issues.push({
          type: 'inconsistent-search-label',
          target: 'input[type="search"]',
          detail: `${searchInputs.length} search input(s) have different accessible names: ${[...labels].slice(0, 3).map(l => `"${l}"`).join(', ')}`,
        });
      }
    }

    return { issues };
  });

  if (!data.issues.length) {
    return _pass(ctx, _t(ctx,
      'No inconsistent component identification patterns detected on this page. Multi-page cross-check is manual.',
      'このページで一貫性のないコンポーネント識別パターンは検出されませんでした。複数ページの確認は手動で行ってください。'));
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'moderate',
      status: 'incomplete',
      reason: _t(ctx,
        '{n} component identification inconsistency(ies) detected. Full verification requires cross-page review.',
        '{n} 件のコンポーネント識別の不一貫性が検出されました。完全な確認には複数ページのレビューが必要です。',
        { n: data.issues.length }),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
