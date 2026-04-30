/**
 * @fileoverview axe-core custom rule for WCAG 2.5.1 Pointer Gestures.
 *
 * The evaluate function runs inside the browser via axe-core's serialisation
 * pipeline.  Rules:
 *   • No import statements or Node.js APIs inside the evaluate function body.
 *   • All input data is threaded through axe's `options` object.
 *   • The function must be reference-free so it can be stringified and
 *     reconstructed with `new Function()`.
 */

import { enSelectors, jaSelectors } from './multilingual-selectors.js';

/* ── Comma-joined selector string (all categories, EN + JA banks) ───────── */
const _allSelectors = [
  ...Object.values(enSelectors),
  ...Object.values(jaSelectors),
]
  .flat()
  .filter(s => typeof s === 'string' && !s.startsWith('Hammer') && !s.startsWith('interact') && !s.startsWith('ZingTouch'));

const ALL_SELECTORS_STRING = [...new Set(_allSelectors)].join(', ');

/* ── Check evaluate function (must be self-contained) ───────────────────── */

/**
 * axe-core check evaluate body.
 * Runs inside the browser with `this` bound to the check context.
 *
 * @param {Element} node    - DOM element matched by the rule selector
 * @param {Object}  options - Check options set via axe.configure()
 * @returns {boolean} false = violation found; true = passed
 */
function _evaluateBody(node, options) {
  const gestureAttrs = [
    'data-gesture', 'data-swipe', 'data-touch', 'data-pan', 'data-pinch',
    'data-rotate', 'data-direction', 'data-flick', 'data-draw', 'data-path',
    'data-scrub', 'data-signature',
    // Japanese attribute names
    'data-スワイプ',  // data-スワイプ
    'data-タッチ',        // data-タッチ
    'data-ジェスチャー', // data-ジェスチャー
    'data-フリック', // data-フリック
    'data-描画',              // data-描画
    'data-ドラッグ', // data-ドラッグ
  ];

  const hasGestureAttr = gestureAttrs.some(attr => node.hasAttribute(attr));
  const isDraggable    = node.getAttribute('draggable') === 'true';

  if (!hasGestureAttr && !isDraggable) return true;

  /* Check for single-pointer alternatives */
  const hasClickHandler = typeof node.onclick === 'function' || !!node.getAttribute('onclick');
  const hasFocusable    = node.tabIndex >= 0;

  const parent = node.parentElement;
  const ALT_SEL = 'button, [role="button"], a[href], input[type="button"], input[type="submit"]';
  const hasButtonSibling = !!(parent && Array.from(parent.children)
    .some(c => c !== node && c.matches && c.matches(ALT_SEL)));
  const hasInternalBtn = !!(node.querySelector && node.querySelector(ALT_SEL));

  if (hasClickHandler || hasFocusable || hasButtonSibling || hasInternalBtn) return true;

  /* Violation — store data for result extraction */
  this.data({
    gestureAttr:  gestureAttrs.find(a => node.hasAttribute(a)) || (isDraggable ? 'draggable' : null),
    isDraggable,
    element:      (node.outerHTML || '').slice(0, 200),
  });
  return false;
}

/* ── Exported rule and check objects ───────────────────────────────────── */

/** @type {Object} axe-core check definition */
export const pointerGestureCheck = {
  id:       'pointer-gestures-2-5-1-check',
  evaluate: _evaluateBody,
  metadata: {
    impact: 'serious',
    messages: {
      pass: 'Element provides a single-pointer alternative for gesture-based interaction',
      fail: 'Element uses gesture-based interaction with no single-pointer alternative detected',
    },
  },
};

/**
 * @type {Object} axe-core rule definition for WCAG 2.5.1 Pointer Gestures.
 * Pass to axe.configure({ rules: [pointerGestureRule] }).
 */
export const pointerGestureRule = {
  id:       'pointer-gestures-2-5-1',
  selector: ALL_SELECTORS_STRING,
  tags:     ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa', 'wcag251', 'pointer-gestures'],
  any:      ['pointer-gestures-2-5-1-check'],
  metadata: {
    description: 'Ensures all functionality using multipoint or path-based gestures has a single-pointer alternative',
    help:        'Provide single-pointer alternatives for all gesture-based interactions',
    helpUrl:     'https://www.w3.org/WAI/WCAG22/Understanding/pointer-gestures',
  },
};

/**
 * Registers the custom pointer-gesture rule and check with an axe-core instance.
 *
 * @param {Object} axeInstance - The axe-core object (window.axe inside a browser evaluate)
 * @returns {void}
 */
export function registerPointerGestureRule(axeInstance) {
  axeInstance.configure({
    checks: [pointerGestureCheck],
    rules:  [pointerGestureRule],
  });
}

/* ── Backward-compat aliases (used by existing index.js and spec file) ─── */
export const pointerGesturesRule  = pointerGestureRule;
export const pointerGesturesCheck = pointerGestureCheck;
