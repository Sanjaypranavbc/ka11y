'use strict';

const {
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '4.1.1';
const RULE_ID = 'custom-html-parsing';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/parsing';

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);
  const data = await page.evaluate(() => {
    // 4.1.1 parsing signal used here: duplicate IDs.
    // Duplicate names and landmark structure are not parsing errors, so they are
    // intentionally excluded from this rule to avoid false positives.
    const seenIds = Object.create(null);
    const dupeIds = [];
    const elements = [];
    let totalIdCount = 0;
    document.querySelectorAll('[id]').forEach(el => {
      totalIdCount++;
      const id = el.id;
      if (seenIds[id]) {
        dupeIds.push(id);
        elements.push({
          html: el.outerHTML.slice(0, 150),
          element_id: id,
          target: [`#${CSS.escape(id)}`],
          tag: el.tagName.toUpperCase(),
        });
      } else {
        seenIds[id] = true;
      }
    });

    // Broken ARIA reference check
    const brokenRefs = [];
    for (const el of document.querySelectorAll('[aria-labelledby], [aria-describedby], [aria-controls], [aria-owns]')) {
      for (const attr of ['aria-labelledby', 'aria-describedby', 'aria-controls', 'aria-owns']) {
        const val = el.getAttribute(attr);
        if (!val) continue;
        for (const id of val.split(/\s+/).filter(Boolean)) {
          if (!document.getElementById(id)) {
            brokenRefs.push({ attr, id, html: el.outerHTML.slice(0, 100) });
            elements.push({
              html: el.outerHTML.slice(0, 150),
              element_id: el.id || null,
              target: el.id ? [`#${CSS.escape(el.id)}`] : [el.tagName.toLowerCase()],
              tag: el.tagName.toUpperCase(),
            });
          }
        }
      }
    }

    // Orphaned label[for] check
    const orphanedLabels = [];
    for (const label of document.querySelectorAll('label[for]')) {
      const forId = label.getAttribute('for');
      if (forId && !document.getElementById(forId)) {
        orphanedLabels.push({ for: forId, html: label.outerHTML.slice(0, 100) });
        elements.push({
          html: label.outerHTML.slice(0, 150),
          element_id: label.id || null,
          target: label.id ? [`#${CSS.escape(label.id)}`] : ['label'],
          tag: 'LABEL',
        });
      }
    }

    return {
      duplicateIds:  [...new Set(dupeIds)],
      totalIdCount,
      brokenRefs,
      orphanedLabels,
      elements,
    };
  });

  const { duplicateIds, totalIdCount, brokenRefs, orphanedLabels, elements } = data;
  const issues = [];

  if (duplicateIds.length > 0) {
    issues.push(
      `${duplicateIds.length} duplicate id value(s) found: ${duplicateIds.slice(0, 5).map(id => `"${id}"`).join(', ')}`
    );
  }

  if (brokenRefs && brokenRefs.length > 0) {
    const sample = brokenRefs.slice(0, 3).map(r => `${r.attr}="${r.id}"`).join(', ');
    issues.push(
      `${brokenRefs.length} broken ARIA reference(s) — referenced id(s) not found in DOM: ${sample}`
    );
  }

  if (orphanedLabels && orphanedLabels.length > 0) {
    const sample = orphanedLabels.slice(0, 3).map(l => `for="${l.for}"`).join(', ');
    issues.push(
      `${orphanedLabels.length} <label for="..."> element(s) reference a non-existent id: ${sample}`
    );
  }

  if (issues.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: 'HTML must have no parsing errors that affect AT', impact: null, status: 'pass', reason: _t(sharedContext, '{count} element(s) with id attributes checked — all id values are unique, no broken ARIA references, and no orphaned label[for] elements detected.', 'id 属性を持つ要素 {count} 件を確認し、重複 ID、壊れた ARIA 参照、孤立した label[for] 要素は検出されませんでした。', { count: totalIdCount }), helpUrl: HELP_URL }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'HTML must have no parsing errors that affect AT',
      impact: 'critical',
      status: 'fail',
      reason: _t(
        sharedContext,
        '{issues}. Duplicate ids break ARIA references and can confuse assistive technologies.',
        '{issues}。重複した id は ARIA 参照を壊し、支援技術の解釈を妨げる可能性があります。',
        { issues: issues.join('; ') },
      ),
      elements: elements,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
