'use strict';

const SC = '2.5.2';
const RULE_ID = 'custom-pointer-cancellation';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/pointer-cancellation';

// Patterns that indicate a meaningful action handler (not just style/UI feedback)
const ACTION_PATTERN = /\b(submit|navigate|redirect|window\.location|document\.location|history\.(push|replace)|fetch|xhr|ajax|open\(|close\(|modal|dialog|toggle|show|hide|dispatch|emit|call|invoke|play|pause|remove|delete|add|insert|update|save|load|send|post|put|get)\b/i;

async function run(page) {
  const violations = await page.evaluate((actionPat) => {
    const results = [];
    const actionRe = new RegExp(actionPat, 'i');

    // Bug fix: also include onpointermove — some implementations define the action
    // in the move phase and use pointerup for cancellation.
    const SELECTOR = '[onmousedown], [onpointerdown], [onpointermove]';
    const elements = Array.from(document.querySelectorAll(SELECTOR));

    for (const el of elements) {
      const mousedown    = el.getAttribute('onmousedown') || '';
      const pointerdown  = el.getAttribute('onpointerdown') || '';
      const pointermove  = el.getAttribute('onpointermove') || '';
      const downHandler  = (mousedown + ' ' + pointerdown + ' ' + pointermove).trim();

      if (!downHandler) continue;

      // Skip purely return-false or empty handlers — these are for drag init, not action execution
      const isTrivial = /^return\s+false\s*;?$/.test(downHandler.trim()) ||
                        downHandler.length < 5;
      if (isTrivial) continue;

      // Skip if the handler is clearly only visual/style manipulation
      const isVisualOnly = /^\s*(this\s*\.\s*style|event\s*\.\s*preventDefault\s*\(\s*\))\s*;?\s*$/.test(downHandler);
      if (isVisualOnly) continue;

      // Bug fix: check for meaningful action in the handler
      const isAction = actionRe.test(downHandler);

      // Bug fix: check for BOTH onmouseup/onpointerup (cancellation paths)
      const hasCancellationPath =
        el.hasAttribute('onmouseup') ||
        el.hasAttribute('onpointerup') ||
        el.hasAttribute('onclick');

      if (isAction && !hasCancellationPath) {
        results.push({
          tagName: el.tagName.toLowerCase(),
          id: el.id || null,
          html: el.outerHTML.slice(0, 150),
        });
      }
    }

    return results;
  }, ACTION_PATTERN.source);

  if (violations.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Functionality that uses a single pointer must be cancellable',
        impact: null,
        status: 'pass',
        reason: 'No elements detected activating actions solely on pointer-down without a cancellation mechanism.',
        helpUrl: HELP_URL,
      }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Functionality that uses a single pointer must be cancellable',
      impact: 'serious',
      status: 'incomplete',
      reason: `${violations.length} element(s) with action-triggering pointer-down handlers detected without matching pointer-up/click handlers. Verify these actions are cancellable by moving the pointer away before release: ${violations.slice(0, 3).map(v => `<${v.tagName}${v.id ? ` id="${v.id}"` : ''}>`).join(', ')}.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
