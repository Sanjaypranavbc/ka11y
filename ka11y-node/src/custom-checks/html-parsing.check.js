'use strict';

const SC = '4.1.1';
const RULE_ID = 'custom-html-parsing';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/parsing';

async function run(page) {
  const data = await page.evaluate(() => {
    // 4.1.1 parsing signal used here: duplicate IDs.
    // Duplicate names and landmark structure are not parsing errors, so they are
    // intentionally excluded from this rule to avoid false positives.
    const seenIds = Object.create(null);
    const dupeIds = [];
    let totalIdCount = 0;
    document.querySelectorAll('[id]').forEach(el => {
      totalIdCount++;
      const id = el.id;
      if (seenIds[id]) dupeIds.push(id);
      else seenIds[id] = true;
    });

    return {
      duplicateIds:  [...new Set(dupeIds)],
      totalIdCount,
    };
  });

  const { duplicateIds, totalIdCount } = data;
  const issues = [];

  if (duplicateIds.length > 0) {
    issues.push(
      `${duplicateIds.length} duplicate id value(s) found: ${duplicateIds.slice(0, 5).map(id => `"${id}"`).join(', ')}`
    );
  }

  if (issues.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: 'HTML must have no parsing errors that affect AT', impact: null, status: 'pass', reason: `${totalIdCount} element(s) with id attributes checked — all id values are unique.`, helpUrl: HELP_URL }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'HTML must have no parsing errors that affect AT',
      impact: 'critical',
      status: 'fail',
      reason: `${issues.join('; ')}. Duplicate ids break ARIA references and can confuse assistive technologies.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
