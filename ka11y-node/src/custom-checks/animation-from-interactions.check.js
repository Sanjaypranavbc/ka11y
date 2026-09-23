'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '2.3.3';
const RULE_ID = 'custom-animation-from-interactions';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Motion animation triggered by interaction must be able to be disabled unless essential';

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

  const data = await page.evaluate(() => {
    // ── Check 1: Does any stylesheet honour prefers-reduced-motion? ───────────
    let hasReducedMotionQuery = false;
    for (const sheet of Array.from(document.styleSheets)) {
      try {
        for (const rule of Array.from(sheet.cssRules || [])) {
          if (rule.type === CSSRule.MEDIA_RULE) {
            const media = rule.conditionText || (rule.media && rule.media.mediaText) || '';
            if (/prefers-reduced-motion/.test(media)) {
              hasReducedMotionQuery = true;
              break;
            }
          }
        }
      } catch (_) { /* cross-origin sheet */ }
      if (hasReducedMotionQuery) break;
    }

    // ── Check 2: Collect elements with transitions/animations ────────────────
    const INTERACTIVE = 'button,a,[role="button"],input,select,textarea,[tabindex]';
    const animated = [];
    for (const el of document.querySelectorAll(INTERACTIVE)) {
      const cs = window.getComputedStyle(el);
      const hasTransition = cs.transitionDuration && cs.transitionDuration !== '0s';
      const hasAnimation = cs.animationName && cs.animationName !== 'none';
      if (hasTransition || hasAnimation) {
        animated.push({
          target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
          snippet: el.outerHTML.slice(0, 150),
          detail: [
            hasTransition && `transition: ${cs.transitionProperty} ${cs.transitionDuration}`,
            hasAnimation && `animation: ${cs.animationName}`,
          ].filter(Boolean).join('; '),
        });
        if (animated.length >= 20) break; // cap reporting
      }
    }

    // ── Check 3 (SCR40): scripts that consult prefers-reduced-motion ─────────
    // Runtime hook records every window.matchMedia() call made by page scripts;
    // fall back to scanning inline <script> text when the hook is not installed.
    const R = window.__ka11yRuntime;
    let hasScriptReducedMotion = !!(R && Array.isArray(R.matchMedia) &&
      R.matchMedia.some(m => /prefers-reduced-motion/i.test(m.query)));
    if (!hasScriptReducedMotion) {
      for (const script of document.querySelectorAll('script:not([src])')) {
        if (/prefers-reduced-motion/i.test(script.textContent || '')) { hasScriptReducedMotion = true; break; }
      }
    }

    return { hasReducedMotionQuery, hasScriptReducedMotion, animatedCount: animated.length, animated };
  });

  // If reduced motion query exists, the page respects user preferences
  if (data.hasReducedMotionQuery) {
    return _pass(ctx, _t(ctx,
      'CSS @media (prefers-reduced-motion) query detected — the page respects motion preferences.',
      'CSS の @media (prefers-reduced-motion) クエリが検出されました。ページはモーション設定を尊重しています。'));
  }
  if (data.hasScriptReducedMotion) {
    return _pass(ctx, _t(ctx,
      'Page scripts query prefers-reduced-motion via matchMedia (SCR40) — motion preferences are respected in JavaScript.',
      'ページのスクリプトが matchMedia で prefers-reduced-motion を参照しています（SCR40）。JavaScript でモーション設定が尊重されています。'));
  }

  if (!data.animatedCount) {
    return _pass(ctx, _t(ctx,
      'No animated interactive elements detected and no prefers-reduced-motion query needed.',
      'アニメーションが適用されたインタラクティブ要素は検出されませんでした。'));
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'moderate',
      status: 'incomplete',
      reason: _t(ctx,
        '{n} interactive element(s) have CSS transitions or animations but no @media (prefers-reduced-motion) block was found. Users who prefer reduced motion cannot disable these animations.',
        '{n} 件のインタラクティブ要素に CSS トランジションまたはアニメーションがありますが、@media (prefers-reduced-motion) ブロックが見つかりませんでした。',
        { n: data.animatedCount }),
      elements: data.animated,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
