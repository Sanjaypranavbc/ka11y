'use strict';

const path = require('path');

const {
  _loadCheckDefinitions,
  mergeWithAxe,
  runAll,
  runStaticChecks,
} = require('../../src/custom-checks/index');

describe('mergeWithAxe', () => {
  test('merges non-overlapping SC entries', () => {
    const axe = [{ successCriteriaId: '1.1.1', rules: [{ ruleId: 'image-alt' }] }];
    const custom = [{ successCriteriaId: '4.1.1', rules: [{ ruleId: 'custom-html-parsing' }] }];
    const merged = mergeWithAxe(axe, custom);
    expect(merged).toHaveLength(2);
    const ids = merged.map(m => m.successCriteriaId);
    expect(ids).toContain('1.1.1');
    expect(ids).toContain('4.1.1');
  });

  test('merges overlapping SC entries by combining rules arrays', () => {
    const axe =    [{ successCriteriaId: '4.1.1', rules: [{ ruleId: 'duplicate-id' }] }];
    const custom = [{ successCriteriaId: '4.1.1', rules: [{ ruleId: 'custom-html-parsing' }] }];
    const merged = mergeWithAxe(axe, custom);
    expect(merged).toHaveLength(1);
    expect(merged[0].rules).toHaveLength(2);
    const ruleIds = merged[0].rules.map(r => r.ruleId);
    expect(ruleIds).toContain('duplicate-id');
    expect(ruleIds).toContain('custom-html-parsing');
  });

  test('returns sorted by successCriteriaId', () => {
    const axe = [
      { successCriteriaId: '4.1.2', rules: [] },
      { successCriteriaId: '1.1.1', rules: [] },
    ];
    const merged = mergeWithAxe(axe, []);
    expect(merged[0].successCriteriaId).toBe('1.1.1');
    expect(merged[1].successCriteriaId).toBe('4.1.2');
  });

  test('empty custom results returns axe results unchanged', () => {
    const axe = [{ successCriteriaId: '1.1.1', rules: [{ ruleId: 'image-alt' }] }];
    const merged = mergeWithAxe(axe, []);
    expect(merged).toHaveLength(1);
    expect(merged[0].rules[0].ruleId).toBe('image-alt');
  });

  test('empty axe results returns custom results', () => {
    const custom = [{ successCriteriaId: '4.1.1', rules: [{ ruleId: 'custom-html-parsing' }] }];
    const merged = mergeWithAxe([], custom);
    expect(merged).toHaveLength(1);
    expect(merged[0].rules[0].ruleId).toBe('custom-html-parsing');
  });
});

describe('runStaticChecks', () => {
  test('returns an array of check results', async () => {
    const mockPage = { evaluate: jest.fn().mockResolvedValue([]) };
    // status-messages returns based on form/liveregion data
    mockPage.evaluate
      .mockResolvedValueOnce({ duplicateIds: [] })                      // html-parsing
      .mockResolvedValueOnce({ liveRegionCount: 0, formCount: 0, hasAlerts: false, hasPolite: false }) // status-messages
      .mockResolvedValueOnce({ hasSearch: true, hasSitemap: false, navCount: 1 }) // multiple-ways
      .mockResolvedValueOnce([]);                                        // meaningful-sequence

    const results = await runStaticChecks(mockPage);
    expect(Array.isArray(results)).toBe(true);
    expect(results.length).toBeGreaterThanOrEqual(1);
  });

  test('returns incomplete fallback entries when checks throw', async () => {
    const mockPage = { evaluate: jest.fn().mockRejectedValue(new Error('boom')) };
    const results = await runStaticChecks(mockPage);
    expect(results.length).toBeGreaterThan(0);
    expect(results.every(r => r.rules[0].status === 'incomplete')).toBe(true);
    expect(results[0].rules[0].reason).toContain('Custom check execution failed');
  });
});

describe('_loadCheckDefinitions', () => {
  test('discovers plugin files from the filesystem without editing index.js', () => {
    const fixtureDir = path.resolve(__dirname, '../fixtures/custom-checks');
    const checks = _loadCheckDefinitions(fixtureDir);

    expect(checks).toHaveLength(1);
    expect(checks[0].ruleId).toBe('plugin-smoke-check');
    expect(checks[0].mode).toBe('static');
    expect(checks[0].fallbackDescription).toBe('Fixture plugin rule loaded from the filesystem');
  });
});

describe('runAll', () => {
  test('does not silently drop failing custom checks', async () => {
    const mockPage = {
      evaluate: jest.fn().mockRejectedValue(new Error('forced-failure')),
      keyboard: { press: jest.fn().mockRejectedValue(new Error('forced-failure')) },
      on: jest.fn(),
      off: jest.fn(),
      url: jest.fn().mockReturnValue('https://example.com'),
    };

    const results = await runAll(mockPage);
    expect(results.length).toBeGreaterThan(0);
    expect(results.every(r => Array.isArray(r.rules) && r.rules.length === 1)).toBe(true);
    expect(results.every(r => r.rules[0].status === 'incomplete')).toBe(true);
  });
});
