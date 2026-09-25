'use strict';

const { mapCustomResultsFlat } = require('../../src/utils/axeResultMapper');

describe('mapCustomResultsFlat — WCAG technique ids', () => {
  const page = 'https://example.com/';

  test('lifts each issue technique onto the finding and off the element', () => {
    const customResults = [{
      successCriteriaId: '2.4.2',
      rules: [{
        ruleId: 'custom-page-titled',
        impact: 'serious',
        status: 'fail',
        reason: 'Page title does not describe the page',
        elements: [
          { type: 'generic-title', technique: 'G88', target: 'title', snippet: '<title>Home</title>', detail: 'generic' },
          { type: 'site-name-missing', technique: ' G127 ', target: 'title', snippet: '<title>Home</title>', detail: 'no site' },
          { type: 'untagged', target: 'title', snippet: '<title>Home</title>', detail: 'no technique' },
        ],
      }],
    }];
    const findings = mapCustomResultsFlat(customResults, page, 'en');
    expect(findings.map(f => f.technique_id)).toEqual(['G88', 'G127', null]);
    expect(findings.map(f => f.issue_type)).toEqual(['generic-title', 'site-name-missing', 'untagged']);
    for (const f of findings) {
      expect(f.element).not.toHaveProperty('technique');
      expect(f.element).not.toHaveProperty('issue_type');
      expect(f.source).toBe('custom');
    }
  });

  test('falls back to a rule-level technique, else null', () => {
    const customResults = [{
      successCriteriaId: '2.4.2',
      rules: [
        { ruleId: 'custom-page-titled', status: 'pass', reason: 'ok', technique: 'G88' },
        { ruleId: 'custom-page-titled', status: 'pass', reason: 'ok' },
      ],
    }];
    const [tagged, untagged] = mapCustomResultsFlat(customResults, page, 'en');
    expect(tagged.technique_id).toBe('G88');
    expect(untagged.technique_id).toBeNull();
    expect(untagged.issue_type).toBeNull();
  });
});
