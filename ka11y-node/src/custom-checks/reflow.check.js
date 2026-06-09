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

    const data = await page.evaluate((vw) => {
      const issues = [];
      const scrollWidth = document.documentElement.scrollWidth;

      // ── Primary signal: page-level horizontal scroll ──────────────────────
      if (scrollWidth > vw + 1) {
        issues.push({
          type: 'horizontal-scroll',
          target: 'document',
          detail: `Document scrollWidth is ${scrollWidth}px — wider than the ${vw}px reflow viewport`,
        });
      }

      // ── Per-element overflow check ────────────────────────────────────────
      // Walk major content elements only (avoid checking every DOM node)
      const candidates = document.querySelectorAll('main,article,section,aside,header,footer,nav,table,[role="main"],[role="article"],img,video,iframe,pre,code');
      for (const el of candidates) {
        const r = el.getBoundingClientRect();
        if (r.right <= vw + 1) continue;

        const cs = window.getComputedStyle(el);
        // Skip elements inside horizontally scrollable containers (intentional)
        const isScrollable = cs.overflowX === 'auto' || cs.overflowX === 'scroll';
        if (isScrollable) continue;

        issues.push({
          type: 'overflow-element',
          target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
          snippet: el.outerHTML.slice(0, 150),
          detail: `Element right edge at ${Math.round(r.right)}px exceeds ${vw}px viewport`,
        });
        if (issues.length >= 15) break;
      }

      return { scrollWidth, issues };
    }, REFLOW_WIDTH);

    if (!data.issues.length) {
      return _pass(ctx, _t(ctx,
        'Page reflows correctly at 320×256px — no horizontal scroll or overflow detected.',
        'ページは 320×256px で正しくリフローします。横スクロールやオーバーフローは検出されませんでした。'));
    }

    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: FALLBACK_DESCRIPTION,
        impact: 'serious',
        status: 'fail',
        reason: _t(ctx,
          '{n} reflow issue(s) detected at 320×256px viewport ({scrollWidth}px scroll width).',
          '320×256px ビューポートで {n} 件のリフロー問題が検出されました（スクロール幅: {scrollWidth}px）。',
          { n: data.issues.length, scrollWidth: data.scrollWidth }),
        elements: data.issues,
        helpUrl: HELP_URL,
      }],
    };
  } finally {
    if (originalViewport) {
      try { await page.setViewport(originalViewport); } catch (_) { /* restore best-effort */ }
    }
  }
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
