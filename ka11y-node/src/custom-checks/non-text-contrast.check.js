'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '1.4.11';
const RULE_ID = 'custom-non-text-contrast';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'UI components and graphical objects must have a contrast ratio of at least 3:1 against adjacent colours';

const MIN_CONTRAST = 3.0;
const MAX_VIOLATIONS = 30;

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

    function isTransparent(c) {
      return !c || c === 'transparent' || c === 'rgba(0, 0, 0, 0)';
    }

    function effectiveBackground(el) {
      let node = el.parentElement;
      while (node && node !== document.documentElement) {
        const bg = window.getComputedStyle(node).backgroundColor;
        if (!isTransparent(bg)) return bg;
        node = node.parentElement;
      }
      return 'rgb(255, 255, 255)';
    }

    const UI_SEL = 'input:not([type="hidden"]), textarea, select, button, [role="checkbox"], [role="radio"], [role="switch"], [role="slider"], [role="spinbutton"], [role="combobox"]';
    const violations = [];
    const checked = [];

    for (const el of document.querySelectorAll(UI_SEL)) {
      const cs = window.getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') continue;
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) continue;

      // Determine the indicator colour — border is the primary visual boundary
      const borderColor = cs.borderColor || cs.borderTopColor;
      const bgColor     = cs.backgroundColor;
      const adjacentBg  = effectiveBackground(el);

      let indicatorColor = null;
      let indicatorLabel = '';

      if (!isTransparent(borderColor)) {
        indicatorColor = borderColor;
        indicatorLabel = 'border';
      } else if (!isTransparent(bgColor)) {
        indicatorColor = bgColor;
        indicatorLabel = 'background';
      }

      if (!indicatorColor) continue;

      const lumIndicator = getLuminance(indicatorColor);
      const lumBg        = getLuminance(adjacentBg);
      if (lumIndicator === null || lumBg === null) continue;

      const cr = contrastRatio(lumIndicator, lumBg);
      checked.push(el.tagName);

      if (cr < opts.minContrast) {
        violations.push({
          target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : '') + (el.type ? `[type="${el.type}"]` : ''),
          snippet: el.outerHTML.slice(0, 120),
          contrast: Math.round(cr * 100) / 100,
          indicatorLabel,
          indicatorColor,
          adjacentBg,
        });
        if (violations.length >= opts.max) break;
      }
    }

    // G207: graphical objects — inline SVG icons and icon-font glyphs must reach 3:1
    // against their background (the fill/stroke or ::before colour is the object).
    const iconViolations = [];
    let iconsChecked = 0;
    try {
      const ICON_CLASS = /(^|\s)(fa|fas|far|fab|fal|material-icons|material-symbols[\w-]*|glyphicon|icon-[\w-]+|bi-[\w-]+|mdi-[\w-]+|ion-[\w-]+)(\s|$)/;
      const iconEls = [...Array.from(document.querySelectorAll('svg')), ...Array.from(document.querySelectorAll('i, span')).filter(e => ICON_CLASS.test(e.getAttribute('class') || ''))].slice(0, 300);
      for (const el of iconEls) {
        const cs = window.getComputedStyle(el);
        if (cs.display === 'none' || cs.visibility === 'hidden') continue;
        const decorative = el.closest('[aria-hidden="true"]') && !el.closest('a, button, [role="button"], [role="link"]');
        if (decorative) continue; // purely decorative icons are exempt
        const rect = el.getBoundingClientRect();
        if (rect.width < 8 || rect.height < 8 || rect.width > 96) continue;
        let color = null;
        if (el.tagName.toLowerCase() === 'svg') {
          const shape = el.querySelector('path, circle, rect, polygon, line, polyline, ellipse, use');
          const scs = shape ? window.getComputedStyle(shape) : cs;
          const fill = scs.fill, stroke = scs.stroke;
          color = (fill && fill !== 'none' && !isTransparent(fill)) ? fill : ((stroke && stroke !== 'none' && !isTransparent(stroke)) ? stroke : null);
          if (!color || /url\(/.test(color)) continue;
        } else {
          const pcs = window.getComputedStyle(el, '::before');
          color = (pcs && pcs.content && pcs.content !== 'none' && pcs.content !== 'normal') ? pcs.color : cs.color;
        }
        const bg = isTransparent(cs.backgroundColor) ? effectiveBackground(el) : cs.backgroundColor;
        const li = getLuminance(color), lb = getLuminance(bg);
        if (li === null || lb === null) continue;
        iconsChecked++;
        const cr = contrastRatio(li, lb);
        if (cr < opts.minContrast) {
          iconViolations.push({
            target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : '') + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/)[0] : ''),
            snippet: el.outerHTML.slice(0, 120),
            contrast: Math.round(cr * 100) / 100,
            indicatorLabel: 'icon',
            indicatorColor: color,
            adjacentBg: bg,
            detail: `Icon colour ${color} against ${bg} is ${Math.round(cr * 100) / 100}:1 — graphical objects need 3:1 (G207)`,
          });
          if (iconViolations.length >= 15) break;
        }
      }
    } catch (_) { /* ignore */ }

    return { violations: [...violations, ...iconViolations], checkedCount: checked.length + iconsChecked, iconsChecked };
  }, { minContrast: MIN_CONTRAST, max: MAX_VIOLATIONS });

  if (data.checkedCount === 0) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'not_applicable', reason: 'No UI form components found on this page.', helpUrl: HELP_URL }],
    };
  }

  if (!data.violations.length) {
    return _pass(ctx, _t(ctx,
      '{n} UI component(s) and icon(s) checked ({i} icons — G207) — all have a border/background/icon contrast ratio ≥ {min}:1.',
      '{n} 件の UI コンポーネントとアイコンを確認しました（アイコン {i} 件 — G207）。すべて {min}:1 以上のコントラスト比を持っています。',
      { n: data.checkedCount, i: data.iconsChecked || 0, min: MIN_CONTRAST }));
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'serious',
      status: 'fail',
      reason: _t(ctx,
        '{n} UI component(s) have insufficient {label} contrast (< {min}:1): {sample}.',
        '{n} 件の UI コンポーネントの{label}コントラストが不足しています（{min}:1 未満）: {sample}。',
        {
          n: data.violations.length,
          min: MIN_CONTRAST,
          label: data.violations.some(v => v.indicatorLabel === 'icon') ? 'border/background/icon' : 'border/background',
          sample: data.violations.slice(0, 3).map(v => `<${v.target}> ${v.contrast}:1`).join('; '),
        }),
      elements: data.violations,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
