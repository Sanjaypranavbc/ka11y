'use strict';

const { run } = require('../../src/custom-checks/location.check');

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
      hasAriaCurrentStep: false,
      hasJsonLdBreadcrumb: false,
      hasVisibleLocationIndicator: true,
      hasWeakLocationIndicator: false,
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
      hasAriaCurrentStep: false,
      hasJsonLdBreadcrumb: false,
      hasVisibleLocationIndicator: true,
      hasWeakLocationIndicator: false,
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
      hasAriaCurrentStep: false,
      hasJsonLdBreadcrumb: false,
      hasVisibleLocationIndicator: true,
      hasWeakLocationIndicator: false,
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('active navigation item');
  });

  test('returns incomplete when no location indicator is detected', async () => {
    const page = makePage({
      hasBreadcrumb:     false,
      hasAriaCurrent:    false,
      hasActiveNavItem:  false,
      hasSiteMap:        false,
      hasAriaCurrentStep: false,
      hasJsonLdBreadcrumb: false,
      hasVisibleLocationIndicator: false,
      hasWeakLocationIndicator: false,
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
      hasAriaCurrentStep: false,
      hasJsonLdBreadcrumb: false,
      hasVisibleLocationIndicator: true,
      hasWeakLocationIndicator: false,
    });
    const result = await run(page);
    expect(result.rules[0].impact).toBeNull();
  });

  test('returns incomplete when only sitemap or JSON-LD location hints exist', async () => {
    const page = makePage({
      hasBreadcrumb: false,
      hasAriaCurrent: false,
      hasActiveNavItem: false,
      hasSiteMap: true,
      hasAriaCurrentStep: false,
      hasJsonLdBreadcrumb: true,
      hasVisibleLocationIndicator: false,
      hasWeakLocationIndicator: true,
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('indirect location signals');
  });

  test('includes Japanese location keywords in source heuristics', () => {
    const src = require('fs').readFileSync(
      require('path').resolve(__dirname, '../../src/custom-checks/location.check.js'),
      'utf8'
    );
    expect(src).toContain('パンくず');
    expect(src).toContain('サイトマップ');
  });
});
