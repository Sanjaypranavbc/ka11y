'use strict';

const {
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '2.4.13';
const RULE_ID = 'custom-focus-appearance';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance';

// WCAG 2.4.13 requirements:
// 1. Focus indicator encloses the component OR has area ≥ perimeter × 2 CSS px
// 2. Contrast ratio between focused and unfocused states ≥ 3:1
const MIN_CONTRAST = 3.0;
const MIN_OUTLINE_WIDTH_PX = 2; // Sufficient for area requirement on typical elements
const MAX_ELEMENTS = 2000;
const SETTLE_MS = 80;

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

function _formatIssue(issue, context) {
  if (!issue) return '';

  if (typeof issue === 'string') {
    return issue;
  }

  switch (issue.code) {
    case 'no-indicator':
      return _t(context, 'no-indicator', 'フォーカスインジケーターなし');
    case 'outline-too-thin':
      return _t(
        context,
        'outline-width {outlineWidth} < {minWidth}px (area requirement)',
        'アウトライン幅 {outlineWidth} が {minWidth}px 未満です（面積要件）。',
        issue,
      );
    case 'low-contrast':
      return _t(
        context,
        'focus indicator contrast < {contrast}:1 against background',
        'フォーカスインジケーターのコントラストが背景に対して {contrast}:1 未満です。',
        issue,
      );
    default:
      return '';
  }
}

function _formatIssueList(issues, context) {
  if (!Array.isArray(issues) || issues.length === 0) return '';
  return issues.map(issue => _formatIssue(issue, context)).filter(Boolean).join('; ');
}

/**
 * Relative luminance per WCAG 2.x formula.
 * Input: "rgb(r, g, b)" or "rgba(r, g, b, a)" string; returns null if unparseable.
 */
function relativeLuminance(colorStr) {
  if (!colorStr) return null;
  const m = String(colorStr).match(/\d+\.?\d*/g);
  if (!m || m.length < 3) return null;
  const [r, g, b] = [parseFloat(m[0]), parseFloat(m[1]), parseFloat(m[2])].map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrastRatio(l1, l2) {
  const lighter = Math.max(l1, l2) + 0.05;
  const darker = Math.min(l1, l2) + 0.05;
  return lighter / darker;
}

/**
 * Split a CSS `box-shadow` value into its comma-separated layers, respecting
 * parentheses so that `rgb(0, 95, 204)` colour functions are not split on their
 * internal commas. Returns [] for "none"/empty.
 *
 * @param {string} boxShadow computed box-shadow string
 * @returns {string[]} one entry per shadow layer
 */
function splitBoxShadowLayers(boxShadow) {
  if (!boxShadow || boxShadow === 'none') return [];
  const layers = [];
  let depth = 0;
  let current = '';
  for (const ch of String(boxShadow)) {
    if (ch === '(') depth++;
    else if (ch === ')') depth--;
    if (ch === ',' && depth === 0) {
      if (current.trim()) layers.push(current.trim());
      current = '';
    } else {
      current += ch;
    }
  }
  if (current.trim()) layers.push(current.trim());
  return layers;
}

/**
 * Extract the spread radius and indicator colour from a single box-shadow layer.
 * CSS length order is offset-x, offset-y, blur-radius, spread-radius, so the
 * spread is the 4th length token (lengths may be unitless `0` or e.g. `3px`).
 *
 * @param {string} layer a single shadow layer (from splitBoxShadowLayers)
 * @returns {{ spread: number, color: string|null }}
 */
function extractBoxShadowMetrics(layer) {
  if (!layer) return { spread: 0, color: null };
  const colorMatch = String(layer).match(/(rgba?\([^)]*\)|hsla?\([^)]*\)|#[0-9a-fA-F]{3,8})/);
  const color = colorMatch ? colorMatch[0] : null;
  const lengths = (String(layer)
    .replace(/(rgba?\([^)]*\)|hsla?\([^)]*\))/g, ' ')
    .match(/-?\d*\.?\d+(?:px)?/g) || [])
    .map(parseFloat)
    .filter((n) => !Number.isNaN(n));
  const spread = lengths.length >= 4 ? Math.abs(lengths[3]) : 0;
  return { spread, color };
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);
  // Snapshot element styles before/after focus in separate evaluate calls
  // to allow the browser to settle between focus state changes.

  const SELECTOR = [
    'a[href]',
    'button:not([disabled])',
    'input:not([disabled]):not([type="hidden"])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    '[tabindex]:not([tabindex="-1"])',
  ].join(', ');

  // Collect elements to test.
  // Each item stores a stable_sel: either "#id" (if unique ID exists) or the
  // nth-of-type selector, so re-queries in subsequent evaluate() calls target
  // the SAME element even if sibling DOM mutations have occurred.
  const elements = await page.evaluate((sel, max) => {
    const seen = new Set();
    const items = [];
    const idCounts = {};
    // Count IDs to detect duplicates (which would make "#id" non-unique)
    for (const el of document.querySelectorAll('[id]')) {
      idCounts[el.id] = (idCounts[el.id] || 0) + 1;
    }
    for (const el of document.querySelectorAll(sel)) {
      if (seen.has(el)) continue;
      seen.add(el);
      // Build a stable selector: prefer unique id, fallback to global DOM index
      let stableSel = null;
      if (el.id && idCounts[el.id] === 1) {
        stableSel = `#${CSS.escape(el.id)}`;
      }
      items.push({
        idx:       items.length,
        stableSel,
        tag:       el.tagName.toUpperCase(),
        tagName:   el.tagName.toLowerCase(),
        target:    stableSel ? [stableSel] : [el.tagName.toLowerCase()],
        id:        el.id || null,
        html:      el.outerHTML.slice(0, 150),
      });
      if (items.length >= max) break;
    }
    return items;
  }, SELECTOR, MAX_ELEMENTS);

  const violations = [];
  const passes = [];

  for (const el of elements) {
    // ── L-2: collapsed per-element round-trip (mirrors L-1 in focus-visible) ──
    // One `page.evaluate` runs the full unfocused-capture → focus → settle →
    // focused-capture → blur cycle browser-side. CDP cost: 1 RT instead of 3.
    // SETTLE_MS waits stay inside the page context so CSS transitions still
    // get to resolve. Also captures body background in the same pass for the
    // transparent-element fallback (B5).
    const sample = await page.evaluate(
      ({ sel, idx, stableSel, settleMs }) => {
        const findEl = () =>
          stableSel
            ? (document.querySelector(stableSel) ||
               Array.from(document.querySelectorAll(sel))[idx])
            : Array.from(document.querySelectorAll(sel))[idx];

        const captureBox = (node) => {
          const cs = window.getComputedStyle(node);
          return {
            outlineWidth:    cs.outlineWidth,
            outlineStyle:    cs.outlineStyle,
            outlineColor:    cs.outlineColor,
            boxShadow:       cs.boxShadow,
            backgroundColor: cs.backgroundColor,
            borderColor:     cs.borderColor,
            borderWidth:     cs.borderWidth,
          };
        };

        const e1 = findEl();
        if (!e1) return null;

        e1.blur();
        const unfocused = captureBox(e1);

        return new Promise((resolve) => {
          setTimeout(() => {
            const e2 = findEl();
            if (!e2) {
              resolve({ unfocused, focused: null });
              return;
            }
            e2.focus({ preventScroll: true });
            setTimeout(() => {
              const e3 = findEl();
              if (!e3) {
                resolve({ unfocused, focused: null });
                return;
              }
              const focused = {
                ...captureBox(e3),
                bodyBg: window.getComputedStyle(document.body).backgroundColor,
              };
              e3.blur();
              resolve({ unfocused, focused });
            }, settleMs);
          }, settleMs);
        });
      },
      { sel: SELECTOR, idx: el.idx, stableSel: el.stableSel, settleMs: SETTLE_MS },
    );

    if (!sample) continue;
    const { unfocused, focused } = sample;
    if (!unfocused || !focused) continue;

    // ── Check 1: Does a visible focus indicator appear? ──────────────────────
    const outlineWidthPx = parseFloat(focused.outlineWidth) || 0;
    const hasVisibleOutline = focused.outlineStyle !== 'none' && outlineWidthPx > 0;
    const boxShadowAdded = focused.boxShadow !== unfocused.boxShadow &&
                           focused.boxShadow !== 'none';
    const borderChanged  = focused.borderColor !== unfocused.borderColor ||
                           focused.borderWidth !== unfocused.borderWidth;

    const hasFocusIndicator = hasVisibleOutline || boxShadowAdded || borderChanged;
    if (!hasFocusIndicator) {
      // No visible indicator at all — this is a fail
      violations.push({
        ...el,
        issues: [{ code: 'no-indicator' }],
      });
      continue;
    }

    // ── Check 2: Area requirement proxy ──────────────────────────────────────
    // For outline: width ≥ MIN_OUTLINE_WIDTH_PX.
    // For box-shadow: spread radius ≥ MIN_OUTLINE_WIDTH_PX (B4: was always true when no outline).
    // For border change: border-width ≥ MIN_OUTLINE_WIDTH_PX counts as area met.
    let meetsAreaReq;
    let boxShadowColor = null;
    if (hasVisibleOutline) {
      const outlineWidth = outlineWidthPx;
      const spreadRadius = 0; // not relevant here
      const borderWidth = parseFloat(focused.borderWidth) || 0;
      const borderChangedForArea = focused.borderWidth !== unfocused.borderWidth;
      const areaMet = outlineWidth >= MIN_OUTLINE_WIDTH_PX || spreadRadius >= MIN_OUTLINE_WIDTH_PX || (borderChangedForArea && borderWidth >= MIN_OUTLINE_WIDTH_PX);
      meetsAreaReq = areaMet;
    } else if (boxShadowAdded) {
      // A box-shadow can have multiple comma-separated layers; the spread radius
      // (4th length) of the *largest* layer is what visually encloses the element,
      // so pick the best spread across all layers (was: only the first layer, which
      // also broke when the colour function contained commas, e.g. rgb(0,95,204)).
      const metrics = splitBoxShadowLayers(focused.boxShadow).map(extractBoxShadowMetrics);
      const best = metrics.reduce(
        (acc, m) => (m.spread > acc.spread ? m : acc),
        { spread: 0, color: null },
      );
      boxShadowColor = best.color;
      const spreadRadius = best.spread;
      const borderWidth = parseFloat(focused.borderWidth) || 0;
      const borderChangedForArea = focused.borderWidth !== unfocused.borderWidth;
      const areaMet = outlineWidthPx >= MIN_OUTLINE_WIDTH_PX || spreadRadius >= MIN_OUTLINE_WIDTH_PX || (borderChangedForArea && borderWidth >= MIN_OUTLINE_WIDTH_PX);
      meetsAreaReq = areaMet;
    } else {
      // border-based indicators: check if border width meets the minimum
      const borderWidth = parseFloat(focused.borderWidth) || 0;
      const borderChangedForArea = focused.borderWidth !== unfocused.borderWidth;
      meetsAreaReq = borderChangedForArea && borderWidth >= MIN_OUTLINE_WIDTH_PX;
    }

    // ── Check 3: Contrast ≥ 3:1 between focused indicator and adjacent area ──
    // We compare the outline/box-shadow color against the element background color.
    // B5: when element background is transparent, fall back to the page body background
    // rather than treating transparent as black (which produced wrong contrast ratios).
    let meetsContrast = true; // assume pass if we can't measure
    // The indicator colour we measure depends on which indicator was detected:
    // outline → outlineColor; box-shadow → the shadow's own colour; otherwise the
    // (changed) border colour. Using the box-shadow colour fixes false low-contrast
    // failures where a coloured shadow sat over an unchanged (e.g. black) border.
    const focusColor = hasVisibleOutline
      ? focused.outlineColor
      : (boxShadowAdded && boxShadowColor ? boxShadowColor : focused.borderColor);
    const isTransparent = (c) => !c || c === 'transparent' || c === 'rgba(0, 0, 0, 0)';
    const bgColor = !isTransparent(focused.backgroundColor)
      ? focused.backgroundColor
      : !isTransparent(unfocused.backgroundColor)
        ? unfocused.backgroundColor
        : (!isTransparent(focused.bodyBg) ? focused.bodyBg : 'rgb(255, 255, 255)');

    const lumFocus = relativeLuminance(focusColor);
    const lumBg    = relativeLuminance(bgColor);
    if (lumFocus !== null && lumBg !== null) {
      const cr = contrastRatio(lumFocus, lumBg);
      meetsContrast = cr >= MIN_CONTRAST;
    }

    if (!meetsAreaReq || !meetsContrast) {
      const issues = [];
      if (!meetsAreaReq) {
        issues.push({
          code: 'outline-too-thin',
          outlineWidth: focused.outlineWidth,
          minWidth: MIN_OUTLINE_WIDTH_PX,
        });
      }
      if (!meetsContrast) {
        issues.push({
          code: 'low-contrast',
          contrast: MIN_CONTRAST,
        });
      }
      violations.push({
        ...el,
        issues,
      });
    } else {
      passes.push(el);
    }
  }

  if (violations.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Focus indicators must have sufficient area and contrast',
        impact: null,
        status: 'pass',
        reason: _t(sharedContext, '{count} focusable element(s) sampled — all have a focus indicator meeting minimum area (≥{outline_px}px outline) and contrast (≥{contrast}:1) requirements.', 'フォーカス可能要素 {count} 件をサンプリングし、いずれも最小面積（アウトライン {outline_px}px 以上）とコントラスト（{contrast}:1 以上）の要件を満たすフォーカスインジケーターがありました。', { count: passes.length, outline_px: MIN_OUTLINE_WIDTH_PX, contrast: MIN_CONTRAST }),
        helpUrl: HELP_URL,
      }],
    };
  }

  const sample = violations
    .slice(0, 3)
    .map((v) => `<${v.tag}${v.id ? ` id="${v.id}"` : ''}> (${_formatIssueList(v.issues, sharedContext)})`)
    .join('; ');

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Focus indicators must have sufficient area and contrast',
      impact: 'serious',
      status: 'fail',
      reason: _t(sharedContext, '{count} focusable element(s) have focus indicators that do not fully meet WCAG 2.4.13: {sample}. Ensure outline-width ≥ {outline_px}px and contrast ≥ {contrast}:1 between the indicator colour and adjacent background.', 'フォーカス可能要素 {count} 件のフォーカスインジケーターが WCAG 2.4.13 を十分に満たしていません: {sample}。インジケーターのアウトライン幅を {outline_px}px 以上にし、隣接背景とのコントラストを {contrast}:1 以上にしてください。', { count: violations.length, sample, outline_px: MIN_OUTLINE_WIDTH_PX, contrast: MIN_CONTRAST }),
      elements: violations.map(v => ({
        html: v.html,
        element_id: v.id || null,
        target: v.target,
        tag: v.tag,
      })),
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
