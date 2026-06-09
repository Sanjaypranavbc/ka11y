'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '2.2.2';
const RULE_ID = 'custom-pause-stop-hide';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Moving, blinking, or auto-updating content must be pausable, stoppable, or hideable';

// Minimum animation duration to flag (skip loading spinners which are short/essential)
const MIN_ANIM_DURATION_MS = 1000;
// Animation names likely to indicate motion (not just fade or colour change)
const MOTION_KEYWORDS = /scroll|slide|move|marquee|ticker|rotate|spin|bounce|translate|carousel/i;

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
    const issues = [];

    // ── 1. <marquee> elements (definite fail) ────────────────────────────────
    for (const el of document.querySelectorAll('marquee')) {
      const text = (el.textContent || '').trim();
      if (!text) continue;
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) continue;
      issues.push({
        type: 'marquee',
        severity: 'fail',
        target: 'marquee' + (el.id ? `#${CSS.escape(el.id)}` : ''),
        snippet: el.outerHTML.slice(0, 120),
        detail: '<marquee> scrolls text continuously with no pause control',
      });
    }

    // ── 2. <blink> elements (definite fail) ──────────────────────────────────
    for (const el of document.querySelectorAll('blink')) {
      issues.push({
        type: 'blink',
        severity: 'fail',
        target: 'blink',
        snippet: el.outerHTML.slice(0, 120),
        detail: '<blink> causes text to flash continuously — no pause control',
      });
    }

    // ── 3. CSS text-decoration: blink ────────────────────────────────────────
    for (const el of document.querySelectorAll('*')) {
      const cs = window.getComputedStyle(el);
      if ((cs.textDecorationLine || '').includes('blink')) {
        issues.push({
          type: 'css-blink',
          severity: 'fail',
          target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
          snippet: el.outerHTML.slice(0, 120),
          detail: 'text-decoration: blink causes blinking text with no pause control',
        });
        if (issues.length >= 30) break;
      }
    }

    // ── 4. Infinite CSS animations with motion keywords ──────────────────────
    const checked = new Set();
    for (const el of document.querySelectorAll('[style*="animation"],[class]')) {
      if (checked.has(el)) continue;
      checked.add(el);
      const cs = window.getComputedStyle(el);
      if (!cs.animationName || cs.animationName === 'none') continue;
      if (cs.animationIterationCount !== 'infinite') continue;
      const durationMs = parseFloat(cs.animationDuration) * 1000;
      if (isNaN(durationMs) || durationMs < opts.minDurationMs) continue;
      if (!(new RegExp(opts.motionKeywords, 'i')).test(cs.animationName)) continue;

      const rect = el.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) continue;

      // Check if a pause/play control is present on the page
      const hasPauseControl = !!document.querySelector('[aria-label*="pause" i],[aria-label*="stop" i],[title*="pause" i],[title*="stop" i]');

      issues.push({
        type: 'css-animation',
        severity: 'incomplete',
        target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
        snippet: el.outerHTML.slice(0, 120),
        detail: `Infinite animation "${cs.animationName}" (${Math.round(durationMs)}ms) — ${hasPauseControl ? 'a pause/stop control may be present; verify it controls this animation' : 'no pause/stop/hide control detected on page'}`,
      });
      if (issues.length >= 20) break;
    }

    // ── 5. aria-live assertive regions with content ───────────────────────────
    for (const el of document.querySelectorAll('[aria-live="assertive"],[role="alert"]')) {
      const text = (el.textContent || '').trim();
      if (!text) continue;
      issues.push({
        type: 'aria-live',
        severity: 'incomplete',
        target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
        snippet: el.outerHTML.slice(0, 120),
        detail: 'aria-live="assertive" / role="alert" region has content — if it auto-updates repeatedly, a pause mechanism may be required',
      });
      if (issues.length >= 20) break;
    }

    return { issues };
  }, { minDurationMs: MIN_ANIM_DURATION_MS, motionKeywords: MOTION_KEYWORDS.source });

  if (!data.issues.length) {
    return _pass(ctx, _t(ctx,
      'No <marquee>, <blink>, CSS blink, or infinite motion animations without pause controls detected.',
      'marquee、blink、CSS blink、または一時停止コントロールのない無限モーションアニメーションは検出されませんでした。'));
  }

  const hasDefiniteFail = data.issues.some(i => i.severity === 'fail');
  const status = hasDefiniteFail ? 'fail' : 'incomplete';

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: hasDefiniteFail ? 'critical' : 'moderate',
      status,
      reason: _t(ctx,
        '{n} instance(s) of potentially non-pausable moving or auto-updating content ({types}). Ensure users can pause, stop, or hide any content that moves, blinks, or updates automatically.',
        '{n} 件の一時停止できない可能性のある動き・自動更新コンテンツが検出されました（{types}）。',
        {
          n: data.issues.length,
          types: [...new Set(data.issues.map(i => i.type))].join(', '),
        }),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
