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

    // C23 / G175: can the user change foreground/background colours? Author colours
    // declared with !important defeat user style sheets; an on-page colour picker is a
    // conforming alternative.
    let importantColors = 0;
    try {
      const walk = (rules, depth) => { if (!rules || depth > 3) return; for (const r of rules) { try { if (r.style) { for (const prop of ['color', 'background-color', 'background']) { if (r.style.getPropertyPriority(prop) === 'important' && r.style.getPropertyValue(prop)) importantColors++; } } if (r.cssRules) walk(r.cssRules, depth + 1); } catch (_) { /* ignore */ } } };
      for (const s of document.styleSheets) { try { walk(s.cssRules, 0); } catch (_) { /* cross-origin */ } }
    } catch (_) { /* ignore */ }
    const colorPickers = Array.from(document.querySelectorAll('input[type="color"]')).filter(p => /background|foreground|text|colou?r|背景|文字|色/i.test(((p.labels && p.labels[0]) ? p.labels[0].textContent : '') + ' ' + (p.getAttribute('aria-label') || '') + ' ' + (p.name || '') + ' ' + (p.id || ''))).length;

    return { blockCount: textBlocks.length, issues, presentationControls, importantColors, colorPickers };
  });

  if (!data.blockCount) {
    return _na(ctx, _t(ctx, 'No substantial text blocks found — criterion not applicable.', '十分なテキストブロックが見つかりませんでした。'));
  }
  const colorOverrideRule = (data.importantColors >= 3 && !data.colorPickers) ? {
    ruleId: `${RULE_ID}-color-override`,
    description: FALLBACK_DESCRIPTION,
    impact: 'minor',
    status: 'incomplete',
    reason: _t(ctx,
      '{n} colour/background declarations use !important, which prevents users from overriding text and background colours with their own style sheet; no on-page colour selection tool was found (C23/G175).',
      '{n} 件の color/background 宣言が !important を使用しており、ユーザーが独自のスタイルシートで文字色や背景色を変更できません。ページ内に色選択ツールもありません（C23/G175）。',
      { n: data.importantColors }),
    helpUrl: HELP_URL,
  } : null;

  if (!data.issues.length) {
    const pass = _pass(ctx, _t(ctx,
      '{n} text block(s) checked — no text-align: justify, tight line-height, or excessive column width detected{pk}.',
      '{n} 件のテキストブロックを確認しました。text-align: justify、行間の詰め、過広なカラム幅は検出されませんでした{pk}。',
      { n: data.blockCount, pk: data.colorPickers ? _t(ctx, `; ${data.colorPickers} colour selection control(s) available (G175)`, `。色選択コントロール ${data.colorPickers} 件あり（G175）`) : '' }));
    if (colorOverrideRule) pass.rules.push(colorOverrideRule);
    return pass;
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
    }].concat(colorOverrideRule ? [colorOverrideRule] : []),
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
