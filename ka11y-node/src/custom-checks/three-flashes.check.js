'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '2.3.1';
const RULE_ID = 'custom-three-flashes';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/three-flashes-or-below-threshold';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Pages must not contain anything that flashes more than three times per second, or the flash must be below threshold';

// 3 flashes/sec = period <= 333ms. Use 400ms as a slightly lenient threshold to
// reduce false positives from 2.5 fps animations (400ms) that are borderline.
const FLASH_PERIOD_MS = 400;

function _t(ctx, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, ctx, en);
}

function _pass(ctx, reason) {
  return {
    successCriteriaId: SC,
    rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'pass', reason, helpUrl: HELP_URL }],
  };
}

// Detect high-contrast colour pairs in keyframe stops (luminance delta > 0.1)
function _isHighContrast(colors) {
  if (colors.length < 2) return false;
  const parse = c => {
    const m = c.match(/\d+\.?\d*/g);
    return m && m.length >= 3 ? m.slice(0, 3).map(Number) : null;
  };
  const lum = ([r, g, b]) => 0.2126 * (r / 255) + 0.7152 * (g / 255) + 0.0722 * (b / 255);
  for (let i = 0; i < colors.length - 1; i++) {
    const a = parse(colors[i]);
    const b = parse(colors[i + 1]);
    if (a && b && Math.abs(lum(a) - lum(b)) > 0.1) return true;
  }
  return false;
}

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  const data = await page.evaluate((flashPeriodMs) => {
    const issues = [];

    // ── Scan CSS @keyframes for rapid colour-toggling animations ─────────────
    const keyframeColors = {}; // keyframeName → [colors seen]

    for (const sheet of Array.from(document.styleSheets)) {
      try {
        for (const rule of Array.from(sheet.cssRules || [])) {
          // Collect keyframe colour stops
          if (rule.type === CSSRule.KEYFRAMES_RULE) {
            const colors = [];
            for (const kf of Array.from(rule.cssRules || [])) {
              const text = kf.cssText || '';
              const match = text.match(/(?:background(?:-color)?|color)\s*:\s*(rgba?\([^)]+\)|#[0-9a-f]{3,8}|[a-z]+)/gi);
              if (match) colors.push(...match.map(m => m.split(':')[1].trim()));
            }
            if (colors.length) keyframeColors[rule.name] = colors;
          }
        }
      } catch (_) { /* cross-origin */ }
    }

    // ── Find animated elements using those keyframes ──────────────────────────
    const candidates = document.querySelectorAll('[style*="animation"],[class]');
    const checked = new Set();

    for (const el of candidates) {
      if (checked.has(el)) continue;
      const cs = window.getComputedStyle(el);
      const animName = cs.animationName;
      const animDuration = parseFloat(cs.animationDuration) * 1000; // convert to ms
      const iterCount = cs.animationIterationCount;

      if (!animName || animName === 'none') continue;
      if (isNaN(animDuration) || animDuration > flashPeriodMs) continue; // too slow to be a flash risk

      checked.add(el);
      const isInfinite = iterCount === 'infinite' || parseFloat(iterCount) > 10;
      const colors = keyframeColors[animName] || [];

      // Only flag if colour changes are high-contrast (actual luminance flash)
      // OR if we can't inspect the keyframe (external sheet) and the period is very short
      const isFlashRisk = colors.length > 0
        ? _isHighContrast(colors) // we have colour data
        : animDuration <= 200;    // very short unknown animation is suspect

      if (isInfinite && isFlashRisk) {
        const r = el.getBoundingClientRect();
        const areaNote = (r.width > 0 && r.height > 0)
          ? ` (${Math.round(r.width)}×${Math.round(r.height)}px)`
          : '';
        issues.push({
          type: 'rapid-css-animation',
          target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
          snippet: el.outerHTML.slice(0, 150),
          detail: `animation "${animName}" duration ${Math.round(animDuration)}ms (≥${Math.round(1000 / animDuration * 2).toFixed(1)} flashes/sec)${areaNote}`,
          width: Math.round(r.width),
          height: Math.round(r.height),
        });
      }
    }

    // ── Check for <img> with very short animated GIF filenames ───────────────
    for (const img of document.querySelectorAll('img[src]')) {
      const src = (img.getAttribute('src') || '').toLowerCase();
      if (/\.gif/.test(src)) {
        const r = img.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) continue;
        issues.push({
          type: 'animated-gif',
          target: img.id ? `img#${CSS.escape(img.id)}` : 'img',
          snippet: img.outerHTML.slice(0, 150),
          detail: `Animated GIF at ${src.split('/').pop()} — flash rate cannot be determined without loading the file`,
          width: Math.round(r.width),
          height: Math.round(r.height),
        });
      }
    }

    return { issues };
  }, FLASH_PERIOD_MS);

  if (!data.issues.length) {
    return _pass(ctx, _t(ctx,
      'No rapid CSS animations or animated GIFs with potential flash risk detected.',
      '点滅リスクのある高速 CSS アニメーションやアニメーション GIF は検出されませんでした。'));
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'critical',
      status: 'incomplete',
      reason: _t(ctx,
        '{n} potential flash source(s) detected (rapid CSS animation or animated GIF). Verify flash rate and area are within threshold, or remove the animation.',
        '{n} 件の潜在的な点滅ソースが検出されました（高速 CSS アニメーションまたはアニメーション GIF）。点滅レートと面積が閾値内かどうか確認するか、アニメーションを削除してください。',
        { n: data.issues.length }),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
