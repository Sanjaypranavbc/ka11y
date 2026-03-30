'use strict';

const { run } = require('../../src/custom-checks/error-suggestion.check');

function makePage(data) {
  return { evaluate: jest.fn().mockResolvedValue(data) };
}

describe('error-suggestion.check (WCAG 3.3.3)', () => {
  test('passes when no forms exist', async () => {
    const page = makePage({ formCount: 0, errorsWithSuggestion: 0, errorsWithoutSuggestion: [], allErrors: [] });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('3.3.3');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].ruleId).toBe('custom-error-suggestion');
    expect(result.rules[0].reason).toContain('No forms');
  });

  test('returns incomplete when forms exist but no errors are visible', async () => {
    const page = makePage({ formCount: 2, errorsWithSuggestion: 0, errorsWithoutSuggestion: [], allErrors: [] });
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].impact).toBe('moderate');
  });

  test('fails when error messages lack suggestions', async () => {
    const page = makePage({
      formCount: 1,
      errorsWithSuggestion: 0,
      errorsWithoutSuggestion: ['Invalid', 'Error'],
      allErrors: ['Invalid', 'Error'],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('2 error message(s)');
  });

  test('passes when all error messages have suggestions', async () => {
    const page = makePage({
      formCount: 1,
      errorsWithSuggestion: 2,
      errorsWithoutSuggestion: [],
      allErrors: ['Please enter a valid email address', 'Must be at least 8 characters'],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('2 error message(s) checked');
  });

  test('N11 fix: class-based selectors in source are scoped to form descendants', () => {
    // Regression test: class-based error selectors must start with "form " to avoid
    // matching documentation/decorative elements outside forms.
    const src = require('fs').readFileSync(
      require('path').resolve(__dirname, '../../src/custom-checks/error-suggestion.check.js'),
      'utf8'
    );
    // Extract classSelectors array content
    const match = src.match(/const classSelectors\s*=\s*\[([\s\S]*?)\]/);
    expect(match).not.toBeNull();
    const selectors = match[1].match(/'([^']+)'/g) || [];
    expect(selectors.length).toBeGreaterThan(0);
    selectors.forEach(sel => {
      const clean = sel.replace(/'/g, '');
      expect(clean).toMatch(/^form /);
    });
  });

  // FP Fix: sibling selector tests
  describe('FP Fix: sibling selector — non-immediate sibling and outside-form detection', () => {
    test('aria-invalid with non-immediate sibling error message should be detected', async () => {
      // The updated code uses ~ (general sibling) + class filter — simulate the browser
      // returning an error element that is a non-immediate sibling with class "error"
      const page = makePage({
        formCount: 1,
        allErrors: ['Please enter a valid email address'],
      });
      const result = await run(page);
      // With a valid suggestion message, should pass
      expect(result.rules[0].status).toBe('pass');
    });

    test('aria-invalid with terse error message should fail', async () => {
      const page = makePage({
        formCount: 1,
        allErrors: ['Invalid'],
      });
      const result = await run(page);
      expect(result.rules[0].status).toBe('fail');
      expect(result.rules[0].reason).toContain('lack correction guidance');
    });

    test('visible error with correction hint should PASS', async () => {
      const page = makePage({
        formCount: 1,
        allErrors: ['Please enter a valid email address such as user@example.com'],
      });
      const result = await run(page);
      expect(result.rules[0].status).toBe('pass');
    });

    test('FP fix: source does not use immediate next-sibling selector for aria-invalid', () => {
      const src = require('fs').readFileSync(
        require('path').resolve(__dirname, '../../src/custom-checks/error-suggestion.check.js'),
        'utf8'
      );
      // The old bad selector was: [aria-invalid="true"] + *
      // After fix it should NOT be present as a bare + selector
      expect(src).not.toMatch(/\[aria-invalid="true"\]\s*\+\s*\*/);
    });

    test('FP fix: source uses general sibling combinator (~) for aria-invalid error detection', () => {
      const src = require('fs').readFileSync(
        require('path').resolve(__dirname, '../../src/custom-checks/error-suggestion.check.js'),
        'utf8'
      );
      expect(src).toMatch(/\[aria-invalid="true"\]\s*~\s*/);
    });
  });

  test('includes Japanese correction/error keywords in source heuristics', () => {
    const src = require('fs').readFileSync(
      require('path').resolve(__dirname, '../../src/custom-checks/error-suggestion.check.js'),
      'utf8'
    );
    expect(src).toContain('入力してください');
    expect(src).toContain('有効な');
    expect(src).toContain('必須');
  });
});
