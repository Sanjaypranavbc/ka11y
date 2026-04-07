'use strict';

const { run, SC, RULE_ID, HELP_URL } = require('../../src/custom-checks/accessible-auth.check');

function makePage(data) {
  return { evaluate: jest.fn().mockResolvedValue(data) };
}

describe('accessible-auth.check (WCAG 3.3.8)', () => {
  // ── Module exports ─────────────────────────────────────────────────────────
  test('exports SC as 3.3.8', () => { expect(SC).toBe('3.3.8'); });
  test('exports RULE_ID as custom-accessible-auth', () => { expect(RULE_ID).toBe('custom-accessible-auth'); });
  test('exports HELP_URL', () => { expect(HELP_URL).toContain('accessible-authentication'); });

  // ── No auth forms ──────────────────────────────────────────────────────────
  test('passes when no auth forms are found', async () => {
    const page = makePage({ hasAuthForm: false });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('3.3.8');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].ruleId).toBe('custom-accessible-auth');
    expect(result.rules[0].impact).toBeNull();
    expect(result.rules[0].reason).toContain('No authentication forms');
    expect(result.rules[0].helpUrl).toBe(HELP_URL);
  });

  // ── Auth form with no issues ───────────────────────────────────────────────
  test('passes when auth form has no issues', async () => {
    const page = makePage({ hasAuthForm: true, authFormCount: 1, issues: [] });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].impact).toBeNull();
    expect(result.rules[0].reason).toContain('1 authentication form');
    expect(result.rules[0].reason).toContain('no CAPTCHA');
  });

  test('passes when multiple auth forms all have no issues', async () => {
    const page = makePage({ hasAuthForm: true, authFormCount: 3, issues: [] });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('3 authentication form');
  });

  // ── CAPTCHA issues ─────────────────────────────────────────────────────────
  test('fails when CAPTCHA has no alternative', async () => {
    const page = makePage({
      hasAuthForm: true,
      authFormCount: 1,
      issues: [{ type: 'captcha-no-alternative', detail: 'form#login: CAPTCHA detected (reCAPTCHA/hCaptcha) without a detectable audio or accessible alternative.' }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].impact).toBe('serious');
    expect(result.rules[0].reason).toContain('CAPTCHA');
    expect(result.rules[0].reason).toContain('reCAPTCHA');
  });

  test('fails with image CAPTCHA issue detail', async () => {
    const page = makePage({
      hasAuthForm: true,
      authFormCount: 1,
      issues: [{ type: 'captcha-no-alternative', detail: 'authentication form: CAPTCHA detected (image CAPTCHA) without a detectable audio or accessible alternative.' }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('image CAPTCHA');
  });

  test('fails with Cloudflare Turnstile issue detail', async () => {
    const page = makePage({
      hasAuthForm: true,
      authFormCount: 1,
      issues: [{ type: 'captcha-no-alternative', detail: 'authentication form: CAPTCHA detected (Cloudflare Turnstile) without accessible alternative.' }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('Turnstile');
  });

  // ── Paste blocking ─────────────────────────────────────────────────────────
  test('fails when password field blocks paste', async () => {
    const page = makePage({
      hasAuthForm: true,
      authFormCount: 1,
      issues: [{ type: 'paste-blocked', detail: 'form#login: password field blocks paste, preventing use of password managers.' }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].impact).toBe('serious');
    expect(result.rules[0].reason).toContain('paste');
  });

  // ── Cognitive test ─────────────────────────────────────────────────────────
  test('fails for cognitive test without alternative', async () => {
    const page = makePage({
      hasAuthForm: true,
      authFormCount: 1,
      issues: [{ type: 'cognitive-test', detail: 'authentication form: authentication appears to require solving a cognitive puzzle without an accessible alternative.' }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('cognitive');
  });

  // ── Multiple issues ────────────────────────────────────────────────────────
  test('fails when multiple issues exist (all included in reason)', async () => {
    const page = makePage({
      hasAuthForm: true,
      authFormCount: 2,
      issues: [
        { type: 'captcha-no-alternative', detail: 'form#login: CAPTCHA without alternative.' },
        { type: 'paste-blocked', detail: 'form#signup: password field blocks paste.' },
      ],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('2 authentication form');
    expect(result.rules[0].reason).toContain('CAPTCHA');
    expect(result.rules[0].reason).toContain('paste');
  });

  // ── N10 fix: data-sitekey alone should not be flagged ─────────────────────
  test('N10 fix: does not flag data-sitekey alone without CAPTCHA class context', async () => {
    const page = makePage({ hasAuthForm: true, authFormCount: 1, issues: [] });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('no CAPTCHA');
  });

  // ── Result structure ───────────────────────────────────────────────────────
  test('description is consistent', async () => {
    const pass = await run(makePage({ hasAuthForm: false }));
    expect(pass.rules[0].description).toContain('cognitive function tests');

    const fail = await run(makePage({
      hasAuthForm: true,
      authFormCount: 1,
      issues: [{ type: 'paste-blocked', detail: 'blocked.' }],
    }));
    expect(fail.rules[0].description).toContain('cognitive function tests');
  });

  test('helpUrl is set in all results', async () => {
    const pass = await run(makePage({ hasAuthForm: false }));
    expect(pass.rules[0].helpUrl).toBe(HELP_URL);

    const fail = await run(makePage({
      hasAuthForm: true,
      authFormCount: 1,
      issues: [{ type: 'paste-blocked', detail: 'blocked.' }],
    }));
    expect(fail.rules[0].helpUrl).toBe(HELP_URL);
  });

  // ── Source validation ─────────────────────────────────────────────────────
  test('includes Japanese auth/CAPTCHA patterns in source heuristics', () => {
    const src = require('fs').readFileSync(
      require('path').resolve(__dirname, '../../src/custom-checks/accessible-auth.check.js'),
      'utf8'
    );
    expect(src).toContain('ログイン');
    expect(src).toContain('音声');
    expect(src).toContain('パスワード再設定');
  });

  test('scopes passkey and CAPTCHA detection to the current auth form context', () => {
    const src = require('fs').readFileSync(
      require('path').resolve(__dirname, '../../src/custom-checks/accessible-auth.check.js'),
      'utf8'
    );
    expect(src).toContain('authScopeFor');
    expect(src).toContain('authScope.querySelectorAll');
  });

  test('source contains Cloudflare Turnstile detection', () => {
    const src = require('fs').readFileSync(
      require('path').resolve(__dirname, '../../src/custom-checks/accessible-auth.check.js'),
      'utf8'
    );
    expect(src).toContain('cf-turnstile');
  });

  test('source uses synthetic paste event for paste-blocking detection', () => {
    const src = require('fs').readFileSync(
      require('path').resolve(__dirname, '../../src/custom-checks/accessible-auth.check.js'),
      'utf8'
    );
    expect(src).toContain('ClipboardEvent');
    expect(src).toContain('defaultPrevented');
  });
});
