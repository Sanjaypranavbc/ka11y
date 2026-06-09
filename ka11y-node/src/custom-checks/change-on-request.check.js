'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '3.2.5';
const RULE_ID = 'custom-change-on-request';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/change-on-request';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Changes of context must be initiated only by user request, not automatically';

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

    // ── Check 1: <meta http-equiv="refresh"> auto-redirect ──────────────────
    const metaRefresh = document.querySelector('meta[http-equiv="refresh" i]');
    if (metaRefresh) {
      const content = metaRefresh.getAttribute('content') || '';
      const delay = parseInt(content, 10);
      // delay=0 is commonly used for immediate redirect; any positive value is a timed context change
      if (!isNaN(delay) && delay > 0) {
        issues.push({
          type: 'meta-refresh',
          target: 'meta[http-equiv="refresh"]',
          snippet: metaRefresh.outerHTML,
          detail: `<meta http-equiv="refresh"> will redirect/reload the page after ${delay} second(s) without user request`,
        });
      }
    }

    // ── Check 2: <select> that navigates on change ───────────────────────────
    for (const select of document.querySelectorAll('select[onchange]')) {
      const handler = (select.getAttribute('onchange') || '').toLowerCase();
      if (/location|window\.open|navigate|href/i.test(handler)) {
        issues.push({
          type: 'select-onchange-navigate',
          target: select.id ? `select#${CSS.escape(select.id)}` : 'select',
          snippet: select.outerHTML.slice(0, 150),
          detail: 'select onchange handler navigates/opens a new URL on selection — context change without submit button',
        });
      }
    }

    // ── Check 3: Inline scripts with timed/automatic location changes ─────────
    const TIMED_NAV_RE = /(?:setTimeout|setInterval)\s*\([^)]*(?:location|window\.location|href|navigate)[^)]*,\s*\d+/;
    const AUTO_FOCUS_RE = /window\s*\.\s*(?:location|open)\s*=|document\s*\.\s*location\s*(?:\.href)?\s*=/;
    for (const script of document.querySelectorAll('script:not([src])')) {
      const src = script.textContent || '';
      if (TIMED_NAV_RE.test(src)) {
        issues.push({
          type: 'timed-auto-navigation',
          target: 'inline script',
          snippet: src.slice(0, 200),
          detail: 'Script uses setTimeout/setInterval to navigate automatically — context change without user request',
        });
        break;
      }
    }

    // ── Check 4: Auto-playing carousels / sliders that advance page context ───
    // Look for auto-advancing slide structures (common pattern: .active/.current cycling)
    const AUTO_SLIDE_RE = /autoplay|auto[-_]?play|auto[-_]?slide|auto[-_]?advance/i;
    for (const el of document.querySelectorAll('[class],[data-ride],[data-autoplay],[data-auto-play]')) {
      const cls = (el.getAttribute('class') || '');
      const dataRide = el.getAttribute('data-ride') || '';
      const dataAuto = el.getAttribute('data-autoplay') || el.getAttribute('data-auto-play') || '';
      if (AUTO_SLIDE_RE.test(cls) || dataRide === 'carousel' || dataAuto === 'true' || dataAuto === '1') {
        // Only flag if it doesn't have a pause/stop control nearby
        const hasPauseCtrl = el.querySelector('[aria-label*="pause" i],[aria-label*="stop" i],[aria-label*="一時停止" i],[data-action="pause"]') !== null;
        if (!hasPauseCtrl) {
          issues.push({
            type: 'auto-advancing-carousel',
            target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
            snippet: el.outerHTML.slice(0, 150),
            detail: 'Auto-advancing carousel/slider with no pause control detected',
          });
        }
      }
    }

    // ── Check 5: onblur / onfocus that navigates ──────────────────────────────
    for (const el of document.querySelectorAll('[onblur],[onfocus]')) {
      for (const attr of ['onblur', 'onfocus']) {
        const handler = (el.getAttribute(attr) || '').toLowerCase();
        if (/location|window\.open|navigate|href/i.test(handler)) {
          issues.push({
            type: `${attr}-navigate`,
            target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
            snippet: el.outerHTML.slice(0, 150),
            detail: `${attr} handler navigates/opens a URL on focus change`,
          });
        }
      }
    }

    return { issues };
  });

  if (!data.issues.length) {
    return _pass(ctx, _t(ctx,
      'No automatic context-change patterns detected (no meta-refresh, auto-navigating selects, timed redirects, or unpaused carousels).',
      '自動コンテキスト変更パターンは検出されませんでした（meta-refresh、自動ナビゲーション select、時間指定リダイレクト、一時停止なしカルーセルなし）。'));
  }

  const byType = {};
  for (const iss of data.issues) byType[iss.type] = (byType[iss.type] || 0) + 1;
  const summary = Object.entries(byType).map(([k, v]) => `${k}(${v})`).join(', ');

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'serious',
      status: 'fail',
      reason: _t(ctx,
        '{n} automatic context change(s) detected ({summary}).',
        '{n} 件の自動コンテキスト変更が検出されました（{summary}）。',
        { n: data.issues.length, summary }),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
