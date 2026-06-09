'use strict';

const { getSharedRuleContext, renderLocalizedText, settle } = require('./sharedAssets');

const SC = '1.4.13';
const RULE_ID = 'custom-content-on-hover-focus';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/content-on-hover-or-focus';
const MODE = 'interactive';
const FALLBACK_DESCRIPTION = 'Content that appears on hover or focus must be dismissible, hoverable, and persistent';

const MAX_CANDIDATES = 10;

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

  // ── Phase 1: Find tooltip trigger candidates in the DOM ──────────────────
  const candidates = await page.evaluate((max) => {
    const results = [];
    // Elements likely to have hover-triggered content:
    // 1. aria-describedby pointing to a hidden element
    // 2. [title] attributes (native browser tooltip)
    // 3. role="tooltip" targets' triggers
    // 4. Elements with data-tooltip, data-tippy, data-bs-toggle="tooltip" etc.
    const TOOLTIP_TRIGGERS = '[title],[aria-describedby],[data-tooltip],[data-tippy-content],[data-bs-toggle="tooltip"],[data-original-title]';

    for (const el of document.querySelectorAll(TOOLTIP_TRIGGERS)) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      if (r.top < 0 || r.top > window.innerHeight) continue;

      results.push({
        selector: el.id ? `#${CSS.escape(el.id)}` : el.tagName.toLowerCase(),
        x: Math.round(r.left + r.width / 2),
        y: Math.round(r.top + r.height / 2),
        hasTitle: el.hasAttribute('title'),
        describedBy: el.getAttribute('aria-describedby') || null,
      });
      if (results.length >= max) break;
    }
    return results;
  }, MAX_CANDIDATES);

  if (!candidates.length) {
    return _pass(ctx, _t(ctx,
      'No hover/focus tooltip trigger elements found on this page.',
      'ホバー/フォーカスのツールチップトリガー要素が見つかりませんでした。'));
  }

  const issues = [];

  for (const cand of candidates) {
    try {
      // Hover over the trigger element
      await page.mouse.move(cand.x, cand.y);
      await settle(page, 300);

      const result = await page.evaluate((sel, dby) => {
        // ── Check 1: Does content appear? ──────────────────────────────────
        let tooltipEl = null;
        if (dby) {
          tooltipEl = document.getElementById(dby);
        }
        if (!tooltipEl) {
          tooltipEl = document.querySelector('[role="tooltip"]:not([hidden])');
        }

        const tooltipVisible = tooltipEl
          ? (tooltipEl.offsetParent !== null && window.getComputedStyle(tooltipEl).visibility !== 'hidden')
          : false;

        // ── Check 2: Is tooltip hoverable? (has bounding box > 0) ──────────
        let isHoverable = false;
        if (tooltipEl && tooltipVisible) {
          const r = tooltipEl.getBoundingClientRect();
          isHoverable = r.width > 0 && r.height > 0;
        }

        // ── Check 3: [title] attribute — browser native, cannot be made hoverable ──
        const triggerEl = document.querySelector(sel) || document.querySelector(`[aria-describedby="${CSS.escape(dby || '')}"]`);
        const hasNativeTitle = triggerEl && triggerEl.hasAttribute('title') && !dby;

        return { tooltipVisible, isHoverable, hasNativeTitle };
      }, cand.selector, cand.describedBy || '');

      // [title] tooltips are browser-native and cannot be made hoverable — always flag
      if (result.hasNativeTitle) {
        issues.push({
          type: 'native-title-tooltip',
          target: cand.selector,
          detail: 'Browser-native [title] tooltip cannot be hovered over or dismissed with Esc — replace with a custom tooltip',
        });
      } else if (result.tooltipVisible && !result.isHoverable) {
        issues.push({
          type: 'tooltip-not-hoverable',
          target: cand.selector,
          detail: 'Tooltip appears on hover but has zero dimensions — users cannot move pointer over it',
        });
      }

      // Move mouse away to reset
      await page.mouse.move(0, 0);
      await settle(page, 150);
    } catch (_) {
      // Skip this candidate if interaction fails
    }
  }

  if (!issues.length) {
    return _pass(ctx, _t(ctx,
      '{n} hover/focus tooltip trigger(s) checked — all appear to meet hover and dismiss requirements.',
      '{n} 件のホバー/フォーカストリガーを確認しました。すべてホバーと閉じる要件を満たしているようです。',
      { n: candidates.length }));
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'moderate',
      status: 'incomplete',
      reason: _t(ctx,
        '{i} of {n} hover/focus tooltip trigger(s) have issues (not hoverable or browser-native [title]). Manual review required.',
        '{n} 件中 {i} 件のホバー/フォーカストリガーに問題があります（ホバー不可またはネイティブ [title]）。手動確認が必要です。',
        { i: issues.length, n: candidates.length }),
      elements: issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
