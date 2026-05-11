'use strict';

const { run } = require('../../src/custom-checks/location.check');
const { getKeywordList } = require('../../src/custom-checks/sharedAssets');

function makePage(data) {
  return { evaluate: jest.fn().mockResolvedValue(data) };
}

describe('location.check (WCAG 2.4.8 AAA)', () => {
  test('passes when breadcrumb navigation is present', async () => {
    const page = makePage({
      hasBreadcrumb:     true,
      hasAriaCurrent:    false,
      hasActiveNavItem:  false,
      hasSiteMap:        false,
      hasLocationIndicator: true,
    });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('2.4.8');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].ruleId).toBe('custom-location');
    expect(result.rules[0].reason).toContain('breadcrumb');
  });

  test('passes when aria-current="page" is present in navigation', async () => {
    const page = makePage({
      hasBreadcrumb:     false,
      hasAriaCurrent:    true,
      hasActiveNavItem:  false,
      hasSiteMap:        false,
      hasLocationIndicator: true,
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('aria-current');
  });

  test('passes when active nav item is present', async () => {
    const page = makePage({
      hasBreadcrumb:     false,
      hasAriaCurrent:    false,
      hasActiveNavItem:  true,
      hasSiteMap:        false,
      hasLocationIndicator: true,
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('active navigation item');
  });

  test('passes when table of contents is present', async () => {
    const page = makePage({
      hasBreadcrumb: false,
      hasAriaCurrent: false,
      hasActiveNavItem: false,
      hasSiteMap: false,
      hasTableOfContents: true,
      hasLocationIndicator: true,
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('table of contents');
  });

  test('returns incomplete when no location indicator is detected', async () => {
    const page = makePage({
      hasBreadcrumb:     false,
      hasAriaCurrent:    false,
      hasActiveNavItem:  false,
      hasSiteMap:        false,
      hasLocationIndicator: false,
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].impact).toBe('moderate');
    expect(result.rules[0].reason).toContain('No location indicator');
  });

  test('impact is null when passing', async () => {
    const page = makePage({
      hasBreadcrumb:        true,
      hasAriaCurrent:       false,
      hasActiveNavItem:     false,
      hasSiteMap:           false,
      hasLocationIndicator: true,
    });
    const result = await run(page);
    expect(result.rules[0].impact).toBeNull();
  });

  test('loads Japanese location keywords from shared universal config', () => {
    expect(getKeywordList('location', 'breadcrumb_keywords')).toContain('パンくず');
    expect(getKeywordList('location', 'sitemap_keywords')).toContain('サイトマップ');
    expect(getKeywordList('location', 'toc_keywords')).toContain('目次');
  });
});
