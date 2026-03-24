'use strict';

const { run } = require('../../src/custom-checks/accessible-auth.check');

function makePage(data) {
  return { evaluate: jest.fn().mockResolvedValue(data) };
}

describe('accessible-auth.check (WCAG 3.3.8)', () => {
  test('passes when no auth forms are found', async () => {
    const page = makePage({ hasAuthForm: false });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('3.3.8');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].ruleId).toBe('custom-accessible-auth');
  });

  test('passes when auth form has no issues', async () => {
    const page = makePage({ hasAuthForm: true, authFormCount: 1, issues: [] });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('1 authentication form');
  });

  test('fails when CAPTCHA has no alternative', async () => {
    const page = makePage({
      hasAuthForm: true,
      authFormCount: 1,
      issues: [{ type: 'captcha-no-alternative', detail: 'CAPTCHA detected (reCAPTCHA) without an audio or alternative accessible version.' }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].impact).toBe('serious');
    expect(result.rules[0].reason).toContain('CAPTCHA');
  });

  test('fails when password field blocks paste', async () => {
    const page = makePage({
      hasAuthForm: true,
      authFormCount: 1,
      issues: [{ type: 'paste-blocked', detail: 'Password field blocks paste, preventing use of password managers.' }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('paste');
  });

  test('fails for cognitive test without alternative', async () => {
    const page = makePage({
      hasAuthForm: true,
      authFormCount: 1,
      issues: [{ type: 'cognitive-test', detail: 'Authentication appears to require solving a cognitive puzzle without an accessible alternative.' }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('cognitive');
  });
});