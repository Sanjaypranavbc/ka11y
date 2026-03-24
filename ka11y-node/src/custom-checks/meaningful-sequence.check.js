'use strict';

const SC = '1.3.2';
const RULE_ID = 'custom-meaningful-sequence';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/meaningful-sequence';
const MAX_CONTAINERS = 100;

async function run(page) {
  const violations = await page.evaluate((maxC) => {
    const results = [];
    let count = 0;

    for (const el of document.querySelectorAll('*')) {
      if (count++ > maxC) break;
      const style = window.getComputedStyle(el);
      const display = style.display;

      const isFlexOrGrid = display === 'flex' || display === 'inline-flex' ||
                           display === 'grid' || display === 'inline-grid';
      if (!isFlexOrGrid) continue;

      const children = Array.from(el.children);
      if (children.length < 2) continue;

      const orders = children.map(ch => parseInt(window.getComputedStyle(ch).order) || 0);
      if (orders.every(o => o === 0)) continue; // no reordering

      results.push({
        tagName: el.tagName.toLowerCase(),
        id: el.id || null,
        display,
        orders,
        html: el.outerHTML.slice(0, 200),
      });
    }

    return results;
  }, MAX_CONTAINERS);

  if (violations.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: 'Reading and navigation order must be programmatically determinable', impact: null, status: 'pass', reason: 'No CSS reordering (flex/grid order property) detected that diverges from DOM order.', helpUrl: HELP_URL }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Reading and navigation order must be programmatically determinable',
      impact: 'moderate',
      status: 'incomplete',
      reason: `${violations.length} flex/grid container(s) use CSS order property which may cause reading order to diverge from visual order. Verify that the DOM order matches the intended reading sequence.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run };