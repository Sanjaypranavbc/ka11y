'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '2.4.12';
const RULE_ID = 'custom-focus-not-obscured-enhanced';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-enhanced';
const MODE = 'interactive';
const FALLBACK_DESCRIPTION = 'When a UI component receives keyboard focus, it must not be hidden at all by author-created content';

const MAX_TABS = 10;
const SETTLE_MS = 40;

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

function _partiallyObscured(focused, sticky) {
  return !(sticky.left > focused.right || sticky.right < focused.left ||
           sticky.top > focused.bottom || sticky.bottom < focused.top);
}

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

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

  const failures = [];   // entirely obscured (fail)
  const partials = [];   // partially overlapped (incomplete — needs human review)
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

    let classified = false;
    for (const sticky of stickyRects) {
      if (_entirelyObscured(focusedRect, sticky)) {
        failures.push({
          html: focusedRect.html,
          tag: focusedRect.tag,
          id: focusedRect.id,
          detail: `Entirely covered by a fixed/sticky element (top:${Math.round(focusedRect.top)} left:${Math.round(focusedRect.left)})`,
        });
        classified = true;
        break;
      } else if (_partiallyObscured(focusedRect, sticky)) {
        partials.push({
          html: focusedRect.html,
          tag: focusedRect.tag,
          id: focusedRect.id,
          detail: `Partially overlapped by a fixed/sticky element — verify focused component is fully visible`,
        });
        classified = true;
        break;
      }
    }
  }

  if (!failures.length && !partials.length) {
    return _pass(ctx, _t(ctx,
      '{n} focusable element(s) sampled — none were obscured (fully or partially) by sticky/fixed content.',
      '{n} 件のフォーカス可能要素をサンプリングしました。固定/スティッキーコンテンツによって隠されたものはありませんでした。',
      { n: tabCount }));
  }

  if (failures.length) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: FALLBACK_DESCRIPTION,
        impact: 'serious',
        status: 'fail',
        reason: _t(ctx,
          '{n} focusable element(s) were entirely hidden by a sticky/fixed element when focused. The enhanced criterion (2.4.12) requires no obscuring at all.',
          '{n} 件のフォーカス可能要素がフォーカス時に固定/スティッキー要素によって完全に隠されていました（強化基準 2.4.12 では一切の遮蔽が禁止されています）。',
          { n: failures.length }),
        elements: failures,
        helpUrl: HELP_URL,
      }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'moderate',
      status: 'incomplete',
      reason: _t(ctx,
        '{n} focusable element(s) were partially overlapped by a sticky/fixed element when focused. Verify that the focused component is fully visible to meet SC 2.4.12 (Enhanced).',
        '{n} 件のフォーカス可能要素がフォーカス時に固定/スティッキー要素と部分的に重なっていました。SC 2.4.12（強化）を満たすには完全に表示される必要があります。',
        { n: partials.length }),
      elements: partials,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
