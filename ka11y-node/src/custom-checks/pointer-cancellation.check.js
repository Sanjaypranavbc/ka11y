'use strict';

const SC = '2.5.2';
const RULE_ID = 'custom-pointer-cancellation';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/pointer-cancellation';

// Patterns that indicate a meaningful action handler (not just style/UI feedback)
const ACTION_PATTERN = /\b(submit|navigate|redirect|window\.location|document\.location|history\.(push|replace)|fetch|xhr|ajax|open\(|close\(|modal|dialog|toggle|show|hide|dispatch|emit|call|invoke|play|pause|remove|delete|add|insert|update|save|load|send|post|put|get)\b|送信|購入|削除|確認|登録|申込|注文|クリック/i;

async function run(page) {
  const violations = await page.evaluate((actionPat) => {
    const results = [];
    const actionRe = new RegExp(actionPat, 'i');

    // Bug fix: also include onpointermove — some implementations define the action
    // in the move phase and use pointerup for cancellation.
    // Also include ontouchstart — touch-based down events that may trigger actions without cancellation.
    const SELECTOR = '[onmousedown], [onpointerdown], [onpointermove], [ontouchstart]';
    const elements = Array.from(document.querySelectorAll(SELECTOR));

    for (const el of elements) {
      const mousedown    = el.getAttribute('onmousedown') || '';
      const pointerdown  = el.getAttribute('onpointerdown') || '';
      const pointermove  = el.getAttribute('onpointermove') || '';
      const touchstart   = el.getAttribute('ontouchstart') || '';
      const downHandler  = (mousedown + ' ' + pointerdown + ' ' + pointermove + ' ' + touchstart).trim();

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
      // Also check ontouchend as cancellation path for touch events
      const hasCancellationPath =
        el.hasAttribute('onmouseup') ||
        el.hasAttribute('onpointerup') ||
        el.hasAttribute('onclick') ||
        el.hasAttribute('ontouchend');

      if (isAction && !hasCancellationPath) {
        results.push({
          tagName: el.tagName.toLowerCase(),
          id: el.id || null,
          html: el.outerHTML.slice(0, 150),
        });
      }
    }

    return { results, totalChecked: elements.length };
  }, ACTION_PATTERN.source);

  if (violations.results.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Functionality that uses a single pointer must be cancellable',
        impact: null,
        status: 'pass',
        reason: `${violations.totalChecked} element(s) with pointer-down handlers checked — all action-triggering handlers have a corresponding pointer-up or click event, allowing cancellation by moving the pointer away before release.`,
        helpUrl: HELP_URL,
      }],
    };
  }

  const violations2 = violations.results;

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Functionality that uses a single pointer must be cancellable',
      impact: 'serious',
      status: 'incomplete',
      reason: `${violations2.length} of ${violations.totalChecked} element(s) have action-triggering pointer-down handlers without a matching pointer-up or click handler. Actions fire immediately on press with no way to cancel — add onpointerup/onclick or use the up-event for activation: ${violations2.slice(0, 3).map(v => `<${v.tagName}${v.id ? ` id="${v.id}"` : ''}>`).join(', ')}.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
