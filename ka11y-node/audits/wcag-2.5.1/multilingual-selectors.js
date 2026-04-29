/**
 * @fileoverview Selector banks for WCAG 2.5.1 Pointer Gestures audit.
 * Japanese strings are expressed exclusively through unicode escapes so the
 * source file is safe in any locale or editor that may mangle multi-byte
 * characters.
 *
 * Unicode reference:
 *   スライダー = スライダー  (slider)
 *   カルーセル = カルーセル  (carousel)
 *   回転バナー = 回転バナー  (rotating banner)
 *   ドラッグ       = ドラッグ    (drag)
 *   スワイプ       = スワイプ    (swipe)
 *   タッチ             = タッチ      (touch)
 *   ピンチ             = ピンチ      (pinch)
 *   パン                   = パン        (pan)
 */

/**
 * Selector bank for English-language pages.
 *
 * @typedef {Object} SelectorBank
 * @property {string[]} carousels         - Carousel / slider widget selectors
 * @property {string[]} dragDrop          - Drag-and-drop container selectors
 * @property {string[]} mapEmbeds         - Touch-only map embed selectors
 * @property {string[]} gestureWidgets    - Custom gesture widget selectors
 * @property {string[]} gestureLibraryGlobals - Window global names injected by gesture libraries
 */

/** @type {SelectorBank} */
export const enSelectors = {
  carousels: [
    // Swiper.js
    '.swiper',
    '.swiper-container',
    '.swiper-wrapper',
    '[data-swiper]',
    // Slick
    '.slick-slider',
    '.slick-list',
    '.slick-track',
    // Flickity
    '.flickity-viewport',
    '.flickity-slider',
    '.flickity-enabled',
    // Glide.js
    '.glide',
    '.glide__track',
    '[data-glide-el]',
    // Owl Carousel
    '.owl-carousel',
    '.owl-stage',
    '.owl-stage-outer',
    // Splide
    '.splide',
    '.splide__track',
    '.splide__list',
    // Generic patterns
    '[data-carousel]',
    '[data-slider]',
    '[data-ride="carousel"]',
    '.carousel',
    '.slider',
    '.slideshow',
  ],

  dragDrop: [
    // Native HTML5
    '[draggable="true"]',
    // react-beautiful-dnd
    '[data-rbd-draggable-id]',
    '[data-rbd-drag-handle-draggable-id]',
    // dnd-kit
    '[data-dnd-kit-draggable]',
    // Sortable.js
    '.sortable-ghost',
    '.sortable-chosen',
    '.sortable-drag',
    '[data-sortable]',
    '.sortable-item',
    // jQuery UI
    '.ui-draggable',
    '.ui-sortable-handle',
    '.ui-droppable',
    // Interact.js
    '[data-interact]',
    // Dragula
    '.gu-transit',
    '.gu-mirror',
    // Generic
    '[data-drag-handle]',
    '[ondragstart]',
  ],

  mapEmbeds: [
    // Google Maps
    'iframe[src*="google.com/maps"]',
    'iframe[src*="maps.google"]',
    'iframe[src*="maps.googleapis"]',
    '.gm-style',
    '#map canvas',
    // Leaflet
    '.leaflet-container',
    '.leaflet-map-pane',
    // Mapbox
    '.mapboxgl-canvas',
    '.mapboxgl-map',
    'iframe[src*="mapbox"]',
    // OpenStreetMap
    'iframe[src*="openstreetmap.org"]',
    // Generic map containers
    '#map',
    '[id^="map-"]',
    '[class*="map-container"]',
  ],

  gestureWidgets: [
    '[data-gesture]',
    '[data-swipe]',
    '[data-swipe-left]',
    '[data-swipe-right]',
    '[data-drag]',
    '[data-touch]',
    '[data-pinch]',
    '[data-rotate]',
    '[data-pan]',
    '[data-flick]',
    '[data-gesture-target]',
    '[data-swipe-target]',
  ],

  // These are window global variable names, not CSS selectors.
  // Used to detect gesture library injection at runtime.
  gestureLibraryGlobals: [
    'Hammer',      // Hammer.js
    'interact',    // interact.js
    'ZingTouch',   // ZingTouch
  ],
};

/**
 * Selector bank for Japanese-language pages (lang="ja").
 * Japanese class/attribute names are unicode-escaped throughout.
 *
 * @type {SelectorBank}
 */
export const jaSelectors = {
  carousels: [
    // スライダー = スライダー
    '.スライダー',
    '[class*="スライダー"]',
    // カルーセル = カルーセル
    '.カルーセル',
    '[class*="カルーセル"]',
    // 回転バナー = 回転バナー
    '.回転バナー',
    '[class*="バナー"]',
    // Library classes also used in Japanese sites
    '.swiper',
    '.swiper-container',
    '.slick-slider',
    '.flickity-viewport',
    '.splide',
    '[data-slider]',
    '[data-carousel]',
  ],

  dragDrop: [
    '[draggable="true"]',
    // ドラッグ = ドラッグ (drag)
    '[class*="ドラッグ"]',
    // data-ドラッグ attribute pattern
    '[data-ドラッグ]',
    '[data-rbd-draggable-id]',
    '.sortable-ghost',
    '.sortable-chosen',
    '[data-sortable]',
    '.ui-draggable',
    '[ondragstart]',
  ],

  mapEmbeds: [
    // Google Maps (global)
    'iframe[src*="google.com/maps"]',
    'iframe[src*="maps.google"]',
    // Yahoo Maps Japan
    'iframe[src*="map.yahoo.co.jp"]',
    '[id*="yahoo-map"]',
    // Zenrin Maps (major Japanese map provider)
    'iframe[src*="zenrin.co.jp"]',
    'iframe[src*="zmaps"]',
    'iframe[src*="z-maps"]',
    // Mapion (Japanese map service)
    'iframe[src*="mapion.co.jp"]',
    // Leaflet (widely used in Japan)
    '.leaflet-container',
    '.leaflet-map-pane',
    // Mapbox
    '.mapboxgl-canvas',
    'iframe[src*="mapbox"]',
    // Generic
    '#map',
    '[id^="map-"]',
  ],

  gestureWidgets: [
    '[data-gesture]',
    '[data-swipe]',
    '[data-drag]',
    // スワイプ = スワイプ (swipe)
    '[data-スワイプ]',
    // タッチ = タッチ (touch)
    '[data-タッチ]',
    // ピンチ = ピンチ (pinch)
    '[data-ピンチ]',
    // パン = パン (pan)
    '[data-パン]',
    '[data-gesture-target]',
  ],

  gestureLibraryGlobals: [
    'Hammer',
    'interact',
    'ZingTouch',
  ],
};
