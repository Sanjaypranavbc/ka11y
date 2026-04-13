'use strict';

const {
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '2.4.7';
const RULE_ID = 'custom-focus-visible';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/focus-visible';
const MAX_ELEMENTS = 100;
// Settle delay: allow CSS transitions and React/Vue re-renders to apply before capturing styles
const SETTLE_MS = 80;

const SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);
  // Collect element metadata once — include stable selectors (B11: DOM index shifts when
  // focus triggers DOM mutations; stable selectors survive re-queries after mutations).
  const elements = await page.evaluate((sel, max) => {
    const seen = new Set();
    const items = [];
    const idCounts = {};
    for (const el of document.querySelectorAll('[id]')) {
      idCounts[el.id] = (idCounts[el.id] || 0) + 1;
    }
    for (const el of document.querySelectorAll(sel)) {
      if (seen.has(el)) continue;
      seen.add(el);
      let stableSel = null;
      if (el.id && idCounts[el.id] === 1) stableSel = `#${CSS.escape(el.id)}`;
      items.push({ idx: items.length, stableSel, tagName: el.tagName.toLowerCase(), id: el.id || null, html: el.outerHTML.slice(0, 200) });
      if (items.length >= max) break;
    }
    return items;
  }, SELECTOR, MAX_ELEMENTS);

  const violations = [];

  for (const el of elements) {
    // ── Step 1: Capture unfocused styles ─────────────────────────────────────
    // Use stable selector when available to survive DOM mutations caused by focus (B11).
    const unfocused = await page.evaluate((sel, idx, stableSel) => {
      const e = stableSel
        ? (document.querySelector(stableSel) || Array.from(document.querySelectorAll(sel))[idx])
        : Array.from(document.querySelectorAll(sel))[idx];
      if (!e) return null;
      e.blur();
      const cs = window.getComputedStyle(e);
      return {
        outlineWidth:    cs.outlineWidth,
        outlineStyle:    cs.outlineStyle,
        outlineColor:    cs.outlineColor,
        boxShadow:       cs.boxShadow,
        borderColor:     cs.borderColor,
        borderWidth:     cs.borderWidth,
        backgroundColor: cs.backgroundColor,
        color:           cs.color,
        transform:       cs.transform,
      };
    }, SELECTOR, el.idx, el.stableSel);

    if (!unfocused) continue;

    // ── Step 2: Focus the element and wait for transitions to settle ──────────
    await page.evaluate((sel, idx, stableSel) => {
      const e = stableSel
        ? (document.querySelector(stableSel) || Array.from(document.querySelectorAll(sel))[idx])
        : Array.from(document.querySelectorAll(sel))[idx];
      if (e) e.focus({ preventScroll: true });
    }, SELECTOR, el.idx, el.stableSel);

    await new Promise(r => setTimeout(r, SETTLE_MS));

    // ── Step 3: Capture focused styles ────────────────────────────────────────
    const focused = await page.evaluate((sel, idx, stableSel) => {
      const e = stableSel
        ? (document.querySelector(stableSel) || Array.from(document.querySelectorAll(sel))[idx])
        : Array.from(document.querySelectorAll(sel))[idx];
      if (!e) return null;
      const cs = window.getComputedStyle(e);
      return {
        outlineWidth:    cs.outlineWidth,
        outlineStyle:    cs.outlineStyle,
        outlineColor:    cs.outlineColor,
        boxShadow:       cs.boxShadow,
        borderColor:     cs.borderColor,
        borderWidth:     cs.borderWidth,
        backgroundColor: cs.backgroundColor,
        color:           cs.color,
        transform:       cs.transform,
      };
    }, SELECTOR, el.idx, el.stableSel);

    // Blur and wait before next element
    await page.evaluate((sel, idx, stableSel) => {
      const e = stableSel
        ? (document.querySelector(stableSel) || Array.from(document.querySelectorAll(sel))[idx])
        : Array.from(document.querySelectorAll(sel))[idx];
      if (e) e.blur();
    }, SELECTOR, el.idx, el.stableSel);
    await new Promise(r => setTimeout(r, SETTLE_MS));

    if (!focused) continue;

    // ── Step 4: Determine if a visual change occurred ─────────────────────────
    // Verify the focused outline is not transparent before counting it visible.
    // Covers: transparent keyword, rgba/hsla with alpha=0, inherit/initial/unset/revert.
    const _oc = (focused.outlineColor || '').trim();
    const _outlineColorInvisible =
      /^(transparent|inherit|initial|unset|revert)$/i.test(_oc) ||
      /^rgba?\s*\([^)]*,\s*0\.?0*\s*\)$/i.test(_oc) ||
      /^hsla?\s*\([^)]*,\s*0%?\s*\)$/i.test(_oc);
    const outlineActuallyVisible =
      focused.outlineStyle !== 'none' &&
      focused.outlineWidth !== '0px' &&
      !_outlineColorInvisible;
    const hasVisibleOutline = outlineActuallyVisible;
    const outlineChanged =
      (focused.outlineWidth  !== unfocused.outlineWidth  ||
       focused.outlineStyle  !== unfocused.outlineStyle  ||
       focused.outlineColor  !== unfocused.outlineColor) &&
      outlineActuallyVisible;
    const boxShadowChanged   = focused.boxShadow       !== unfocused.boxShadow &&
                               focused.boxShadow       !== 'none';
    const borderChanged      = focused.borderColor     !== unfocused.borderColor ||
                               focused.borderWidth     !== unfocused.borderWidth;
    const bgChanged          = focused.backgroundColor !== unfocused.backgroundColor;
    const colorChanged       = focused.color           !== unfocused.color;
    const transformChanged   = focused.transform       !== unfocused.transform;
    // B16: opacity change alone is NOT a visible focus indicator — it reflects CSS animations
    // or transitions on child elements and produces false passes (e.g. a loading spinner
    // child transitioning 0→1 while the button itself has no focus style).
    const isVisible = hasVisibleOutline || outlineChanged || boxShadowChanged ||
                      borderChanged || bgChanged || colorChanged || transformChanged;

    if (!isVisible) {
      violations.push({ tagName: el.tagName, id: el.id, html: el.html });
    }
  }

  if (violations.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: 'Focusable elements must have a visible focus indicator', impact: null, status: 'pass', reason: _t(sharedContext, 'All {count} sampled focusable elements have a visible focus indicator.', 'サンプリングしたフォーカス可能要素 {count} 件すべてに、視認できるフォーカスインジケーターがあります。', { count: elements.length }), helpUrl: HELP_URL }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Focusable elements must have a visible focus indicator',
      impact: 'serious',
      status: 'fail',
      reason: _t(
        sharedContext,
        '{count} focusable element(s) lack a visible focus indicator: {sample}.',
        'フォーカス可能要素 {count} 件に、視認できるフォーカスインジケーターがありません: {sample}。',
        {
          count: violations.length,
          sample: violations.slice(0, 3).map(v => `<${v.tagName}${v.id ? ` id="${v.id}"` : ''}>`).join(', '),
        },
      ),
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
