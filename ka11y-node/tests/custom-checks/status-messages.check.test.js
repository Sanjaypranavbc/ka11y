'use strict';

const { run } = require('../../src/custom-checks/status-messages.check');

function makePage(data) {
  return { evaluate: jest.fn().mockResolvedValue(data) };
}

describe('status-messages.check (WCAG 4.1.3)', () => {
  test('passes when live regions exist and no unprotected dynamic contexts', async () => {
    // needsLiveRegions is falsy → all dynamic contexts are covered by live regions
    const page = makePage({
      liveRegionCount: 2,
      formCount: 1,
      hasAlerts: true,
      hasPolite: true,
      hasSearchResults: false,
      hasCartOrCounter: false,
      hasNotificationArea: false,
      needsLiveRegions: false,
      dynamicContexts: [],
    });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('4.1.3');
    expect(result.rules[0].status).toBe('pass');
  });

  test('fails when forms exist but no live regions', async () => {
    const page = makePage({
      liveRegionCount: 0, formCount: 2, hasAlerts: false, hasPolite: false,
      hasSearchResults: false, hasCartOrCounter: false, hasNotificationArea: false,
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
      hasSearchResults: false, hasCartOrCounter: false, hasNotificationArea: true,
      needsLiveRegions: true, dynamicContexts: ['notification area'],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('notification area');
  });

  test('incomplete when no forms and no live regions', async () => {
    const page = makePage({
      liveRegionCount: 0, formCount: 0, hasAlerts: false, hasPolite: false,
      hasSearchResults: false, hasCartOrCounter: false, hasNotificationArea: false,
      needsLiveRegions: false, dynamicContexts: [],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
  });

  test('ruleId is custom-status-messages', async () => {
    const page = makePage({
      liveRegionCount: 1,
      formCount: 0,
      hasAlerts: false,
      hasPolite: true,
      hasSearchResults: false,
      hasCartOrCounter: false,
      hasNotificationArea: false,
      needsLiveRegions: false,
      dynamicContexts: [],
    });
    const result = await run(page);
    expect(result.rules[0].ruleId).toBe('custom-status-messages');
  });

  // FP fix: notification elements already inside live regions should not trigger "needs" message
  describe('FP fix: notification elements inside existing live regions', () => {
    test('notification area INSIDE a live region → needsLiveRegions false → PASS', async () => {
      // When the source code's ancestor walk finds a live region ancestor, it sets
      // hasNotificationArea=false, so needsLiveRegions is false even though live regions exist.
      const page = makePage({
        liveRegionCount: 1,
        formCount: 0,
        hasAlerts: false,
        hasPolite: true,
        hasSearchResults: false,
        hasCartOrCounter: false,
        hasNotificationArea: false,
        needsLiveRegions: false,  // notification area IS inside a live region → not a problem
        dynamicContexts: [],
      });
      const result = await run(page);
      expect(result.rules[0].status).toBe('pass');
      expect(result.rules[0].reason).toContain('live region');
    });

    test('dynamic contexts present AND live regions exist → INCOMPLETE (needs manual review)', async () => {
      // needsLiveRegions: true means at least one dynamic context lacks a live region ancestor.
      // Even though live regions exist, we cannot verify they cover every context statically.
      const page = makePage({
        liveRegionCount: 1,
        formCount: 0,
        hasAlerts: false,
        hasPolite: true,
        hasSearchResults: false,
        hasCartOrCounter: false,
        hasNotificationArea: true,
        needsLiveRegions: true,
        dynamicContexts: ['notification area'],
      });
      const result = await run(page);
      expect(result.rules[0].status).toBe('incomplete');
      expect(result.rules[0].reason).toContain('live region');
    });

    test('notification area WITHOUT any live regions should FAIL', async () => {
      const page = makePage({
        liveRegionCount: 0,
        formCount: 0,
        hasAlerts: false,
        hasPolite: false,
        hasSearchResults: false,
        hasCartOrCounter: false,
        hasNotificationArea: true,
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

  test('localizes reasons to Japanese when lang=ja', async () => {
    const page = makePage({
      liveRegionCount: 0,
      formCount: 0,
      hasAlerts: false,
      hasPolite: false,
      hasSearchResults: true,
      hasCartOrCounter: false,
      hasNotificationArea: false,
      needsLiveRegions: true,
    });
    const result = await run(page, { lang: 'ja' });
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('動的コンテンツ');
    expect(result.rules[0].reason).toContain('検索結果');
  });

  test('emits toast heuristic rule when toast containers lack ARIA live semantics', async () => {
    const page = makePage({
      liveRegionCount: 1,
      formCount: 0,
      hasAlerts: false,
      hasPolite: true,
      hasSearchResults: false,
      hasCartOrCounter: false,
      hasNotificationArea: true,
      needsLiveRegions: true,
      toastWithoutAria: [
        { html: '<div class="Toastify__toast-container"></div>', tag: 'DIV' },
      ],
    });
    const result = await run(page);
    const toastRule = result.rules.find(r => r.ruleId === 'custom-status-messages-toast');
    expect(toastRule).toBeTruthy();
    expect(toastRule.status).toBe('incomplete');
    expect(toastRule.reason).toContain('toast');
  });
});
