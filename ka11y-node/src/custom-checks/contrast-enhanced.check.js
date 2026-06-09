'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '1.4.6';
const RULE_ID = 'custom-contrast-enhanced';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/contrast-enhanced';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Text must have a contrast ratio of at least 7:1 (normal text) or 4.5:1 (large text)';

const MAX_VIOLATIONS = 200;
const LARGE_TEXT_PX = 24;      // ~18pt
const LARGE_BOLD_PX = 18.67;   // ~14pt bold

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

  const data = await page.evaluate((opts) => {
    function getLuminance(colorStr) {
      if (!colorStr) return null;
      const m = String(colorStr).match(/\d+\.?\d*/g);
      if (!m || m.length < 3) return null;
      return [parseFloat(m[0]), parseFloat(m[1]), parseFloat(m[2])].reduce((sum, c, i) => {
        const s = c / 255;
        const lin = s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
        return sum + lin * [0.2126, 0.7152, 0.0722][i];
      }, 0);
    }

    function contrastRatio(l1, l2) {
      return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    }

    function effectiveBackground(el) {
      let node = el;
      while (node && node !== document.documentElement) {
        const cs = window.getComputedStyle(node);
        const bg = cs.backgroundColor;
        if (bg && bg !== 'transparent' && bg !== 'rgba(0, 0, 0, 0)') return bg;
        node = node.parentElement;
      }
      return 'rgb(255, 255, 255)';
    }

    const TEXT_SEL = 'p,h1,h2,h3,h4,h5,h6,li,td,th,span,label,a,button';
    const elements = Array.from(document.querySelectorAll(TEXT_SEL));
    const violations = [];
    const seen = new Set();

    for (const el of elements) {
      if (violations.length >= opts.maxViolations) break;

      const text = (el.textContent || '').trim();
      if (!text) continue;

      // Only check near-leaf nodes (avoid counting the same text multiple times through parents)
      const hasTextChildren = Array.from(el.childNodes).some(n => n.nodeType === Node.TEXT_NODE && (n.textContent || '').trim());
      if (!hasTextChildren && el.children.length > 2) continue;

      const key = el.tagName + ':' + text.slice(0, 40);
      if (seen.has(key)) continue;
      seen.add(key);

      const cs = window.getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') continue;
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) continue;

      const lumFg = getLuminance(cs.color);
      const lumBg = getLuminance(effectiveBackground(el));
      if (lumFg === null || lumBg === null) continue;

      const cr = contrastRatio(lumFg, lumBg);
      const fontSize = parseFloat(cs.fontSize) || 16;
      const fontWeight = cs.fontWeight;
      const isBold = parseInt(fontWeight, 10) >= 700 || fontWeight === 'bold';
      const isLarge = fontSize >= opts.largePx || (isBold && fontSize >= opts.largeBoldPx);
      const requiredRatio = isLarge ? 4.5 : 7.0;

      if (cr < requiredRatio) {
        violations.push({
          target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
          snippet: el.outerHTML.slice(0, 120),
          contrast: Math.round(cr * 100) / 100,
          required: requiredRatio,
          isLarge,
          fontSize: Math.round(fontSize),
        });
      }
    }

    return { violations };
  }, { maxViolations: MAX_VIOLATIONS, largePx: LARGE_TEXT_PX, largeBoldPx: LARGE_BOLD_PX });

  if (!data.violations.length) {
    return _pass(ctx, _t(ctx,
      'All sampled text elements meet the 7:1 (normal) / 4.5:1 (large text) enhanced contrast ratio required by SC 1.4.6.',
      'サンプリングしたすべてのテキスト要素が SC 1.4.6 の強化コントラスト比 7:1（通常テキスト）/ 4.5:1（大テキスト）を満たしています。'));
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'serious',
      status: 'fail',
      reason: _t(ctx,
        '{n} text element(s) fail the enhanced 7:1 / 4.5:1 contrast ratio: {sample}.',
        '{n} 件のテキスト要素が 7:1 / 4.5:1 の強化コントラスト比を満たしていません: {sample}。',
        {
          n: data.violations.length,
          sample: data.violations.slice(0, 3).map(v => `<${v.target}> ${v.contrast}:1 (req ${v.required}:1)`).join('; '),
        }),
      elements: data.violations,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
