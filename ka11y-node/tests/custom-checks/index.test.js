'use strict';

const { mergeWithAxe, runStaticChecks } = require('../../src/custom-checks/index');

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
});