'use strict';

/**
 * Unit tests for the WCAG 2.5.1 Pointer Gestures custom-check wrapper.
 *
 * Covers the three branches of the check:
 *   - pass        — auditor returns no findings
 *   - fail        — auditor returns at least one violation
 *   - incomplete  — auditor returns only warnings (escape-hatch / library-only)
 *
 * The audit orchestrator (`auditPointerGestures`) is mocked at the require
 * boundary so these tests run without a browser. Orchestrator internals are
 * exercised by `src/audits/wcag-2.5.1/__tests__/pointer-gestures.test.js`.
 */

jest.mock('../../src/audits/wcag-2.5.1/index.js', () => ({
  auditPointerGestures: jest.fn(),
}));

const { auditPointerGestures } = require('../../src/audits/wcag-2.5.1/index.js');
const { run, SC, RULE_ID, HELP_URL, MODE } = require('../../src/custom-checks/pointer-gestures.check');

function makePage(url = 'https://example.com') {
  return { url: () => url };
}

function emptyResult() {
  return {
    pageUrl: 'https://example.com',
    pageLang: 'en',
    gestureLibrariesDetected: [],
    domFindingsCount: 0,
    violations: [],
    warnings: [],
    summary: { total: 0, violations: 0, warnings: 0, layers: { domPattern: 0, libraryDetected: 0, axeRule: 0 } },
  };
}

beforeEach(() => {
  auditPointerGestures.mockReset();
});

describe('pointer-gestures.check (WCAG 2.5.1) — module exports', () => {
  test('exports the expected metadata constants', () => {
    expect(SC).toBe('2.5.1');
    expect(RULE_ID).toBe('custom-pointer-gestures');
    expect(MODE).toBe('static');
    expect(HELP_URL).toBe('https://www.w3.org/WAI/WCAG22/Understanding/pointer-gestures');
  });
});

describe('pointer-gestures.check (WCAG 2.5.1) — pass branch', () => {
  test('returns pass when auditor reports no findings', async () => {
    auditPointerGestures.mockResolvedValue(emptyResult());

    const result = await run(makePage());

    expect(result.successCriteriaId).toBe('2.5.1');
    expect(result.rules).toHaveLength(1);
    expect(result.rules[0].ruleId).toBe('custom-pointer-gestures');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].impact).toBeNull();
    expect(result.rules[0].helpUrl).toBe(HELP_URL);
    expect(result.rules[0].elements).toBeUndefined();
  });

  test('passes the current page URL to the auditor', async () => {
    auditPointerGestures.mockResolvedValue(emptyResult());

    await run(makePage('https://shop.example.com/cart'));

    expect(auditPointerGestures).toHaveBeenCalledTimes(1);
    const [, options] = auditPointerGestures.mock.calls[0];
    expect(options.pageUrl).toBe('https://shop.example.com/cart');
  });
});

describe('pointer-gestures.check (WCAG 2.5.1) — fail branch', () => {
  function violationItem(extra = {}) {
    return {
      severity: 'violation',
      selector: '.swiper-container',
      outerHTML: '<div class="swiper-container">…</div>',
      tag: 'div',
      message: 'Gesture-dependent widget detected (carousels) — no alternative',
      ...extra,
    };
  }

  test('returns fail when auditor reports at least one violation', async () => {
    auditPointerGestures.mockResolvedValue({
      ...emptyResult(),
      violations: [violationItem()],
      summary: { total: 1, violations: 1, warnings: 0, layers: { domPattern: 1, libraryDetected: 0, axeRule: 0 } },
    });

    const result = await run(makePage());

    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].impact).toBe('serious');
  });

  test('flattens violations to the elements array with serious severity', async () => {
    auditPointerGestures.mockResolvedValue({
      ...emptyResult(),
      violations: [
        violationItem({ selector: '.carousel-a' }),
        violationItem({ selector: '.carousel-b' }),
      ],
      summary: { total: 2, violations: 2, warnings: 0, layers: { domPattern: 2, libraryDetected: 0, axeRule: 0 } },
    });

    const result = await run(makePage());
    const { elements } = result.rules[0];

    expect(elements).toHaveLength(2);
    expect(elements[0].target).toEqual(['.carousel-a']);
    expect(elements[0].severity).toBe('serious');
    expect(elements[0].html).toContain('swiper-container');
    expect(elements[0].reason).toContain('carousels');
  });

  test('reason mentions the total finding count', async () => {
    auditPointerGestures.mockResolvedValue({
      ...emptyResult(),
      violations: [violationItem(), violationItem({ selector: '.b' })],
      summary: { total: 2, violations: 2, warnings: 0, layers: { domPattern: 2, libraryDetected: 0, axeRule: 0 } },
    });

    const result = await run(makePage());
    expect(result.rules[0].reason).toMatch(/2/);
  });
});

