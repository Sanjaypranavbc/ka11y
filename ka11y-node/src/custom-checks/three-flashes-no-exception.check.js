'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

// SC 2.3.2 is the AAA stricter sibling of 2.3.1: no area-based exception —
// even a single pixel flashing > 3 Hz is a failure.
const SC = '2.3.2';
const RULE_ID = 'custom-three-flashes-no-exception';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/three-flashes';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Pages must not contain anything that flashes more than three times per second (no size exception)';

// Stricter period than 2.3.1 — flag everything at or below 333ms (exactly 3 Hz)
const FLASH_PERIOD_MS = 333;

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

  const data = await page.evaluate((flashPeriodMs) => {
    const issues = [];

    const keyframeColors = {};
    for (const sheet of Array.from(document.styleSheets)) {
      try {
        for (const rule of Array.from(sheet.cssRules || [])) {
          if (rule.type === CSSRule.KEYFRAMES_RULE) {
            const colors = [];
            for (const kf of Array.from(rule.cssRules || [])) {
              const m = (kf.cssText || '').match(/(?:background(?:-color)?|color)\s*:\s*(rgba?\([^)]+\)|#[0-9a-f]{3,8}|[a-z]+)/gi);
              if (m) colors.push(...m.map(s => s.split(':')[1].trim()));
            }
            if (colors.length) keyframeColors[rule.name] = colors;
          }
        }
      } catch (_) { /* cross-origin */ }
    }

    function luminance(colorStr) {
      const m = colorStr.match(/\d+\.?\d*/g);
      if (!m || m.length < 3) return null;
      const [r, g, b] = m.slice(0, 3).map(Number);
      return 0.2126 * (r / 255) + 0.7152 * (g / 255) + 0.0722 * (b / 255);
    }

    function isHighContrast(colors) {
      for (let i = 0; i < colors.length - 1; i++) {
        const la = luminance(colors[i]);
        const lb = luminance(colors[i + 1]);
        if (la !== null && lb !== null && Math.abs(la - lb) > 0.1) return true;
      }
      return false;
    }

    // ── Animated elements ─────────────────────────────────────────────────────
    for (const el of document.querySelectorAll('*')) {
      const cs = window.getComputedStyle(el);
      const animName = cs.animationName;
      const animDuration = parseFloat(cs.animationDuration) * 1000;
      const iterCount = cs.animationIterationCount;

      if (!animName || animName === 'none' || isNaN(animDuration) || animDuration > flashPeriodMs) continue;
      const isInfinite = iterCount === 'infinite' || parseFloat(iterCount) > 5;
      if (!isInfinite) continue;

      const colors = keyframeColors[animName] || [];
      const isFlashRisk = colors.length > 0 ? isHighContrast(colors) : animDuration <= 200;
      if (!isFlashRisk) continue;

      const r = el.getBoundingClientRect();
      issues.push({
        type: 'rapid-css-animation',
        target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
        snippet: el.outerHTML.slice(0, 150),
        detail: `animation "${animName}" period ${Math.round(animDuration)}ms — no size exception applies under SC 2.3.2`,
      });
      if (issues.length >= 20) break;
    }

    // ── Animated GIFs (no size exception under 2.3.2) ─────────────────────────
    for (const img of document.querySelectorAll('img[src]')) {
      if (!/\.gif/i.test(img.getAttribute('src') || '')) continue;
      const r = img.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      issues.push({
        type: 'animated-gif',
        target: img.id ? `img#${CSS.escape(img.id)}` : 'img',
        snippet: img.outerHTML.slice(0, 150),
        detail: 'Animated GIF — flash rate unknown; under SC 2.3.2 even small flashing elements must not exceed 3 Hz',
      });
    }

    return { issues };
  }, FLASH_PERIOD_MS);

  if (!data.issues.length) {
    return _pass(ctx, _t(ctx,
      'No rapid animations or animated GIFs detected that could violate the 3-flash-per-second threshold.',
      '1 秒あたり 3 回の点滅閾値に違反する可能性のある高速アニメーションやアニメーション GIF は検出されませんでした。'));
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'critical',
      status: 'incomplete',
      reason: _t(ctx,
        '{n} potential flash source(s) detected. Under SC 2.3.2 no area exception applies — all flashing > 3 Hz must be eliminated.',
        '{n} 件の潜在的な点滅ソースが検出されました。SC 2.3.2 では面積の例外が適用されません — 3 Hz を超えるすべての点滅を排除する必要があります。',
        { n: data.issues.length }),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
