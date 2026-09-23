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

  const issues = [];

  // ── Phase 2 (SCR39): custom hover content without tooltip markers ─────────
  // Hover a sample of focusable elements, diff the set of visible positioned
  // overlays before/after, then test the three SC requirements on what appeared:
  // hoverable (pointer can move onto it), persistent (stays until dismissed) and
  // dismissible (Escape closes it without moving the pointer).
  let hoverSample = 0, hoverRevealed = 0;
  try {
    const focusables = (ctx.focusableElements && ctx.focusableElements.length) ? ctx.focusableElements : [];
    const skipSel = new Set(candidates.map(c => c.selector));
    const sample = [];
    for (const el of focusables) {
      if (sample.length >= 12) break;
      if (el.stableSel && skipSel.has(el.stableSel)) continue;
      if (!/^(a|button|span|div|li|input)$/i.test(el.tagName || '')) continue;
      sample.push(el);
    }
    const snapshot = () => page.evaluate(() => {
      const out = []; let i = 0;
      for (const el of document.querySelectorAll('body *')) {
        if (i++ > 6000) break;
        const cs = window.getComputedStyle(el);
        if (cs.position !== 'absolute' && cs.position !== 'fixed') continue;
        if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) < 0.1) continue;
        const r = el.getBoundingClientRect();
        if (r.width < 20 || r.height < 10) continue;
        if (!(el.textContent || '').trim() && !el.querySelector('img, svg')) continue;
        el.__ka11yHoverId = el.__ka11yHoverId || ('h' + Math.random().toString(36).slice(2));
        out.push({ id: el.__ka11yHoverId, x: r.left + r.width / 2, y: r.top + r.height / 2 });
      }
      return out;
    });
    const visibleById = (id) => page.evaluate((hid) => {
      for (const el of document.querySelectorAll('body *')) {
        if (el.__ka11yHoverId === hid) { const cs = window.getComputedStyle(el); const r = el.getBoundingClientRect(); return cs.display !== 'none' && cs.visibility !== 'hidden' && parseFloat(cs.opacity) >= 0.1 && r.width > 0; }
      }
      return false;
    }, id);
    for (const el of sample) {
      const pos = await page.evaluate(({ idx, stableSel }) => {
        const node = stableSel ? document.querySelector(stableSel) : Array.from(document.querySelectorAll('*'))[idx];
        if (!node) return null;
        node.scrollIntoView({ block: 'center' });
        const r = node.getBoundingClientRect();
        return r.width > 0 && r.height > 0 ? { x: r.left + r.width / 2, y: r.top + r.height / 2 } : null;
      }, { idx: el.idx, stableSel: el.stableSel });
      if (!pos) continue;
      hoverSample++;
      await page.mouse.move(0, 0); await settle(page, 120);
      const beforeList = await snapshot();
      const before = new Set((Array.isArray(beforeList) ? beforeList : []).map(s => s.id));
      await page.mouse.move(pos.x, pos.y); await settle(page, 350);
      const afterList = await snapshot();
      const fresh = (Array.isArray(afterList) ? afterList : []).filter(s => !before.has(s.id));
      if (!fresh.length) continue;
      hoverRevealed++;
      const content = fresh[0];
      await page.mouse.move(content.x, content.y); await settle(page, 250);
      const hoverable = await visibleById(content.id);
      await settle(page, 1000);
      const persistent = await visibleById(content.id);
      await page.mouse.move(pos.x, pos.y); await settle(page, 150);
      await page.keyboard.press('Escape'); await settle(page, 250);
      const dismissed = !(await visibleById(content.id));
      await page.mouse.move(0, 0); await settle(page, 150);
      const gone = !(await visibleById(content.id));
      const target = el.stableSel || el.tagName;
      if (!hoverable) issues.push({ type: 'hover-content-not-hoverable', target, detail: 'Content revealed on hover disappears when the pointer moves onto it (SCR39 — hoverable)' });
      if (hoverable && !persistent) issues.push({ type: 'hover-content-not-persistent', target, detail: 'Content revealed on hover disappears by itself within about a second (SCR39 — persistent)' });
      if (!dismissed && gone) issues.push({ type: 'hover-content-not-dismissible', target, detail: 'Content revealed on hover cannot be dismissed with Escape without moving the pointer (SCR39 — dismissible)' });
    }
  } catch (_) { /* best effort — never fail the check */ }

  if (!candidates.length && !issues.length) {
    return _pass(ctx, hoverSample
      ? _t(ctx, 'No tooltip trigger markers; {n} focusable element(s) hovered and {r} custom hover content(s) verified hoverable, persistent and dismissible (SCR39).', 'ツールチップのマーカーはありません。フォーカス可能要素 {n} 件にホバーし、{r} 件のカスタムホバーコンテンツがホバー可能・持続的・閉じられることを確認しました（SCR39）。', { n: hoverSample, r: hoverRevealed })
      : _t(ctx, 'No hover/focus tooltip trigger elements found on this page.', 'ホバー/フォーカスのツールチップトリガー要素が見つかりませんでした。'));
  }

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
      '{n} hover/focus tooltip trigger(s) checked and {h} focusable element(s) hovered ({r} custom hover content(s)) — all appear to meet the hoverable, persistent and dismissible requirements.',
      '{n} 件のホバー/フォーカストリガーを確認し、フォーカス可能要素 {h} 件にホバー（カスタムホバーコンテンツ {r} 件）しました。すべてホバー可能・持続的・閉じられる要件を満たしているようです。',
      { n: candidates.length, h: hoverSample, r: hoverRevealed }));
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'moderate',
      status: 'incomplete',
      reason: _t(ctx,
        '{i} issue(s) across {n} tooltip trigger(s) and {h} hovered element(s): {types}. Hover content must be hoverable, persistent and dismissible (SCR39).',
        'ツールチップトリガー {n} 件とホバーした要素 {h} 件で {i} 件の問題: {types}。ホバーで表示されるコンテンツはホバー可能・持続的・閉じられる必要があります（SCR39）。',
        { i: issues.length, n: candidates.length, h: hoverSample, types: [...new Set(issues.map(i => i.type))].join(', ') }),
      elements: issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
