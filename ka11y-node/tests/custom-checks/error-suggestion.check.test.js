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
});