/**
 * @fileoverview Selector banks for WCAG 2.5.1 Pointer Gestures audit.
 *
 * Japanese strings are expressed via unicode escapes throughout so the source
 * file is safe in any locale or editor that may mangle multi-byte characters.
 *
 * Unicode reference:
 *   スライダー  = slider         カルーセル = carousel
 *   ドラッグ    = drag            スワイプ   = swipe
 *   タッチ      = touch           ジェスチャー = gesture
 *   フリック    = flick           描画       = drawing
 *   手書き      = handwriting     サイン     = signature
 *   並び替え    = sort/reorder
 */

/**
 * @typedef {Object} SelectorBank
 * @property {string[]} carousels            - Carousel / slider widget selectors
 * @property {string[]} draggable            - Drag-and-drop container selectors
 * @property {string[]} mapEmbeds            - Touch-only map embed selectors
 * @property {string[]} touchGestureWidgets  - Custom touch/gesture widget selectors
 * @property {string[]} pathBasedInteractions - Draw / signature / scrub selectors
 */

/* ── English selector bank ─────────────────────────────────────────────── */

/** @type {SelectorBank} */
const _en = {
  carousels: [
    '.swiper-container',
    '.swiper-wrapper',
    '.swiper',
    '[data-swiper]',
    '.slick-slider',
    '.slick-list',
    '.slick-track',
    '.flickity-viewport',
    '.flickity-slider',
    '.flickity-enabled',
    '.glide__track',
    '.glide',
    '[data-glide-el]',
    '.owl-carousel',
    '.owl-stage',
    '.splide__track',
    '.splide',
    '.splide__list',
    '[data-ride="carousel"]',
    '.carousel-inner',
    '.carousel',
    '.slider',
    '.slideshow',
    '[data-carousel]',
    '[data-slider]',
    '.embla__viewport',
    '.embla',
  ],

  draggable: [
    '[draggable="true"]',
    '.sortable-container',
    '.ui-sortable',
    '.ui-draggable',
    '[data-drag]',
    '[data-sortable]',
    '.drag-handle',
    '.draggable',
    '[data-rbd-draggable-id]',
    '[data-rbd-drag-handle-draggable-id]',
    '[data-dnd-kit-draggable]',
    '.sortable-ghost',
    '.sortable-chosen',
    '.sortable-drag',
    '.sortable-item',
    '.ui-sortable-handle',
    '.ui-droppable',
    '[data-interact]',
    '.gu-transit',
    '.gu-mirror',
    '[data-drag-handle]',
    '[ondragstart]',
  ],

  mapEmbeds: [
    '.leaflet-container',
    '.mapboxgl-map',
    '.gm-style',
    'iframe[src*="maps.google"]',
    'iframe[src*="google.com/maps"]',
    'iframe[src*="maps.googleapis"]',
    'iframe[src*="openstreetmap"]',
    '.leaflet-map-pane',
    '.mapboxgl-canvas',
    'iframe[src*="mapbox"]',
    '#map',
    '[id^="map-"]',
    '[class*="map-container"]',
    '#map canvas',
  ],

  touchGestureWidgets: [
    '[data-gesture]',
    '[data-swipe]',
    '[data-touch]',
    '[data-pan]',
    '[data-pinch]',
    '[data-rotate]',
    '[data-direction]',
    '[data-swipe-left]',
    '[data-swipe-right]',
    '[data-drag]',
    '[data-flick]',
    '[data-gesture-target]',
    '[data-swipe-target]',
  ],

  pathBasedInteractions: [
    '[data-draw]',
    '[data-path]',
    'canvas[data-interactive]',
    '.signature-pad',
    '.drawing-canvas',
    '[data-scrub]',
    '[data-signature]',
    '.canvas-draw',
    '[data-handwriting]',
  ],
};

/* ── Japanese selector bank ────────────────────────────────────────────── */

