'use strict';

const SC = '4.1.1';
const RULE_ID = 'custom-html-parsing';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/parsing';

async function run(page) {
  const data = await page.evaluate(() => {
    const seen = Object.create(null);
    const dupes = [];
    document.querySelectorAll('[id]').forEach(el => {
      const id = el.id;
      if (seen[id]) dupes.push(id);
      else seen[id] = true;
    });
    return { duplicateIds: [...new Set(dupes)] };
  });

  const { duplicateIds } = data;

  if (duplicateIds.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: 'HTML id attributes must be unique', impact: null, status: 'pass', reason: 'No duplicate id attributes found.', helpUrl: HELP_URL }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'HTML id attributes must be unique',
      impact: 'critical',
      status: 'fail',
      reason: `${duplicateIds.length} duplicate id attribute(s) found: ${duplicateIds.slice(0, 5).map(id => `"${id}"`).join(', ')}.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
