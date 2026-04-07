'use strict';

const { run, SC, RULE_ID, HELP_URL } = require('../../src/custom-checks/status-messages.check');

function makePage(data) {
  return { evaluate: jest.fn().mockResolvedValue(data) };
}

function makeData(overrides = {}) {
  return {
    liveRegionCount: 0,
    formCount: 0,
    hasAlerts: false,
    hasPolite: false,
    needsLiveRegions: false,
    anyLiveRegionHasContent: false,
    dynamicContexts: [],
    alertsWithoutAtomicCount: 0,
    invalidWithoutLiveRegionCount: 0,
    ...overrides,
  };
}

describe('status-messages.check (WCAG 4.1.3)', () => {
  // ── Module exports ─────────────────────────────────────────────────────────
  test('exports SC as 4.1.3', () => { expect(SC).toBe('4.1.3'); });
  test('exports RULE_ID as custom-status-messages', () => { expect(RULE_ID).toBe('custom-status-messages'); });
  test('exports HELP_URL', () => { expect(HELP_URL).toContain('status-messages'); });

  // ── Pass: live regions, no unprotected contexts ────────────────────────────
  test('passes when live regions exist and no unprotected dynamic contexts', async () => {
    const page = makePage(makeData({ liveRegionCount: 2, hasAlerts: true, hasPolite: true }));
    const result = await run(page);
    expect(result.successCriteriaId).toBe('4.1.3');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].ruleId).toBe('custom-status-messages');
    expect(result.rules[0].impact).toBeNull();
    expect(result.rules[0].helpUrl).toBe(HELP_URL);
  });

  test('pass reason mentions live region count', async () => {
    const page = makePage(makeData({ liveRegionCount: 3, hasPolite: true }));
    const result = await run(page);
    expect(result.rules[0].reason).toContain('3 ARIA live region');
  });

  test('pass reason shows assertive and polite status', async () => {
    const page = makePage(makeData({ liveRegionCount: 2, hasAlerts: true, hasPolite: false }));
    const result = await run(page);
    expect(result.rules[0].reason).toContain('true');
    expect(result.rules[0].reason).toContain('false');
  });

  // ── Fail: dynamic contexts but no live regions ────────────────────────────
  test('fails when notification area exists but no live regions', async () => {
    const page = makePage(makeData({
      needsLiveRegions: true,
      dynamicContexts: ['notification area'],
    }));
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].impact).toBe('serious');
    expect(result.rules[0].reason).toContain('notification area');
  });

  test('fails with multiple dynamic contexts listed', async () => {
    const page = makePage(makeData({
      needsLiveRegions: true,
      dynamicContexts: ['search results', 'cart/counter', 'notification area'],
    }));
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('search results');
    expect(result.rules[0].reason).toContain('cart/counter');
    expect(result.rules[0].reason).toContain('notification area');
  });

  // ── Incomplete: dynamic contexts with live regions ─────────────────────────
  test('incomplete when dynamic contexts AND live regions exist (empty regions)', async () => {
    const page = makePage(makeData({
      liveRegionCount: 1,
      needsLiveRegions: true,
      dynamicContexts: ['notification area'],
      hasPolite: true,
      anyLiveRegionHasContent: false,
    }));
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('confirm they are populated on status updates');
  });

  test('incomplete when dynamic contexts AND live regions exist (with content)', async () => {
    const page = makePage(makeData({
      liveRegionCount: 2,
      needsLiveRegions: true,
      dynamicContexts: ['search results'],
      hasPolite: true,
      anyLiveRegionHasContent: true,
    }));
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('At least one live region contains text');
  });

  // ── Incomplete: forms present ──────────────────────────────────────────────
  test('returns incomplete when forms exist but no live regions', async () => {
    const page = makePage(makeData({ formCount: 2 }));
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].impact).toBe('moderate');
    expect(result.rules[0].reason).toMatch('2 form');
  });

  test('returns incomplete when forms and live regions exist', async () => {
    const page = makePage(makeData({ liveRegionCount: 1, formCount: 1, hasPolite: true }));
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].impact).toBeNull();
    expect(result.rules[0].reason).toContain('Verify form validation');
  });

  test('form with live regions has null impact', async () => {
    const page = makePage(makeData({ liveRegionCount: 1, formCount: 1, hasPolite: true }));
    const result = await run(page);
    expect(result.rules[0].impact).toBeNull();
  });

  test('form without live regions has moderate impact', async () => {
    const page = makePage(makeData({ formCount: 1 }));
    const result = await run(page);
    expect(result.rules[0].impact).toBe('moderate');
  });

  // ── Incomplete: no forms, no live regions ─────────────────────────────────
  test('incomplete when no forms and no live regions', async () => {
    const page = makePage(makeData());
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].impact).toBe('moderate');
    expect(result.rules[0].reason).toContain('No ARIA live regions');
  });

  // ── Extra rules: alertsWithoutAtomic ──────────────────────────────────────
  test('adds extra incomplete rule for alerts without aria-atomic', async () => {
    const page = makePage(makeData({
      liveRegionCount: 1,
      alertsWithoutAtomicCount: 2,
    }));
    const result = await run(page);
    const atomicRule = result.rules.find(r => r.ruleId === 'custom-status-messages-atomic');
    expect(atomicRule).toBeDefined();
    expect(atomicRule.status).toBe('incomplete');
    expect(atomicRule.reason).toContain('2');
    expect(atomicRule.reason).toContain('aria-atomic');
  });

  test('no atomic extra rule when count is 0', async () => {
    const page = makePage(makeData({ liveRegionCount: 1, alertsWithoutAtomicCount: 0 }));
    const result = await run(page);
    const atomicRule = result.rules.find(r => r.ruleId === 'custom-status-messages-atomic');
    expect(atomicRule).toBeUndefined();
  });

  // ── Extra rules: invalidWithoutLiveRegion ─────────────────────────────────
  test('adds extra incomplete rule for aria-invalid without live region', async () => {
    const page = makePage(makeData({
      liveRegionCount: 1,
      invalidWithoutLiveRegionCount: 3,
    }));
    const result = await run(page);
    const invalidRule = result.rules.find(r => r.ruleId === 'custom-status-messages-inline-validation');
    expect(invalidRule).toBeDefined();
    expect(invalidRule.status).toBe('incomplete');
    expect(invalidRule.reason).toContain('3');
    expect(invalidRule.reason).toContain('aria-invalid');
  });

  test('no inline-validation extra rule when count is 0', async () => {
    const page = makePage(makeData({ liveRegionCount: 1 }));
    const result = await run(page);
    const invalidRule = result.rules.find(r => r.ruleId === 'custom-status-messages-inline-validation');
    expect(invalidRule).toBeUndefined();
  });

  // ── Combined extra rules ───────────────────────────────────────────────────
  test('can have both atomic and inline-validation extra rules', async () => {
    const page = makePage(makeData({
      liveRegionCount: 2,
      hasAlerts: true,
      alertsWithoutAtomicCount: 1,
      invalidWithoutLiveRegionCount: 2,
    }));
    const result = await run(page);
    expect(result.rules.length).toBe(3); // pass + atomic + inline-validation
  });

  test('extra rules appended to fail result too', async () => {
    const page = makePage(makeData({
      needsLiveRegions: true,
      dynamicContexts: ['notification area'],
      alertsWithoutAtomicCount: 1,
    }));
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules.length).toBe(2);
    expect(result.rules[1].ruleId).toBe('custom-status-messages-atomic');
  });

  // ── FP fix: notification elements inside existing live regions ────────────
  test('notification area INSIDE a live region → needsLiveRegions false → PASS', async () => {
    const page = makePage(makeData({
      liveRegionCount: 1,
      hasPolite: true,
      needsLiveRegions: false,
    }));
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
  });

  test('dynamic contexts present AND live regions exist → INCOMPLETE', async () => {
    const page = makePage(makeData({
      liveRegionCount: 1,
      hasPolite: true,
      needsLiveRegions: true,
      dynamicContexts: ['notification area'],
    }));
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
  });

  test('notification area WITHOUT any live regions should FAIL', async () => {
    const page = makePage(makeData({
      needsLiveRegions: true,
      dynamicContexts: ['notification area'],
    }));
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('notification area');
  });

  // ── Source validations ─────────────────────────────────────────────────────
  test('FP fix: source checks notification elements for live region ancestors', () => {
    const src = require('fs').readFileSync(
      require('path').resolve(__dirname, '../../src/custom-checks/status-messages.check.js'),
      'utf8'
    );
    expect(src).toMatch(/parentElement|closest/);
    expect(src).toMatch(/role.*status|aria-live/);
  });

  test('includes Japanese dynamic-context keywords in source heuristics', () => {
    const src = require('fs').readFileSync(
      require('path').resolve(__dirname, '../../src/custom-checks/status-messages.check.js'),
      'utf8'
    );
    expect(src).toContain('検索結果');
    expect(src).toContain('未読');
    expect(src).toContain('カート');
  });

  test('does not require explicit aria-atomic on role="alert"', () => {
    const src = require('fs').readFileSync(
      require('path').resolve(__dirname, '../../src/custom-checks/status-messages.check.js'),
      'utf8'
    );
    expect(src).toContain('[aria-live="assertive"]:not([role="alert"])');
  });
});
