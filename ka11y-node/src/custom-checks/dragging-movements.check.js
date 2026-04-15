'use strict';

const {
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '2.5.7';
const RULE_ID = 'custom-dragging-movements';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements';

const DND_LIBRARY_MARKERS = [
  '[data-rbd-draggable-id]',    // react-beautiful-dnd
  '[data-dnd-kit-draggable]',   // dnd-kit
  '.sortable-item',             // Sortable.js
  '.ui-draggable',              // jQuery UI
  '[data-sortable]',            // generic sortable
  '[data-interact]',            // Interact.js
  '.gu-transit',                // Dragula
  '[data-drag-handle]',         // generic drag handle
];

// Selectors that indicate a single-pointer alternative to drag
const ALT_SELECTOR = 'button, [role="button"], a[href], input[type="button"], input[type="submit"]';

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);
  const data = await page.evaluate((libraryMarkers, altSel) => {
    const draggables = [];

    // 1. Native draggable="true" elements
    for (const el of document.querySelectorAll('[draggable="true"]')) {
      // Bug fix: look for alternatives in element AND in immediate parent/siblings
      const altInside   = !!el.querySelector(altSel);
      const altInParent = !!(el.parentElement && el.parentElement.querySelector(altSel));
      const hasAlt = altInside || altInParent;

      draggables.push({
        html: el.outerHTML.slice(0, 150),
        hasAlternative: hasAlt,
        source: 'native',
      });
    }

    // 2. Inline ondragstart without draggable attribute, and custom drag events
    for (const el of document.querySelectorAll('[ondragstart]:not([draggable="true"]), [onpointerdown], [ontouchstart]')) {
      // For pointer/touch down, check if there's an associated move event on the element or window
      // We heuristically flag elements that have BOTH down and move handlers inline.
      const hasMove = el.hasAttribute('onpointermove') || el.hasAttribute('ontouchmove') || el.hasAttribute('ondrag');
      if (!el.hasAttribute('ondragstart') && !hasMove) continue;

      const altInside   = !!el.querySelector(altSel);
      const altInParent = !!(el.parentElement && el.parentElement.querySelector(altSel));
      draggables.push({
        html: el.outerHTML.slice(0, 150),
        hasAlternative: altInside || altInParent,
        source: el.hasAttribute('ondragstart') ? 'inline-handler' : 'custom-pointer-drag',
      });
    }

    // Bug fix: library detection — only flag if actual draggable markers are present
    // Dedup fix: use a Set to prevent the same element being counted multiple times
    // when it matches more than one library marker selector.
    const _libSeen = new Set();
    const libraryDraggables = libraryMarkers
      .flatMap(sel => Array.from(document.querySelectorAll(sel)))
      .filter(el => {
        if (_libSeen.has(el)) return false;
        // Check if it's actually meant to be dragged (not just a container)
        if (el.getAttribute('draggable') === 'false') return false;
        // FP fix: for react-beautiful-dnd, skip elements with empty data-rbd-draggable-id
        // (empty value indicates a container/droppable, not an actual draggable item)
        const rbdId = el.getAttribute('data-rbd-draggable-id');
        if (rbdId !== null && rbdId.trim() === '') return false;
        _libSeen.add(el);
        return true;
      });
    const hasLibraryDnd = libraryDraggables.length > 0;

    // B15: also check alternatives for library DnD elements so that well-implemented
    // library-based drag lists (e.g. react-beautiful-dnd with "Move up/down" buttons)
    // can receive a pass verdict instead of always being marked incomplete.
    let libraryMissingAlt = 0;
    for (const el of libraryDraggables) {
      const altInside   = !!el.querySelector(altSel);
      const altInParent = !!(el.parentElement && el.parentElement.querySelector(altSel));
      if (!altInside && !altInParent) libraryMissingAlt++;
    }

    return { draggables, hasLibraryDnd, libraryCount: libraryDraggables.length, libraryMissingAlt };
  }, DND_LIBRARY_MARKERS, ALT_SELECTOR);

  const { draggables, hasLibraryDnd, libraryCount, libraryMissingAlt } = data;
  const totalCount = draggables.length + libraryCount;

  if (totalCount === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'All functionality that uses dragging movements must have a single-pointer alternative',
        impact: null,
        status: 'pass',
        reason: _t(
          sharedContext,
          'No drag-and-drop functionality detected.',
          'ドラッグアンドドロップ機能は検出されませんでした。'
        ),
        helpUrl: HELP_URL,
      }],
    };
  }

  const missingAlternative = draggables.filter(d => !d.hasAlternative);

  // B15 fix: library DnD can now pass if every library draggable has a detectable
  // single-pointer alternative nearby. Previously it always returned incomplete regardless.
  if (missingAlternative.length === 0 && (!hasLibraryDnd || libraryMissingAlt === 0)) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'All functionality that uses dragging movements must have a single-pointer alternative',
        impact: null,
        status: 'pass',
        reason: _t(
          sharedContext,
          '{total_count} draggable element(s) detected — each appears to have a single-pointer alternative nearby.',
          'ドラッグ可能な要素が {total_count} 件検出され、いずれも近くに単一ポインターで操作できる代替手段があるように見えます。',
          { total_count: totalCount },
        ),
        helpUrl: HELP_URL,
      }],
    };
  }

  const totalMissing = missingAlternative.length + libraryMissingAlt;
  const sample = missingAlternative.slice(0, 3).map(d => d.html.slice(0, 80)).join('; ');
  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'All functionality that uses dragging movements must have a single-pointer alternative',
      impact: 'serious',
      status: 'incomplete',
      reason: _t(
        sharedContext,
        '{total_count} draggable element(s) detected{library_suffix}. {missing_count} appear to lack a nearby single-pointer alternative (button/link). Verify each drag action has an accessible equivalent: {sample}.',
        'ドラッグ可能な要素が {total_count} 件検出されました{library_suffix}。このうち {missing_count} 件は近くに単一ポインターで操作できる代替手段（ボタンやリンク）がないように見えます。各ドラッグ操作にアクセシブルな同等手段があることを確認してください: {sample}。',
        {
          total_count: totalCount,
          library_suffix: hasLibraryDnd ? ` (including ${libraryCount} from D&D library)` : '',
          missing_count: totalMissing,
          sample: sample || 'D&D library elements present — verify alternatives exist',
        },
      ),
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
