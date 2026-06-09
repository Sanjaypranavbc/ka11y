'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '2.4.11';
const RULE_ID = 'custom-focus-not-obscured';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum';
const MODE = 'interactive';
const FALLBACK_DESCRIPTION = 'When a UI component receives keyboard focus, it must not be entirely hidden by author-created content';

const MAX_TABS = 15;
const SETTLE_MS = 80;

function _t(ctx, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, ctx, en);
}

function _pass(ctx, reason) {
  return {
    successCriteriaId: SC,
    rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'pass', reason, helpUrl: HELP_URL }],
  };
}

function _entirelyObscured(focused, sticky) {
  return (
    sticky.left  <= focused.left  &&
    sticky.right >= focused.right &&
    sticky.top   <= focused.top   &&
    sticky.bottom >= focused.bottom
  );
}

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  // Collect all fixed/sticky overlay rects
  const stickyRects = await page.evaluate(() => {
    const rects = [];
    for (const el of document.querySelectorAll('*')) {
      const cs = window.getComputedStyle(el);
      if (cs.position !== 'fixed' && cs.position !== 'sticky') continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      rects.push({ top: r.top, right: r.right, bottom: r.bottom, left: r.left });
    }
    return rects;
  });

  if (!stickyRects.length) {
    return _pass(ctx, _t(ctx,
      'No fixed or sticky positioned elements found on this page — focus cannot be obscured.',
      '固定またはスティッキー配置の要素が見つかりませんでした。フォーカスが隠れることはありません。'));
  }

  const violations = [];
  let tabCount = 0;

  for (let i = 0; i < MAX_TABS; i++) {
    await page.keyboard.press('Tab');
    await new Promise(r => setTimeout(r, SETTLE_MS));

    const focusedRect = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body || el === document.documentElement) return null;
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) return null;
      return {
        top: r.top, right: r.right, bottom: r.bottom, left: r.left,
        html: el.outerHTML.slice(0, 120),
        tag: el.tagName.toLowerCase(),
        id: el.id || null,
      };
    });

    if (!focusedRect) continue;
    tabCount++;

    const isEntirelyObscured = stickyRects.some(s => _entirelyObscured(focusedRect, s));
    if (isEntirelyObscured) {
      violations.push({
        html: focusedRect.html,
        tag: focusedRect.tag,
        id: focusedRect.id,
        detail: `Focused element (top:${Math.round(focusedRect.top)} left:${Math.round(focusedRect.left)}) is entirely covered by a fixed/sticky element`,
      });
    }
  }

  if (!violations.length) {
    return _pass(ctx, _t(ctx,
      '{n} focusable element(s) sampled — none were entirely hidden by sticky/fixed content.',
      '{n} 件のフォーカス可能要素をサンプリングしました。固定/スティッキーコンテンツによって完全に隠されたものはありませんでした。',
      { n: tabCount }));
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'serious',
      status: 'fail',
      reason: _t(ctx,
        '{n} focusable element(s) were entirely hidden by a sticky/fixed element when focused. Keyboard-only users cannot see where focus is.',
        '{n} 件のフォーカス可能要素がフォーカス時に固定/スティッキー要素によって完全に隠されていました。',
        { n: violations.length }),
      elements: violations,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
