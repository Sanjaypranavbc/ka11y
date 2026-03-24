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
});