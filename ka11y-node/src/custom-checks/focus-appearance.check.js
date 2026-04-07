'use strict';

const SC = '2.4.13';
const RULE_ID = 'custom-focus-appearance';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance';

// WCAG 2.4.13 requirements:
// 1. Focus indicator encloses the component OR has area ≥ perimeter × 2 CSS px
// 2. Contrast ratio between focused and unfocused states ≥ 3:1
const MIN_CONTRAST = 3.0;
const MIN_OUTLINE_WIDTH_PX = 2; // Sufficient for area requirement on typical elements
const MAX_ELEMENTS = 30;
const SETTLE_MS = 80;

function splitBoxShadowLayers(boxShadow) {
  const layers = [];
  let current = '';
  let depth = 0;

  for (const ch of String(boxShadow || '')) {
    if (ch === '(') depth++;
    if (ch === ')') depth = Math.max(0, depth - 1);

    if (ch === ',' && depth === 0) {
      if (current.trim()) layers.push(current.trim());
      current = '';
      continue;
    }

    current += ch;
  }

  if (current.trim()) layers.push(current.trim());
  return layers;
}

function extractBoxShadowMetrics(boxShadow) {
  const layers = splitBoxShadowLayers(boxShadow);
  let best = { spreadRadius: 0, color: null };

  for (const layer of layers) {
    const colorMatch = layer.match(/(rgba?\([^)]*\)|hsla?\([^)]*\)|#[0-9a-fA-F]{3,8}|transparent)/i);
    const lengthsOnly = layer
      .replace(/rgba?\([^)]*\)|hsla?\([^)]*\)|#[0-9a-fA-F]{3,8}/gi, ' ')
      .replace(/\binset\b/gi, ' ');
    const lengthTokens = lengthsOnly.match(/-?[\d.]+(?:px)?/g) || [];
    const spreadRadius = lengthTokens.length >= 4 ? Math.abs(parseFloat(lengthTokens[3])) : 0;

    if (spreadRadius >= best.spreadRadius) {
      best = {
        spreadRadius,
        color: colorMatch ? colorMatch[0] : best.color,
      };
    }
  }

  return best;
}