/** @type {SelectorBank} */
const _ja = {
  carousels: [
    // スライダー = スライダー
    '.スライダー',
    '[class*="スライダー"]',
    // カルーセル = カルーセル
    '.カルーセル',
    '[class*="カルーセル"]',
    // スライドショー = スライドショー
    '.スライドショー',
    // [data-スワイプ] = data-スワイプ
    '[data-スワイプ]',
    '.slider-wrap',
    '.slide-area',
    '.swiper',
    '.swiper-container',
    '.slick-slider',
    '.flickity-viewport',
    '.splide',
    '[data-slider]',
    '[data-carousel]',
  ],

  draggable: [
    '[draggable="true"]',
    // [data-ドラッグ] = data-ドラッグ
    '[data-ドラッグ]',
    // .ドラッグ = .ドラッグ
    '.ドラッグ',
    '[class*="ドラッグ"]',
    // .並び替え = .並び替え
    '.並び替え',
    '[data-rbd-draggable-id]',
    '.sortable-ghost',
    '.sortable-chosen',
    '[data-sortable]',
    '.ui-draggable',
    '[ondragstart]',
  ],

  mapEmbeds: [
    'iframe[src*="google.com/maps"]',
    'iframe[src*="maps.google"]',
    'iframe[src*="map.yahoo.co.jp"]',
    // [id*="yahoo-map"]
    '[id*="yahoo-map"]',
    'iframe[src*="zenrin.co.jp"]',
    'iframe[src*="zmaps"]',
    'iframe[src*="mapion.co.jp"]',
    // .ヤフーマップ = .ヤフーマップ
    '.ヤフーマップ',
    '.leaflet-container',
    '.leaflet-map-pane',
    '.mapboxgl-canvas',
    'iframe[src*="mapbox"]',
    '#map',
    '[id^="map-"]',
  ],

  touchGestureWidgets: [
    '[data-gesture]',
    '[data-swipe]',
    '[data-drag]',
    // [data-スワイプ] = data-スワイプ
    '[data-スワイプ]',
    // [data-タッチ] = data-タッチ
    '[data-タッチ]',
    // [data-ジェスチャー] = data-ジェスチャー
    '[data-ジェスチャー]',
    // [data-フリック] = data-フリック
    '[data-フリック]',
    // [data-ピンチ] = data-ピンチ
    '[data-ピンチ]',
    '[data-gesture-target]',
  ],

  pathBasedInteractions: [
    '[data-draw]',
    '[data-path]',
    'canvas[data-interactive]',
    '.signature-pad',
    '.drawing-canvas',
    '[data-scrub]',
    // [data-描画] = data-描画
    '[data-描画]',
    // .手書き = .手書き
    '.手書き',
    // .サイン = .サイン
    '.サイン',
  ],
};

/* ── Shared Attribute Bank ──────────────────────────────────────────────── */

const gestureAttrs = [
  'data-gesture', 'data-swipe', 'data-touch', 'data-pan', 'data-pinch',
  'data-rotate', 'data-direction', 'data-flick', 'data-draw', 'data-path',
  'data-scrub', 'data-signature',
  // Japanese attribute names
  'data-スワイプ',
  'data-タッチ',
  'data-ジェスチャー',
  'data-フリック',
  'data-描画',
  'data-ドラッグ',
];

/* ── Unified Selector Constants ─────────────────────────────────────────── */

/**
 * Selector for alternative interactive elements (buttons, links, button-likes).
 * Single source of truth — consumed by axe-rule-pointer-gestures.js and
 * escape-hatch-checker.js to avoid drift.
 * @type {string}
 */
const ALT_SEL = 'button, [role="button"], a[href], input[type="button"], input[type="submit"]';

/**
 * Comma-joined CSS selector string for all gesture-related elements
 * (EN + JA banks, deduped, with library prefixes filtered out).
 * @type {string}
 */
const _allCombinedSelectors = [...Object.values(_en), ...Object.values(_ja)]
  .flat()
  .filter(s => typeof s === 'string'
    && !s.startsWith('Hammer')
    && !s.startsWith('interact')
    && !s.startsWith('ZingTouch'));
const ALL_GESTURE_SELECTORS_STRING = [...new Set(_allCombinedSelectors)].join(', ');

/* ── Public API ─────────────────────────────────────────────────────────── */

/**
 * Returns the CSS selector bank for the given BCP 47 language tag.
 * Japanese pages (`lang` starting with "ja") receive English selectors merged
 * with their Japanese equivalents; all other languages get English only.
 *
 * @param {string} lang - BCP 47 language tag (e.g. "en", "ja", "ja-JP")
 * @returns {SelectorBank}
 */
function getSelectorBank(lang = 'en') {
  const isJapanese = String(lang).toLowerCase().startsWith('ja');

  if (!isJapanese) return { ..._en };

  return {
    carousels:            [..._en.carousels,            ..._ja.carousels],
    draggable:            [..._en.draggable,            ..._ja.draggable],
    mapEmbeds:            [..._en.mapEmbeds,            ..._ja.mapEmbeds],
    touchGestureWidgets:  [..._en.touchGestureWidgets,  ..._ja.touchGestureWidgets],
    pathBasedInteractions:[..._en.pathBasedInteractions,..._ja.pathBasedInteractions],
  };
}

/* Backward-compat named exports (used by gesture-listener-detector.js, axe rule, etc.) */
const enSelectors = _en;
const jaSelectors = _ja;
module.exports = {
  enSelectors,
  jaSelectors,
  getSelectorBank,
  gestureAttrs,
  ALT_SEL,
  ALL_GESTURE_SELECTORS_STRING,
};
