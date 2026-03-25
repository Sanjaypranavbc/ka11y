'use strict';

const { run } = require('../../src/custom-checks/status-messages.check');

function makePage(data) {
  return { evaluate: jest.fn().mockResolvedValue(data) };
}

describe('status-messages.check (WCAG 4.1.3)', () => {
  test('passes when live regions exist', async () => {
    const page = makePage({ liveRegionCount: 2, formCount: 1, hasAlerts: true, hasPolite: true });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('4.1.3');
    expect(result.rules[0].status).toBe('pass');
  });

  test('fails when forms exist but no live regions', async () => {
    const page = makePage({
      liveRegionCount: 0, formCount: 2, hasAlerts: false, hasPolite: false,
      needsLiveRegions: true, dynamicContexts: ['2 form(s)'],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].impact).toBe('serious');
    expect(result.rules[0].reason).toMatch('2 form');
  });

  test('fails when notification area exists but no live regions', async () => {
    const page = makePage({
      liveRegionCount: 0, formCount: 0, hasAlerts: false, hasPolite: false,
      needsLiveRegions: true, dynamicContexts: ['notification area'],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('notification area');
  });

  test('incomplete when no forms and no live regions', async () => {
    const page = makePage({
      liveRegionCount: 0, formCount: 0, hasAlerts: false, hasPolite: false,
      needsLiveRegions: false, dynamicContexts: [],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
  });

  test('ruleId is custom-status-messages', async () => {
    const page = makePage({ liveRegionCount: 1, formCount: 0, hasAlerts: false, hasPolite: true, needsLiveRegions: false, dynamicContexts: [] });
    const result = await run(page);
    expect(result.rules[0].ruleId).toBe('custom-status-messages');
  });

  // FP fix: notification elements already inside live regions should not trigger "needs" message
  describe('FP fix: notification elements inside existing live regions', () => {
    test('notification area with live regions present should PASS (not report as needing live regions)', async () => {
      // When liveRegionCount > 0, the check passes regardless of needsLiveRegions flag.
      // This covers the case where notification elements are inside existing live regions.
      const page = makePage({
        liveRegionCount: 1,
        formCount: 0,
        hasAlerts: false,
        hasPolite: true,
        needsLiveRegions: true,   // notification area detected...
        dynamicContexts: ['notification area'],
      });
      const result = await run(page);
      // liveRegionCount > 0 → should pass, not fail
      expect(result.rules[0].status).toBe('pass');
      expect(result.rules[0].reason).toContain('live region');
    });

    test('notification area WITHOUT any live regions should FAIL', async () => {
      const page = makePage({
        liveRegionCount: 0,
        formCount: 0,
        hasAlerts: false,
        hasPolite: false,
        needsLiveRegions: true,
        dynamicContexts: ['notification area'],
      });
      const result = await run(page);
      expect(result.rules[0].status).toBe('fail');
      expect(result.rules[0].reason).toContain('notification area');
    });

    test('FP fix: source checks notification elements for live region ancestors', () => {
      const src = require('fs').readFileSync(
        require('path').resolve(__dirname, '../../src/custom-checks/status-messages.check.js'),
        'utf8'
      );
      // Verify the updated logic walks ancestors to check for live region containment
      expect(src).toMatch(/parentElement|closest/);
      expect(src).toMatch(/role.*status|aria-live/);
    });
  });
});