'use strict';

const {
  formatSuccessCriterion,
  mapCustomResultsFlat,
  mapResultsFlat,
} = require('../../src/utils/axeResultMapper');

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
    expect(findings[2].suggested_fix).toBeNull();
  });

  test('normalizes custom status aliases into fail/pass/needs_review', () => {
    const findings = mapCustomResultsFlat([
      {
        successCriteriaId: '4.1.2',
        rules: [{ ruleId: 'custom-a', status: 'FAILED', reason: 'bad' }],
      },
      {
        successCriteriaId: '1.4.12',
        rules: [{ ruleId: 'custom-b', status: 'warning', reason: 'check manually' }],
      },
      {
        successCriteriaId: '2.4.7',
        rules: [{ ruleId: 'custom-c', status: 'needs_review', reason: 'manual' }],
      },
      {
        successCriteriaId: '2.4.1',
        rules: [{ ruleId: 'custom-d', status: 'PASSED', reason: 'ok', impact: 'serious' }],
      },
    ]);

    expect(findings.map(f => f.status)).toEqual(['fail', 'needs_review', 'needs_review', 'pass']);
    expect(findings[3].severity).toBeNull();
    expect(findings[3].suggested_fix).toBeNull();
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

  test('best-practice axe rule gets a stable criterion label instead of empty values', () => {
    const axeResults = makeAxeResults({
      violations: [{
        id:     'landmark-complementary-is-top-level',
        tags:   ['cat.semantics', 'best-practice'],
        impact: 'moderate',
        nodes:  [{
          html: '<aside>Related links</aside>',
          target: ['aside'],
          failureSummary: 'Fix all of the following: The complementary landmark is contained in another landmark.',
        }],
        help:   'The complementary landmark should be top level.',
        helpUrl: 'https://dequeuniversity.com/rules/axe/4.11/landmark-complementary-is-top-level',
        description: 'Complementary landmarks should not be nested.',
      }],
    });

    const findings = mapResultsFlat(axeResults, 'https://example.com');
    expect(findings).toHaveLength(1);
    expect(findings[0].wcag_sc).toBe('best-practice');
    expect(findings[0].criterion_name).toBe('Complementary Landmark at Top Level');
    expect(findings[0].suggested_fix).toContain('Move <aside> elements');
  });

  test('AAA criteria like 1.4.6 resolve to names and levels', () => {
    const axeResults = makeAxeResults({
      violations: [{
        id:     'color-contrast-enhanced',
        tags:   ['cat.color', 'wcag146'],
        impact: 'serious',
        nodes:  [{ html: '<p>Low contrast</p>', target: ['p'], failureSummary: 'Fix all of the following: Text has insufficient contrast.' }],
        help:   'Text must have enhanced contrast.',
        helpUrl: 'https://dequeuniversity.com/rules/axe/4.11/color-contrast-enhanced',
        description: 'Ensure text contrast meets enhanced thresholds.',
      }],
    });

    const findings = mapResultsFlat(axeResults, 'https://example.com');
    expect(findings).toHaveLength(1);
    expect(findings[0].wcag_sc).toBe('1.4.6');
    expect(findings[0].criterion_name).toBe('Contrast (Enhanced)');
    expect(findings[0].level).toBe('AAA');
  });

  test('passes include element metadata for each passing node', () => {
    const axeResults = makeAxeResults({
      passes: [{
        id: 'image-alt',
        tags: ['wcag111', 'wcag2a'],
        help: 'Images should have alt text.',
        helpUrl: 'https://example.com/image-alt',
        description: 'Ensure <img> has alt text',
        nodes: [
          { html: '<img id="hero" alt="Hero" src="/hero.png">', target: ['#hero'] },
          { html: '<img alt="Logo" src="/logo.png">', target: ['header img.logo'] },
        ],
      }],
    });

    const findings = mapResultsFlat(axeResults, 'https://example.com');
    expect(findings).toHaveLength(2);
    expect(findings.every(f => f.status === 'pass')).toBe(true);
    expect(findings[0].element).toEqual({
      html: '<img id="hero" alt="Hero" src="/hero.png">',
      element_id: 'hero',
      tag: 'IMG',
      target: ['#hero'],
      page_url: 'https://example.com',
    });
    expect(findings[1].element).toEqual({
      html: '<img alt="Logo" src="/logo.png">',
      element_id: null,
      tag: 'IMG',
      target: ['header img.logo'],
      page_url: 'https://example.com',
    });
  });

  test('criteriaFilter narrows flat axe findings to a single WCAG SC', () => {
    const axeResults = makeAxeResults({
      violations: [
        {
          id: 'image-alt',
          tags: ['wcag111', 'wcag2a'],
          impact: 'serious',
          nodes: [{ html: '<img>', target: ['img'], failureSummary: 'Missing alt text' }],
          help: 'Images should have alt text.',
          helpUrl: 'https://example.com/image-alt',
          description: 'Ensure images have alternative text',
        },
        {
          id: 'label',
          tags: ['wcag332', 'wcag2a'],
          impact: 'moderate',
          nodes: [{ html: '<input>', target: ['input'], failureSummary: 'Missing label' }],
          help: 'Form controls need labels.',
          helpUrl: 'https://example.com/label',
          description: 'Ensure form controls have labels',
        },
      ],
    });

    const findings = mapResultsFlat(axeResults, 'https://example.com', 'en', '1.1.1');

    expect(findings).toHaveLength(1);
    expect(findings[0].wcag_sc).toBe('1.1.1');
    expect(findings[0].rule_id).toBe('image-alt');
  });
});

