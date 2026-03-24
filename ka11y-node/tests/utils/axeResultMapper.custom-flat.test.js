'use strict';

const { mapCustomResultsFlat } = require('../../src/utils/axeResultMapper');

describe('mapCustomResultsFlat', () => {
  test('maps custom fail/pass/incomplete into flat finding statuses', () => {
    const customResults = [
      {
        successCriteriaId: '2.4.7',
        rules: [{
          ruleId: 'custom-focus-visible',
          impact: 'serious',
          status: 'fail',
          reason: 'No visible focus style.',
          helpUrl: 'https://example.com/focus',
        }],
      },
      {
        successCriteriaId: '3.2.6',
        rules: [{
          ruleId: 'custom-consistent-help',
          impact: 'moderate',
          status: 'incomplete',
          reason: 'Needs manual verification across pages.',
          helpUrl: 'https://example.com/help',
        }],
      },
      {
        successCriteriaId: '4.1.1',
        rules: [{
          ruleId: 'custom-html-parsing',
          impact: null,
          status: 'pass',
          reason: 'No duplicate IDs found.',
          helpUrl: 'https://example.com/html',
        }],
      },
    ];

    const findings = mapCustomResultsFlat(customResults, 'https://example.com');

    expect(findings).toHaveLength(3);
    expect(findings.map(f => f.status)).toEqual(['fail', 'needs_review', 'pass']);
    expect(findings[0].severity).toBe('high');    // serious -> high
    expect(findings[1].severity).toBe('medium');  // moderate -> medium
    expect(findings[2].severity).toBeNull();      // pass -> null
    expect(findings.every(f => f.source === 'axe')).toBe(true);
    expect(findings[0].wcag_sc).toBe('2.4.7');
    expect(findings[1].wcag_sc).toBe('3.2.6');
    expect(findings[2].wcag_sc).toBe('4.1.1');
  });

  test('handles malformed custom rule payloads safely', () => {
    const findings = mapCustomResultsFlat([
      {
        successCriteriaId: null,
        rules: [{ description: 'Missing key fields' }],
      },
    ]);

    expect(findings).toHaveLength(1);
    expect(findings[0].rule_id).toBe('custom-unknown-rule');
    expect(findings[0].status).toBe('needs_review');
    expect(findings[0].reason).toBe('Missing key fields');
  });
});
