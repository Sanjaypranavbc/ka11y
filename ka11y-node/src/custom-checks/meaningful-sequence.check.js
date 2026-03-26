'use strict';

const SC = '1.3.2';
const RULE_ID = 'custom-meaningful-sequence';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/meaningful-sequence';
// MAX_CONTAINERS limits how many flex/grid containers are inspected (not total elements).
const MAX_CONTAINERS = 500;

async function run(page) {
  const violations = await page.evaluate((maxC) => {
    const results = [];
    let containerCount = 0;

    for (const el of document.querySelectorAll('*')) {
      const style = window.getComputedStyle(el);
      const display = style.display;

      const isFlex = display === 'flex' || display === 'inline-flex';
      const isGrid = display === 'grid' || display === 'inline-grid';
      if (!isFlex && !isGrid) continue;
      // Only increment the container counter for actual flex/grid containers
      if (containerCount++ >= maxC) break;

      const children = Array.from(el.children).filter(ch => {
        // Only consider visible children — exclude all common hiding patterns
        const cs = window.getComputedStyle(ch);
        return cs.display !== 'none' &&
               cs.visibility !== 'hidden' &&
               cs.visibility !== 'collapse' &&
               cs.opacity !== '0';
      });
      if (children.length < 2) continue;

      // Bug fix 1: detect flex-direction reversal (visually reverses DOM order)
      const flexDir = style.flexDirection || '';
      const isReversed = flexDir === 'row-reverse' || flexDir === 'column-reverse';

      // B13: RTL layout exemption — row-reverse is the CORRECT implementation for
      // Arabic, Hebrew, Persian, and Urdu sites. Flag it only when the document/element
      // writing direction is LTR. column-reverse is still flagged regardless of directionality.
      if (flexDir === 'row-reverse') {
        const docDir  = (document.documentElement.getAttribute('dir') || '').toLowerCase();
        const docLang = document.documentElement.getAttribute('lang') || '';
        const isRtlDoc = docDir === 'rtl' ||
          /^(ar|he|fa|ur|yi|arc|ckb)\b/i.test(docLang);
        const isRtlEl  = !!el.closest('[dir="rtl"]');
        if (isRtlDoc || isRtlEl) continue; // correct usage for RTL — skip
      }

      // Bug fix 2: detect CSS order property — use parseInt with radix 10
      // Note: parseInt('auto', 10) = NaN; we treat NaN as 0 (default order)
      const orders = children.map(ch => {
        const o = parseInt(window.getComputedStyle(ch).order, 10);
        return isNaN(o) ? 0 : o;
      });
      const hasExplicitOrder = !orders.every(o => o === 0);

      // Check if the order property actually reorders relative to DOM position
      // (ascending order = same as DOM → no reordering issue)
      let orderReorders = false;
      if (hasExplicitOrder) {
        const domIndices = orders.map((_, i) => i);
        const visualOrder = [...orders.keys()].sort((a, b) => orders[a] - orders[b]);
        orderReorders = visualOrder.some((vi, di) => vi !== domIndices[di]);
      }

      if (!isReversed && !orderReorders) continue;

      results.push({
        tagName: el.tagName.toLowerCase(),
        id: el.id || null,
        display,
        flexDir: flexDir || null,
        orders: hasExplicitOrder ? orders : null,
        reason: isReversed
          ? `flex-direction: ${flexDir} reverses DOM order visually`
          : `CSS order property reorders children from DOM sequence (orders: [${orders.join(', ')}])`,
        html: el.outerHTML.slice(0, 200),
      });
    }

    return results;
  }, MAX_CONTAINERS);

  if (violations.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: 'Reading and navigation order must be programmatically determinable', impact: null, status: 'pass', reason: `Up to ${MAX_CONTAINERS} flex/grid containers inspected — no CSS reordering (flex-direction reverse or order property) found that diverges from DOM order.`, helpUrl: HELP_URL }],
    };
  }

  const sample = violations.slice(0, 3).map(v => v.reason).join('; ');

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Reading and navigation order must be programmatically determinable',
      impact: 'moderate',
      status: 'incomplete',
      reason: `${violations.length} flex/grid container(s) visually reorder content relative to DOM order. Verify the DOM order matches the intended reading sequence. Details: ${sample}.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