describe('pointer-gestures.check (WCAG 2.5.1) — incomplete branch', () => {
  test('returns incomplete when only warnings are present (escape hatch / library-only)', async () => {
    auditPointerGestures.mockResolvedValue({
      ...emptyResult(),
      violations: [],
      warnings: [{
        severity: 'warning',
        selector: '.swiper-container',
        outerHTML: '<div class="swiper-container">…</div>',
        tag: 'div',
        message: 'Gesture library detected: swiper — manual gesture audit required',
      }],
      summary: { total: 1, violations: 0, warnings: 1, layers: { domPattern: 0, libraryDetected: 1, axeRule: 0 } },
    });

    const result = await run(makePage());

    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].impact).toBe('moderate');
    expect(result.rules[0].elements).toHaveLength(1);
    expect(result.rules[0].elements[0].severity).toBe('moderate');
  });

  test('mixes violations and warnings into a single elements array', async () => {
    auditPointerGestures.mockResolvedValue({
      ...emptyResult(),
      violations: [{
        severity: 'violation',
        selector: '.swiper-a',
        outerHTML: '<div class="swiper-a"></div>',
        tag: 'div',
        message: 'no alternative',
      }],
      warnings: [{
        severity: 'warning',
        selector: '.swiper-b',
        outerHTML: '<div class="swiper-b"></div>',
        tag: 'div',
        message: 'escape hatch found — manual review',
      }],
      summary: { total: 2, violations: 1, warnings: 1, layers: { domPattern: 2, libraryDetected: 0, axeRule: 0 } },
    });

    const result = await run(makePage());

    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].elements).toHaveLength(2);
    const severities = result.rules[0].elements.map(e => e.severity);
    expect(severities).toContain('serious');
    expect(severities).toContain('moderate');
  });
});

describe('pointer-gestures.check (WCAG 2.5.1) — element shape', () => {
  test('falls back to empty target array when selector is missing', async () => {
    auditPointerGestures.mockResolvedValue({
      ...emptyResult(),
      warnings: [{
        severity: 'warning',
        selector: null,
        outerHTML: null,
        tag: null,
        message: 'Library-only signal — manual review',
      }],
      summary: { total: 1, violations: 0, warnings: 1, layers: { domPattern: 0, libraryDetected: 1, axeRule: 0 } },
    });

    const result = await run(makePage());
    expect(result.rules[0].elements[0].target).toEqual([]);
    expect(result.rules[0].elements[0].html).toBeNull();
    expect(result.rules[0].elements[0].tag).toBeNull();
  });
});

describe('pointer-gestures.check (WCAG 2.5.1) — localization', () => {
  test('emits Japanese pass message when context.lang = "ja"', async () => {
    auditPointerGestures.mockResolvedValue(emptyResult());

    const result = await run(makePage(), { lang: 'ja' });
    expect(result.rules[0].reason).toContain('複雑なポインタージェスチャー');
  });

  test('emits Japanese failure message when context.lang = "ja"', async () => {
    auditPointerGestures.mockResolvedValue({
      ...emptyResult(),
      violations: [{
        severity: 'violation',
        selector: '.swiper-container',
        outerHTML: '<div></div>',
        tag: 'div',
        message: 'no alternative',
      }],
      summary: { total: 1, violations: 1, warnings: 0, layers: { domPattern: 1, libraryDetected: 0, axeRule: 0 } },
    });

    const result = await run(makePage(), { lang: 'ja' });
    expect(result.rules[0].reason).toContain('複雑なジェスチャー');
  });
});
