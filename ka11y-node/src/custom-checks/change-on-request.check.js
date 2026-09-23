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

  // SVR1: redirects performed by the server (3xx) are recorded by the service on
  // page.__ka11yNav; they are the recommended alternative to client-side timed redirects.
  const nav = page && page.__ka11yNav && typeof page.__ka11yNav === 'object' ? page.__ka11yNav : null;
  const serverRedirects = nav && Array.isArray(nav.redirectChain) ? nav.redirectChain.length : 0;

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

    // ── Check 6: links/buttons that open a new window without telling the user ──
    // WCAG H83 / G201 / SCR24: opening a new window on user request is allowed only
    // when the link text (or its accessible name) indicates it.
    const NEW_WINDOW_RE = /new\s+(?:window|tab)|opens?\s+(?:in\s+)?(?:a\s+)?new|external\s+(?:site|link|window)|別(?:ウィンドウ|タブ|窓)|新しい(?:ウィンドウ|タブ)|新規(?:ウィンドウ|タブ)|外部サイト/i;
    const nameOf = (el) => {
      const bits = [
        el.textContent || '',
        el.getAttribute('aria-label') || '',
        el.getAttribute('title') || '',
      ];
      const labelledBy = (el.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean);
      for (const id of labelledBy) {
        const ref = document.getElementById(id);
        if (ref) bits.push(ref.textContent || '');
      }
      for (const img of el.querySelectorAll('img[alt], svg title, [aria-label]')) {
        bits.push(img.getAttribute ? (img.getAttribute('alt') || img.getAttribute('aria-label') || img.textContent || '') : '');
      }
      return bits.join(' ');
    };
    let newWindowCount = 0;
    const seenHref = new Set();
    for (const el of document.querySelectorAll('a[target="_blank"], area[target="_blank"], [onclick*="window.open"], form[target="_blank"]')) {
      const cs = window.getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') continue;
      const key = (el.getAttribute('href') || el.getAttribute('onclick') || el.getAttribute('action') || '') + '|' + (el.textContent || '').trim();
      if (seenHref.has(key)) continue;
      seenHref.add(key);
      newWindowCount++;
      if (NEW_WINDOW_RE.test(nameOf(el))) continue;
      issues.push({
        type: 'new-window-no-warning',
        target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : '') + (el.getAttribute('href') ? `[href="${(el.getAttribute('href') || '').slice(0, 80)}"]` : ''),
        snippet: el.outerHTML.slice(0, 150),
        detail: 'Opens a new window/tab (target="_blank" or window.open) without indicating this in the link text or accessible name (WCAG H83/G201)',
      });
      if (issues.filter(i => i.type === 'new-window-no-warning').length >= 20) break;
    }

    // ── Check 7: window.open() fired by script at load, without user activation ──
    const R = window.__ka11yRuntime;
    if (R && Array.isArray(R.windowOpen)) {
      for (const call of R.windowOpen.filter(c => !c.userActivated).slice(0, 5)) {
        issues.push({
          type: 'script-window-open-on-load',
          target: 'window.open()',
          snippet: `window.open(${JSON.stringify(call.url)}, ${JSON.stringify(call.target)}) at +${call.at}ms`,
          detail: 'Script opened a new window/tab without a user action — a change of context not initiated by the user',
        });
      }
    }

    return { issues, newWindowCount };
  });

  if (!data.issues.length) {
    return _pass(ctx, _t(ctx,
      'No automatic context-change patterns detected (no meta-refresh, auto-navigating selects, timed redirects, unpaused carousels, or unannounced new-window links{nw}).',
      '自動コンテキスト変更パターンは検出されませんでした（meta-refresh、自動ナビゲーション select、時間指定リダイレクト、一時停止なしカルーセル、告知のない別ウィンドウリンクなし{nw}）。',
      { nw: (data.newWindowCount ? `; ${data.newWindowCount} new-window link(s) all announce it` : '') + (serverRedirects ? `; ${serverRedirects} server-side redirect(s) before this page (SVR1 — allowed, no client-side timed redirect)` : '') }));
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
