'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '1.4.10';
const RULE_ID = 'custom-reflow';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/reflow';
const MODE = 'interactive';
const FALLBACK_DESCRIPTION = 'Content must be accessible without horizontal scrolling at 320×256 CSS pixels';

// WCAG 1.4.10 reference viewport: 320×256 CSS px (equivalent to 400% zoom on a 1280px screen)
const REFLOW_WIDTH = 320;
const REFLOW_HEIGHT = 256;

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

  const originalViewport = page.viewport ? page.viewport() : null;

  try {
    await page.setViewport({ width: REFLOW_WIDTH, height: REFLOW_HEIGHT, deviceScaleFactor: 1 });
    // Allow layout to settle
    await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));

    const data = await page.evaluate((vw, vh) => {
      const issues = [];
      const inScrollContainer = (el) => {
        let n = el.parentElement;
        while (n && n !== document.body) {
          const c = window.getComputedStyle(n);
          if (c.overflowX === 'auto' || c.overflowX === 'scroll') return true;
          n = n.parentElement;
        }
        return false;
      };
      const scrollWidth = document.documentElement.scrollWidth;

      // ── Primary signal: page-level horizontal scroll ──────────────────────
      if (scrollWidth > vw + 1) {
        issues.push({
          type: 'horizontal-scroll',
          target: 'document',
          detail: `Document scrollWidth is ${scrollWidth}px — wider than the ${vw}px reflow viewport`,
        });
      }

      // ── Per-element overflow check (C32 / C31 / C33 / C37 / C38 / G224) ───────
      // Every visible element is inspected (capped); only the outermost overflowing
      // element of a subtree is reported. Elements that are, or sit inside, a
      // horizontally scrollable container that itself fits the viewport are allowed
      // (two-dimensional content exception, G225).
      const flagged = new Set();
      const hasFlaggedAncestor = (el) => { let n = el.parentElement; while (n) { if (flagged.has(n)) return true; n = n.parentElement; } return false; };
      const sel = (el) => el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : '') + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
      let walked = 0;
      for (const el of document.querySelectorAll('body *')) {
        if (walked++ > 6000 || issues.length >= 20) break;
        if (hasFlaggedAncestor(el)) continue;
        const cs = window.getComputedStyle(el);
        if (cs.display === 'none' || cs.visibility === 'hidden' || cs.display === 'contents') continue;
        const r = el.getBoundingClientRect();
        if (r.width < 4 || r.height < 4) continue;
        if (r.right <= vw + 2) continue;
        if (r.left < -vw / 2) continue; // off-canvas helpers (skip links, drawers)
        if ((cs.position === 'fixed' || cs.position === 'absolute') && r.left >= vw) continue; // hidden off-screen panels
        const isScrollable = cs.overflowX === 'auto' || cs.overflowX === 'scroll';
        if (isScrollable && r.left >= -2 && r.width <= vw + 2) continue;
        if (inScrollContainer(el)) continue;
        // Element is clipped by an overflow:hidden ancestor — no scrollbar, but content is lost.
        let clipper = null; { let n = el.parentElement; while (n && n !== document.body) { const ncs = window.getComputedStyle(n); if (/(hidden|clip)/.test(ncs.overflowX)) { clipper = n; break; } n = n.parentElement; } }
        const tag = el.tagName.toLowerCase();
        let type = 'overflow-element', hint = '';
        if (tag === 'table' || el.closest('table')) { type = 'table-overflow'; hint = 'wrap the table in a container with overflow-x:auto or restructure it for narrow screens (C32/C31)'; }
        else if (tag === 'pre' || tag === 'code') { type = 'code-overflow'; hint = 'allow the block to scroll horizontally (overflow-x:auto) or wrap lines (C32)'; }
        else if (/^(img|svg|video|iframe|canvas|picture|object|embed)$/.test(tag)) { type = 'media-overflow'; hint = 'use max-width:100% / height:auto so media scales down (C37)'; }
        else if (/^(input|select|textarea|button|label|fieldset|form)$/.test(tag) || el.querySelector('input, select, textarea')) { type = 'form-overflow'; hint = 'let labels and controls wrap and use fluid widths (C38)'; }
        else if (/\S{28,}/.test((el.textContent || '').trim())) { type = 'long-string-overflow'; hint = 'break long URLs/strings with overflow-wrap:anywhere or word-break (C33)'; }
        else if (parseFloat(cs.textIndent) > 40) { type = 'text-indent-overflow'; hint = 'reduce text-indent at narrow widths (G224)'; }
        else if (/px$/.test(cs.width) && parseFloat(cs.width) > vw) { hint = 'replace the fixed pixel width with a fluid width (C32)'; }
        flagged.add(el);
        issues.push({
          type,
          target: sel(el),
          snippet: el.outerHTML.slice(0, 150),
          detail: `${clipper ? 'Clipped by ' + sel(clipper) + ': ' : ''}right edge at ${Math.round(r.right)}px exceeds the ${vw}px viewport${hint ? ' — ' + hint : ''}`,
        });
      }

      // ── C34: fixed / sticky bars consuming the 256 px-high viewport ──────────
      const all = document.querySelectorAll('body *');
      if (all.length <= 6000) {
        const bars = [];
        for (const el of all) {
          const cs = window.getComputedStyle(el);
          if (cs.position !== 'fixed' && cs.position !== 'sticky') continue;
          const r = el.getBoundingClientRect();
          if (r.width < vw * 0.6 || r.height < 24) continue;
          if (r.bottom <= 0 || r.top >= vh) continue;
          bars.push([Math.max(0, r.top), Math.min(vh, r.bottom), el]);
        }
        bars.sort((a, b) => a[0] - b[0]);
        let covered = 0, curS = null, curE = null;
        for (const [s, e] of bars) {
          if (curS === null) { curS = s; curE = e; continue; }
          if (s <= curE) curE = Math.max(curE, e); else { covered += curE - curS; curS = s; curE = e; }
        }
        if (curS !== null) covered += curE - curS;
        if (covered > vh * 0.5) {
          issues.push({
            type: 'sticky-consumes-viewport',
            target: bars.map(b => b[2].tagName.toLowerCase() + (b[2].id ? `#${CSS.escape(b[2].id)}` : '')).slice(0, 4).join(', '),
            snippet: bars[0][2].outerHTML.slice(0, 150),
            detail: `position:fixed/sticky bars cover ${Math.round(covered)}px of the ${vh}px viewport at 320×256 — un-fix them in a narrow-viewport media query (C34)`,
          });
        }
      }

      return { scrollWidth, issues };
    }, REFLOW_WIDTH, REFLOW_HEIGHT);

    // ── G146 / G204 / C24: intermediate widths (liquid layout) — advisory for 1.4.4/1.4.8 ──
    const widthFailures = [];
    for (const w of [768, 1024]) {
      try {
        await page.setViewport({ width: w, height: 800, deviceScaleFactor: 1 });
        await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
        const sw = await page.evaluate(() => document.documentElement.scrollWidth);
        if (typeof sw === 'number' && sw > w + 1) widthFailures.push({ width: w, scrollWidth: sw });
      } catch (_) { /* ignore */ }
    }
    const widthRule = widthFailures.length ? {
      ruleId: `${RULE_ID}-intermediate-widths`,
      description: FALLBACK_DESCRIPTION,
      impact: 'minor',
      status: 'incomplete',
      reason: _t(ctx,
        'The layout is not fully liquid: horizontal scrolling appears at {list} even though it may reflow at 320px. Use fluid widths and media queries so content fits at every width (G146/G204/C24).',
        'レイアウトが完全なリキッドではありません: 320px ではリフローしても、{list} で横スクロールが発生します。あらゆる幅で収まるよう、流動的な幅とメディアクエリを使ってください（G146/G204/C24）。',
        { list: widthFailures.map(f => `${f.width}px (scroll width ${f.scrollWidth}px)`).join(', ') }),
      elements: widthFailures.map(f => ({ target: 'document', detail: `scrollWidth ${f.scrollWidth}px at ${f.width}px viewport` })),
      helpUrl: HELP_URL,
    } : null;

    if (!data.issues.length) {
      const pass = _pass(ctx, _t(ctx,
        'Page reflows correctly at 320×256px — no horizontal scroll, clipped or overflowing elements detected{w}.',
        'ページは 320×256px で正しくリフローします。横スクロール、切れ、はみ出す要素は検出されませんでした{w}。',
        { w: widthFailures.length ? '' : _t(ctx, '; 768px and 1024px widths also fit', '。768px と 1024px の幅でも収まります') }));
      if (widthRule) pass.rules.push(widthRule);
      return pass;
    }

    const byType = {};
    for (const i of data.issues) byType[i.type] = (byType[i.type] || 0) + 1;
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: FALLBACK_DESCRIPTION,
        impact: 'serious',
        status: 'fail',
        reason: _t(ctx,
          '{n} reflow issue(s) detected at 320×256px viewport ({scrollWidth}px scroll width): {types}.',
          '320×256px ビューポートで {n} 件のリフロー問題が検出されました（スクロール幅: {scrollWidth}px）: {types}。',
          { n: data.issues.length, scrollWidth: data.scrollWidth, types: Object.entries(byType).map(([k, v]) => `${k}(${v})`).join(', ') }),
        elements: data.issues,
        helpUrl: HELP_URL,
      }].concat(widthRule ? [widthRule] : []),
    };
  } finally {
    if (originalViewport) {
      try { await page.setViewport(originalViewport); } catch (_) { /* restore best-effort */ }
    }
  }
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
