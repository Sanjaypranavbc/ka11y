'use strict';

const SC = '2.4.7';
const RULE_ID = 'custom-focus-visible';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/focus-visible';
const MAX_ELEMENTS = 40;
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

async function run(page) {
  // Collect element metadata once (no interaction yet)
  const elements = await page.evaluate((sel, max) => {
    const seen = new Set();
    const items = [];
    for (const el of document.querySelectorAll(sel)) {
      if (seen.has(el)) continue;
      seen.add(el);
      items.push({ idx: items.length, tagName: el.tagName.toLowerCase(), id: el.id || null, html: el.outerHTML.slice(0, 200) });
      if (items.length >= max) break;
    }
    return items;
  }, SELECTOR, MAX_ELEMENTS);

  const violations = [];

  for (const el of elements) {
    // ── Step 1: Capture unfocused styles ─────────────────────────────────────
    const unfocused = await page.evaluate((sel, idx) => {
      const all = Array.from(document.querySelectorAll(sel));
      const e = all[idx];
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
        opacity:         cs.opacity,
      };
    }, SELECTOR, el.idx);

    if (!unfocused) continue;

    // ── Step 2: Focus the element and wait for transitions to settle ──────────
    await page.evaluate((sel, idx) => {
      const all = Array.from(document.querySelectorAll(sel));
      const e = all[idx];
      if (e) e.focus({ preventScroll: true });
    }, SELECTOR, el.idx);

    await new Promise(r => setTimeout(r, SETTLE_MS));

    // ── Step 3: Capture focused styles ────────────────────────────────────────
    const focused = await page.evaluate((sel, idx) => {
      const all = Array.from(document.querySelectorAll(sel));
      const e = all[idx];
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
        opacity:         cs.opacity,
      };
    }, SELECTOR, el.idx);

    // Blur and wait before next element
    await page.evaluate((sel, idx) => {
      const all = Array.from(document.querySelectorAll(sel));
      const e = all[idx];
      if (e) e.blur();
    }, SELECTOR, el.idx);
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
    const opacityChanged     = focused.opacity         !== unfocused.opacity;

    const isVisible = hasVisibleOutline || outlineChanged || boxShadowChanged ||
                      borderChanged || bgChanged || colorChanged || opacityChanged;

    if (!isVisible) {
      violations.push({ tagName: el.tagName, id: el.id, html: el.html });
    }
  }

  if (violations.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: 'Focusable elements must have a visible focus indicator', impact: null, status: 'pass', reason: `All ${elements.length} sampled focusable elements have a visible focus indicator.`, helpUrl: HELP_URL }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Focusable elements must have a visible focus indicator',
      impact: 'serious',
      status: 'fail',
      reason: `${violations.length} focusable element(s) lack a visible focus indicator: ${violations.slice(0, 3).map(v => `<${v.tagName}${v.id ? ` id="${v.id}"` : ''}>`).join(', ')}.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };