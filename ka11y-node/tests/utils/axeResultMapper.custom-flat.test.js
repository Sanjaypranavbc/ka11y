'use strict';

const { mapCustomResultsFlat, mapResultsFlat } = require('../../src/utils/axeResultMapper');

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
    expect(findings.every(f => f.source === 'custom')).toBe(true);
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

  // N14: undefined fallback for unknown SC codes
  describe('N14: unknown WCAG SC codes must produce null (not undefined) for criterion_name/level', () => {
    test('unknown SC code in custom result produces criterion_name: null', () => {
      const findings = mapCustomResultsFlat([{
        successCriteriaId: '9.9.9', // non-existent SC
        rules: [{ ruleId: 'custom-unknown', status: 'fail', reason: 'test' }],
      }]);
      expect(findings).toHaveLength(1);
      // Must be null, not undefined — undefined breaks JSON serialisation in some clients
      expect(findings[0].criterion_name).toBeNull();
      expect(findings[0].level).toBeNull();
    });

    test('JSON.stringify of result with unknown SC does not throw and has no undefined values', () => {
      const findings = mapCustomResultsFlat([{
        successCriteriaId: '9.9.9',
        rules: [{ ruleId: 'custom-unknown', status: 'fail', reason: 'test' }],
      }]);
      expect(() => JSON.stringify(findings)).not.toThrow();
      const serialized = JSON.stringify(findings);
      // JSON.stringify converts undefined values to omitted keys or null in arrays;
      // verify criterion_name is explicitly null in the output, not missing
      const parsed = JSON.parse(serialized);
      expect(parsed[0]).toHaveProperty('criterion_name', null);
      expect(parsed[0]).toHaveProperty('level', null);
    });

    test('known SC code produces correct criterion_name', () => {
      const findings = mapCustomResultsFlat([{
        successCriteriaId: '1.1.1',
        rules: [{ ruleId: 'custom-alt', status: 'pass', reason: 'ok' }],
      }]);
      expect(findings[0].criterion_name).toBe('Non-text Content');
      expect(findings[0].level).toBe('A');
    });
  });
});

describe('mapResultsFlat - N14: unknown SC code in axe violations', () => {
  function makeAxeResults(overrides = {}) {
    return {
      violations: [],
      passes: [],
      incomplete: [],
      ...overrides,
    };
  }

  test('axe violation with unknown SC produces criterion_name: null (not undefined)', () => {
    const axeResults = makeAxeResults({
      violations: [{
        id:     'unknown-rule',
        tags:   ['wcag999'],  // non-existent SC tag
        impact: 'serious',
        nodes:  [{ html: '<div>', target: [], failureSummary: 'Test failure' }],
        help:   'Some help',
        helpUrl: 'https://example.com',
        description: 'Test rule',
      }],
    });
    const findings = mapResultsFlat(axeResults, 'https://example.com');
    expect(findings.length).toBeGreaterThan(0);
    expect(findings[0].criterion_name).toBeNull();
    expect(findings[0].level).toBeNull();
    // JSON serialisation must not produce undefined
    const parsed = JSON.parse(JSON.stringify(findings));
    expect(parsed[0]).toHaveProperty('criterion_name', null);
  });
});