describe('formatSuccessCriterion', () => {
  test('formats best-practice rules without returning null', () => {
    expect(formatSuccessCriterion(['best-practice'])).toBe('Best Practice');
  });
});

describe('mapCustomResultsFlat element mapping', () => {
  test('expands explicit custom elements and normalizes their metadata', () => {
    const findings = mapCustomResultsFlat([
      {
        successCriteriaId: '2.4.7',
        rules: [{
          ruleId: 'custom-focus-visible',
          status: 'fail',
          reason: 'Focus is not visible.',
          elements: [
            { html: '<button id="save">Save</button>', target: ['#save'] },
            { outerHTML: '<a class="cta">Continue</a>', selector: '.cta', tagName: 'a' },
          ],
        }],
      },
    ], 'https://example.com');

    expect(findings).toHaveLength(2);
    expect(findings[0].element).toEqual({
      html: '<button id="save">Save</button>',
      element_id: 'save',
      tag: 'BUTTON',
      target: ['#save'],
      page_url: 'https://example.com',
    });
    expect(findings[1].element).toEqual({
      html: '<a class="cta">Continue</a>',
      element_id: null,
      tag: 'a',
      target: ['.cta'],
      page_url: 'https://example.com',
    });
  });

  test('needs_review without explicit element infers from reason tag snippet', () => {
    const findings = mapCustomResultsFlat([
      {
        successCriteriaId: '1.2.1',
        rules: [{
          ruleId: 'custom-audio-transcript',
          status: 'incomplete',
          reason: 'Manual check required for <audio id="podcast-player"> content.',
        }],
      },
    ], 'https://example.com');

    expect(findings).toHaveLength(1);
    expect(findings[0].status).toBe('needs_review');
    expect(findings[0].element).toEqual({
      html: '<audio id="podcast-player">',
      element_id: 'podcast-player',
      tag: 'AUDIO',
      target: [],
      page_url: 'https://example.com',
    });
  });

  test('needs_review without identifiable tag gets page-level html fallback element', () => {
    const findings = mapCustomResultsFlat([
      {
        successCriteriaId: '2.4.5',
        rules: [{
          ruleId: 'custom-multiple-ways',
          status: 'incomplete',
          reason: 'Only one navigation mechanism detected; verify multiple ways manually.',
        }],
      },
    ], 'https://example.com');

    expect(findings).toHaveLength(1);
    expect(findings[0].status).toBe('needs_review');
    expect(findings[0].element).toEqual({
      html: '<html>',
      element_id: null,
      tag: 'HTML',
      target: ['html'],
      page_url: 'https://example.com',
    });
  });
});
