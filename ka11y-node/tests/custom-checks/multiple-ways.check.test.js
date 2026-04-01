'use strict';

const { run } = require('../../src/custom-checks/multiple-ways.check');

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

  test('includes Japanese navigation keywords in source heuristics', () => {
    const src = require('fs').readFileSync(
      require('path').resolve(__dirname, '../../src/custom-checks/multiple-ways.check.js'),
      'utf8'
    );
    expect(src).toContain('検索');
    expect(src).toContain('サイトマップ');
    expect(src).toContain('目次');
  });
});
