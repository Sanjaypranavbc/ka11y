'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '1.4.8';
const RULE_ID = 'custom-visual-presentation';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/visual-presentation';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Blocks of text must allow user control of foreground/background color, width, alignment, line spacing, and text size';

function _t(ctx, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, ctx, en);
}

function _pass(ctx, reason) {
  return {
    successCriteriaId: SC,
    rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'pass', reason, helpUrl: HELP_URL }],
  };
}
function _na(ctx, reason) {
  return {
    successCriteriaId: SC,
    rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'not_applicable', reason, helpUrl: HELP_URL }],
  };
}

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  const data = await page.evaluate(() => {
    const issues = [];

    // Collect paragraph-level text containers
    const textBlocks = Array.from(document.querySelectorAll('p,article,main,.content,.article-body,.post-body,[role="article"],[role="main"]'));
    if (!textBlocks.length) return { blockCount: 0, issues: [] };

    const checked = new Set();
    for (const el of textBlocks) {
      if (checked.has(el)) continue;
      checked.add(el);

      const text = (el.textContent || '').trim();
      if (text.length < 80) continue; // Skip short blocks

      const cs = window.getComputedStyle(el);
      const target = el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : '');

      // Check 1: text-align: justify (forbidden by 1.4.8)
      if (cs.textAlign === 'justify') {
        issues.push({ type: 'justified-text', target, snippet: el.outerHTML.slice(0, 100), detail: 'text-align: justify' });
      }

      // Check 2: line-height < 1.5 (must be at least 1.5 within paragraphs)
      const lineHeight = cs.lineHeight;
      const fontSize = parseFloat(cs.fontSize) || 16;
      let lhRatio = null;
      if (lineHeight !== 'normal') {
        const lhPx = parseFloat(lineHeight);
        if (!isNaN(lhPx) && fontSize > 0) lhRatio = lhPx / fontSize;
      }
      if (lhRatio !== null && lhRatio < 1.5) {
        issues.push({ type: 'tight-line-height', target, snippet: el.outerHTML.slice(0, 100), detail: `line-height: ${lineHeight} (ratio ${lhRatio.toFixed(2)})` });
      }

      // Check 3: excessively wide columns (> 80 characters) — approximate via element width / char width
      // CSS column-count or column-width restrictions can be inspected
      const columnWidth = cs.columnWidth;
      if (columnWidth && columnWidth !== 'auto') {
        const cw = parseFloat(columnWidth);
        // If explicitly wider than ~80ch (≈1280px at 16px), flag it
        if (!isNaN(cw) && cw > 1280) {
          issues.push({ type: 'wide-columns', target, snippet: el.outerHTML.slice(0, 100), detail: `column-width: ${columnWidth}` });
        }
      }
    }

    return { blockCount: textBlocks.length, issues };
  });

  if (!data.blockCount) {
    return _na(ctx, _t(ctx, 'No substantial text blocks found — criterion not applicable.', '十分なテキストブロックが見つかりませんでした。'));
  }
  if (!data.issues.length) {
    return _pass(ctx, _t(ctx,
      '{n} text block(s) checked — no text-align: justify, tight line-height, or excessive column width detected.',
      '{n} 件のテキストブロックを確認しました。text-align: justify、行間の詰め、過広なカラム幅は検出されませんでした。',
      { n: data.blockCount }));
  }

  const byType = {};
  for (const iss of data.issues) byType[iss.type] = (byType[iss.type] || 0) + 1;
  const summary = Object.entries(byType).map(([k, v]) => `${k}(${v})`).join(', ');

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'moderate',
      status: 'incomplete',
      reason: _t(ctx,
        '{n} visual presentation issue(s) detected in text blocks ({summary}).',
        'テキストブロックで {n} 件の視覚的表示の問題が検出されました（{summary}）。',
        { n: data.issues.length, summary }),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