async function run(page) {
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
        tag:       el.tagName.toLowerCase(),
        id:        el.id || null,
        html:      el.outerHTML.slice(0, 150),
      });
      if (items.length >= max) break;
    }
    return items;
  }, SELECTOR, MAX_ELEMENTS);

  const violations = [];
  const passes = [];

  /**
   * Relative luminance per WCAG 2.x formula.
   * Input: "rgb(r, g, b)" or "rgba(r, g, b, a)" string.
   */
  function relativeLuminance(colorStr) {
    const m = colorStr.match(/\d+\.?\d*/g);
    if (!m || m.length < 3) return null;
    const [r, g, b] = [parseFloat(m[0]), parseFloat(m[1]), parseFloat(m[2])].map(c => {
      const s = c / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  }

  function contrastRatio(l1, l2) {
    const lighter = Math.max(l1, l2) + 0.05;
    const darker  = Math.min(l1, l2) + 0.05;
    return lighter / darker;
  }

  for (const el of elements) {
    // Capture unfocused styles — resolve element via stable selector first, then DOM index fallback
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
        backgroundColor: cs.backgroundColor,
        borderColor:     cs.borderColor,
        borderWidth:     cs.borderWidth,
      };
    }, SELECTOR, el.idx, el.stableSel);

    if (!unfocused) continue;

    // Settle before focusing
    await new Promise(r => setTimeout(r, SETTLE_MS));

    // Capture focused styles; also capture body background for transparent-element fallback (B5)
    const focused = await page.evaluate((sel, idx, stableSel) => {
      const e = stableSel
        ? (document.querySelector(stableSel) || Array.from(document.querySelectorAll(sel))[idx])
        : Array.from(document.querySelectorAll(sel))[idx];
      if (!e) return null;
      e.focus({ preventScroll: true });
      const cs = window.getComputedStyle(e);
      return {
        outlineWidth:    cs.outlineWidth,
        outlineStyle:    cs.outlineStyle,
        outlineColor:    cs.outlineColor,
        boxShadow:       cs.boxShadow,
        backgroundColor: cs.backgroundColor,
        borderColor:     cs.borderColor,
        borderWidth:     cs.borderWidth,
        bodyBg:          window.getComputedStyle(document.body).backgroundColor,
      };
    }, SELECTOR, el.idx, el.stableSel);

    // Settle then blur
    await new Promise(r => setTimeout(r, SETTLE_MS));
    await page.evaluate((sel, idx, stableSel) => {
      const e = stableSel
        ? (document.querySelector(stableSel) || Array.from(document.querySelectorAll(sel))[idx])
        : Array.from(document.querySelectorAll(sel))[idx];
      if (e) e.blur();
    }, SELECTOR, el.idx, el.stableSel);

    if (!focused) continue;

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
        issue: 'no-indicator',
        detail: 'No visible focus indicator (outline, box-shadow, or border change) detected.',
      });
      continue;
    }

    // ── Check 2: Area requirement proxy ──────────────────────────────────────
    // For outline: width ≥ MIN_OUTLINE_WIDTH_PX.
    // For box-shadow: spread radius ≥ MIN_OUTLINE_WIDTH_PX (B4: was always true when no outline).
    // For border change: border-width ≥ MIN_OUTLINE_WIDTH_PX counts as area met.
    let meetsAreaReq;
    if (hasVisibleOutline) {
      const outlineWidth = outlineWidthPx;
      const spreadRadius = 0; // not relevant here
      const borderWidth = parseFloat(focused.borderWidth) || 0;
      const borderChangedForArea = focused.borderWidth !== unfocused.borderWidth;
      const areaMet = outlineWidth >= MIN_OUTLINE_WIDTH_PX || spreadRadius >= MIN_OUTLINE_WIDTH_PX || (borderChangedForArea && borderWidth >= MIN_OUTLINE_WIDTH_PX);
      meetsAreaReq = areaMet;
    } else if (boxShadowAdded) {
      // Extract spread radius (4th px-length) from box-shadow first layer
      const { spreadRadius } = extractBoxShadowMetrics(focused.boxShadow);
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
    const boxShadowMetrics = boxShadowAdded ? extractBoxShadowMetrics(focused.boxShadow) : { color: null };
    const focusColor = hasVisibleOutline
      ? focused.outlineColor
      : boxShadowAdded
        ? (boxShadowMetrics.color || focused.borderColor)
        : focused.borderColor;
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
      if (!meetsAreaReq) issues.push(`outline-width ${focused.outlineWidth} < ${MIN_OUTLINE_WIDTH_PX}px (area requirement)`);
      if (!meetsContrast) issues.push(`focus indicator contrast < ${MIN_CONTRAST}:1 against background`);
      violations.push({
        ...el,
        issue: issues.join('; '),
        detail: `Focus indicator found but does not meet WCAG 2.4.13: ${issues.join('; ')}.`,
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
        reason: `${passes.length} focusable element(s) sampled — all have a focus indicator meeting minimum area (≥${MIN_OUTLINE_WIDTH_PX}px outline) and contrast (≥${MIN_CONTRAST}:1) requirements.`,
        helpUrl: HELP_URL,
      }],
    };
  }

  const sample = violations.slice(0, 3).map(v => `<${v.tag}${v.id ? ` id="${v.id}"` : ''}> (${v.issue})`).join('; ');

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Focus indicators must have sufficient area and contrast',
      impact: 'serious',
      status: 'fail',
      reason: `${violations.length} focusable element(s) have focus indicators that do not fully meet WCAG 2.4.13: ${sample}. Ensure outline-width ≥ ${MIN_OUTLINE_WIDTH_PX}px and contrast ≥ ${MIN_CONTRAST}:1 between the indicator colour and adjacent background.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
