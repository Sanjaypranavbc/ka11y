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

    // G172 / G178 / G188 / G206: on-page controls that let the user change the presentation
    const CONTROL_RE = /justif|align|text\s*size|font\s*size|larger\s+text|smaller\s+text|line\s*(?:height|spacing)|paragraph\s+spacing|reader\s+(?:mode|view)|single\s+column|文字サイズ|文字を大きく|文字を小さく|行間|配置|リーダー/i;
    const controlLabel = (el) => [el.textContent || '', el.getAttribute('aria-label') || '', el.getAttribute('title') || ''].join(' ');
    const presentationControls = Array.from(document.querySelectorAll('button, [role="button"], a[href], input[type="checkbox"], input[type="range"], select'))
      .filter(el => CONTROL_RE.test(controlLabel(el)) || CONTROL_RE.test(el.id || '') || CONTROL_RE.test(typeof el.className === 'string' ? el.className : ''))
      .slice(0, 5)
      .map(el => el.outerHTML.slice(0, 100));

    const measureCanvas = document.createElement('canvas').getContext('2d');
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

      // Check 2b (C20): estimated characters per line — measure the block's own font
      if (text.length >= 200 && el.clientWidth > 0 && measureCanvas) {
        try {
          measureCanvas.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
          const sample = text.slice(0, 200);
          const avg = measureCanvas.measureText(sample).width / sample.length;
          const cjk = /[\u3040-\u30FF\u3400-\u9FFF\uAC00-\uD7AF]/.test(sample);
          const limit = cjk ? 40 : 80;
          const cpl = avg > 0 ? el.clientWidth / avg : 0;
          if (cpl > limit * 1.1) {
            issues.push({ type: 'long-lines', target, snippet: el.outerHTML.slice(0, 100), detail: `≈${Math.round(cpl)} characters per line exceeds ${limit} (C20)` });
          }
        } catch (_) { /* canvas unavailable */ }
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

    return { blockCount: textBlocks.length, issues, presentationControls };
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

  const controls = Array.isArray(data.presentationControls) ? data.presentationControls : [];
  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'moderate',
      status: 'incomplete',
      reason: controls.length
        ? _t(ctx,
          '{n} visual presentation issue(s) detected in text blocks ({summary}); {c} on-page presentation control(s) (text size / spacing / alignment) were found — verify they let users correct these (G172/G178/G188).',
          'テキストブロックで {n} 件の視覚的表示の問題が検出されました（{summary}）。ページ上に {c} 件の表示調整コントロール（文字サイズ／行間／配置）があります。ユーザーがこれらを修正できるか確認してください（G172/G178/G188）。',
          { n: data.issues.length, summary, c: controls.length })
        : _t(ctx,
          '{n} visual presentation issue(s) detected in text blocks ({summary}).',
          'テキストブロックで {n} 件の視覚的表示の問題が検出されました（{summary}）。',
          { n: data.issues.length, summary }),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
