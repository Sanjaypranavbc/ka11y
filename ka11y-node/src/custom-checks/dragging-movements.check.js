'use strict';

const SC = '2.5.7';
const RULE_ID = 'custom-dragging-movements';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements';

const DND_LIBRARY_MARKERS = [
  '[data-rbd-draggable-id]',    // react-beautiful-dnd
  '[data-dnd-kit-draggable]',   // dnd-kit
  '.sortable-item',             // Sortable.js
  '.ui-draggable',              // jQuery UI
  '[data-sortable]',            // generic sortable
];

// Selectors that indicate a single-pointer alternative to drag
const ALT_SELECTOR = 'button, [role="button"], a[href], input[type="button"], input[type="submit"]';

async function run(page) {
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

    // 2. Inline ondragstart without draggable attribute
    for (const el of document.querySelectorAll('[ondragstart]:not([draggable="true"])')) {
      const altInside   = !!el.querySelector(altSel);
      const altInParent = !!(el.parentElement && el.parentElement.querySelector(altSel));
      draggables.push({
        html: el.outerHTML.slice(0, 150),
        hasAlternative: altInside || altInParent,
        source: 'inline-handler',
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
        reason: 'No drag-and-drop functionality detected.',
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
        reason: `${totalCount} draggable element(s) detected — each appears to have a single-pointer alternative nearby.`,
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
      reason: `${totalCount} draggable element(s) detected${hasLibraryDnd ? ` (incl. ${libraryCount} from D&D library)` : ''}. ${totalMissing} appear to lack a nearby single-pointer alternative (button/link). Verify each drag action has an accessible equivalent: ${sample || 'D&D library elements present — verify alternatives exist'}.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
