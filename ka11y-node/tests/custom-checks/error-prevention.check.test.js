'use strict';

const { run } = require('../../src/custom-checks/error-prevention.check');

function makePage(data) {
  return { evaluate: jest.fn().mockResolvedValue(data) };
}

describe('error-prevention.check (WCAG 3.3.4)', () => {
  test('passes when no high-risk forms exist', async () => {
    const page = makePage([]);
    const result = await run(page);
    expect(result.successCriteriaId).toBe('3.3.4');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].ruleId).toBe('custom-error-prevention');
    expect(result.rules[0].reason).toContain('No legal');
  });

  test('fails when financial form lacks safeguards', async () => {
    const page = makePage([
      { category: 'financial', hasSafeguard: false, hasReviewText: false, hasConfirmCheckbox: false, hasReviewButton: false, formAction: '/checkout', formId: 'payment-form' },
    ]);
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].impact).toBe('serious');
    expect(result.rules[0].reason).toContain('financial');
  });

  test('passes when financial form has a review safeguard', async () => {
    const page = makePage([
      { category: 'financial', hasSafeguard: true, hasReviewText: true, hasConfirmCheckbox: false, hasReviewButton: false, formAction: '/checkout', formId: null },
    ]);
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('1 high-risk form');
  });

  test('fails for destructive action forms without safeguards', async () => {
    const page = makePage([
      { category: 'destructive', hasSafeguard: false, hasReviewText: false, hasConfirmCheckbox: false, hasReviewButton: false, formAction: '/delete-account', formId: null },
    ]);
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('destructive');
  });
});