'use strict';

const SC = '4.1.1';
const RULE_ID = 'custom-html-parsing';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/parsing';

async function run(page) {
  const data = await page.evaluate(() => {
    // 1. Duplicate IDs — each id attribute value must be unique in the document.
    const seenIds = Object.create(null);
    const dupeIds = [];
    let totalIdCount = 0;
    document.querySelectorAll('[id]').forEach(el => {
      totalIdCount++;
      const id = el.id;
      if (seenIds[id]) dupeIds.push(id);
      else seenIds[id] = true;
    });

    // 2. B23: Duplicate `name` on non-radio/checkbox form controls.
    // Shared `name` is valid and expected for radio button groups and checkbox arrays,
    // but duplicate name values on text inputs, selects, and textareas cause ARIA label
    // resolution failures (AT reads the wrong control) and form submission ambiguity.
    const seenNames = Object.create(null);
    const dupeNames = [];
    const nameEls = document.querySelectorAll(
      'input:not([type="radio"]):not([type="checkbox"]):not([type="submit"]):not([type="button"]):not([type="reset"]):not([type="hidden"]), select, textarea'
    );
    nameEls.forEach(el => {
      const name = el.getAttribute('name');
      if (!name) return;
      if (seenNames[name]) dupeNames.push(name);
      else seenNames[name] = true;
    });

    // 3. B23: Multiple <main> or role="main" landmarks — only one is allowed.
    const mains = document.querySelectorAll('main, [role="main"]');
    const multipleMain = mains.length > 1 ? mains.length : 0;

    return {
      duplicateIds:  [...new Set(dupeIds)],
      duplicateNames: [...new Set(dupeNames)],
      multipleMain,
      totalIdCount,
    };
  });

  const { duplicateIds, duplicateNames, multipleMain, totalIdCount } = data;
  const issues = [];

  if (duplicateIds.length > 0) {
    issues.push(
      `${duplicateIds.length} duplicate id value(s) found: ${duplicateIds.slice(0, 5).map(id => `"${id}"`).join(', ')}`
    );
  }
  if (duplicateNames.length > 0) {
    issues.push(
      `${duplicateNames.length} non-radio/checkbox form control(s) share a name attribute: ${duplicateNames.slice(0, 5).map(n => `"${n}"`).join(', ')}`
    );
  }
  if (multipleMain > 0) {
    issues.push(`${multipleMain} main landmark(s) found — only one <main> or role="main" is allowed per page`);
  }

  if (issues.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: 'HTML must have no parsing errors that affect AT', impact: null, status: 'pass', reason: `${totalIdCount} element(s) with id attributes checked — all id values unique, no duplicate form control names, and no duplicate main landmarks.`, helpUrl: HELP_URL }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'HTML must have no parsing errors that affect AT',
      impact: 'critical',
      status: 'fail',
      reason: `${issues.join('; ')}. Duplicate ids and names break keyboard navigation and ARIA references; multiple main landmarks confuse screen reader document structure.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
