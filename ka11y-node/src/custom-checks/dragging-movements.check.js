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
    const libraryDraggables = libraryMarkers
      .flatMap(sel => Array.from(document.querySelectorAll(sel)))
      .filter(el => {
        // Check if it's actually meant to be dragged (not just a container)
        return el.getAttribute('draggable') !== 'false';
      });
    const hasLibraryDnd = libraryDraggables.length > 0;

    return { draggables, hasLibraryDnd, libraryCount: libraryDraggables.length };
  }, DND_LIBRARY_MARKERS, ALT_SELECTOR);

  const { draggables, hasLibraryDnd, libraryCount } = data;
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

  // Bug fix: library-only case → always incomplete (can't verify alt from static DOM)
  // draggables with alternatives → pass, without → incomplete
  if (missingAlternative.length === 0 && !hasLibraryDnd) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'All functionality that uses dragging movements must have a single-pointer alternative',
        impact: null,
        status: 'pass',
        reason: `${draggables.length} draggable element(s) detected — each appears to have a single-pointer alternative nearby.`,
        helpUrl: HELP_URL,
      }],
    };
  }

  const sample = missingAlternative.slice(0, 3).map(d => d.html.slice(0, 80)).join('; ');
  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'All functionality that uses dragging movements must have a single-pointer alternative',
      impact: 'serious',
      status: 'incomplete',
      reason: `${totalCount} draggable element(s) detected${hasLibraryDnd ? ` (incl. ${libraryCount} from D&D library)` : ''}. ${missingAlternative.length} appear to lack a nearby single-pointer alternative (button/link). Verify each drag action has an accessible equivalent: ${sample || 'D&D library elements present — verify alternatives exist'}.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
