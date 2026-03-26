'use strict';

const SC = '4.1.1';
const RULE_ID = 'custom-html-parsing';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/parsing';

async function run(page) {
  const data = await page.evaluate(() => {
    const seen = Object.create(null);
    const dupes = [];
    let totalCount = 0;
    document.querySelectorAll('[id]').forEach(el => {
      totalCount++;
      const id = el.id;
      if (seen[id]) dupes.push(id);
      else seen[id] = true;
    });
    return { duplicateIds: [...new Set(dupes)], totalCount };
  });

  const { duplicateIds, totalCount } = data;

  if (duplicateIds.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: 'HTML id attributes must be unique', impact: null, status: 'pass', reason: `${totalCount} element(s) with id attributes checked — all id values are unique.`, helpUrl: HELP_URL }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'HTML id attributes must be unique',
      impact: 'critical',
      status: 'fail',
      reason: `${duplicateIds.length} duplicate id value(s) found across ${totalCount} id-bearing elements: ${duplicateIds.slice(0, 5).map(id => `"${id}"`).join(', ')}. Each id must be unique — duplicate ids break keyboard navigation and ARIA references.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
