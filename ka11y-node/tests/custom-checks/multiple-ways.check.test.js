'use strict';

const { run } = require('../../src/custom-checks/multiple-ways.check');
const { getKeywordList } = require('../../src/custom-checks/sharedAssets');

function makePage(data) {
  return { evaluate: jest.fn().mockResolvedValue(data) };
}

describe('multiple-ways.check (WCAG 2.4.5)', () => {
  test('passes with search + nav', async () => {
    const page = makePage({ hasSearch: true, hasSitemap: false, navCount: 1 });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('2.4.5');
    expect(result.rules[0].status).toBe('pass');
  });

  test('passes with sitemap + nav', async () => {
    const page = makePage({ hasSearch: false, hasSitemap: true, navCount: 2 });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
  });

  test('incomplete with only a nav and no search or sitemap', async () => {
    const page = makePage({ hasSearch: false, hasSitemap: false, navCount: 1 });
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
  });

  test('incomplete with nothing', async () => {
    const page = makePage({ hasSearch: false, hasSitemap: false, navCount: 0 });
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].impact).toBe('moderate');
  });

  test('ruleId is custom-multiple-ways', async () => {
    const page = makePage({ hasSearch: true, hasSitemap: true, navCount: 1 });
    const result = await run(page);
    expect(result.rules[0].ruleId).toBe('custom-multiple-ways');
  });

  test('loads Japanese navigation keywords from shared universal config', () => {
    expect(getKeywordList('multiple_ways', 'search_keywords')).toContain('検索');
    expect(getKeywordList('multiple_ways', 'sitemap_keywords')).toContain('サイトマップ');
    expect(getKeywordList('multiple_ways', 'toc_keywords')).toContain('目次');
  });
});
