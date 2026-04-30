/**
 * @fileoverview Unit + integration-stub tests for the WCAG 2.5.1 Pointer Gestures module.
 *
 * Run with:
 *   NODE_OPTIONS='--experimental-vm-modules' npx jest audits/wcag-2.5.1/__tests__/pointer-gestures.test.js
 *
 * The integration test at the bottom requires Playwright and a local HTML fixture;
 * it is commented out and can be enabled by replacing FIXTURE_URL below.
 */

const { getSelectorBank } = require('../multilingual-selectors.js');
const { buildViolation } = require('../violation-builder.js');
const { adaptToReportFormat } = require('../../../reporters/wcag-251-report-adapter.js');

/* ─────────────────────────────────────────────────────────────────────────
   1. getSelectorBank — Japanese returns merged selectors
   ───────────────────────────────────────────────────────────────────────── */

describe('getSelectorBank', () => {
  test('returns English-only selectors for lang="en"', () => {
    const bank = getSelectorBank('en');
    expect(Array.isArray(bank.carousels)).toBe(true);
    expect(bank.carousels.length).toBeGreaterThan(0);
    // Japanese-only selectors must not appear
    expect(bank.carousels).not.toContain('.カルーセル');
    expect(bank.draggable).not.toContain('.ドラッグ');
  });

  test('returns merged EN+JA selectors for lang="ja"', () => {
    const bank = getSelectorBank('ja');
    expect(bank.carousels).toContain('.カルーセル');
    expect(bank.carousels).toContain('.swiper-container'); // EN selector present too
    expect(bank.draggable).toContain('.ドラッグ');
    expect(bank.draggable).toContain('[draggable="true"]');
  });

  test('returns merged EN+JA selectors for lang="ja-JP"', () => {
    const bank = getSelectorBank('ja-JP');
    expect(bank.carousels).toContain('.カルーセル');
    expect(bank.touchGestureWidgets).toContain('[data-スワイプ]');
  });

  test('includes all five required categories', () => {
    const bank = getSelectorBank('en');
    const required = ['carousels', 'draggable', 'mapEmbeds', 'touchGestureWidgets', 'pathBasedInteractions'];
    for (const cat of required) {
      expect(bank).toHaveProperty(cat);
      expect(Array.isArray(bank[cat])).toBe(true);
    }
  });

  test('Japanese bank has more selectors than English for carousels', () => {
    const en = getSelectorBank('en');
    const ja = getSelectorBank('ja');
    expect(ja.carousels.length).toBeGreaterThan(en.carousels.length);
  });
});

/* ─────────────────────────────────────────────────────────────────────────
   2. buildViolation — all required fields present
   ───────────────────────────────────────────────────────────────────────── */

describe('buildViolation', () => {
  const mockFinding = {
    category:    'carousels',
    selector:    '.swiper-container',
    outerHTML:   '<div class="swiper-container">...</div>',
    boundingBox: { x: 10, y: 20, width: 300, height: 200 },
    rawSelector: '.swiper-container',
  };
  const mockEscapeHatch = { hasAlternative: false, evidence: [] };
  const mockLibs        = new Set(['swiper']);

  let violation;
  beforeEach(() => {
    violation = buildViolation({
      finding:           mockFinding,
      escapeHatch:       mockEscapeHatch,
      detectedLibraries: mockLibs,
      pageUrl:           'https://example.com',
      pageLang:          'en',
      layer:             'dom-pattern',
    });
  });

  const requiredFields = [
    'ruleId', 'wcag', 'wcagLevel', 'wcagVersion', 'impact', 'layer',
    'pageUrl', 'pageLang', 'category', 'element', 'selector', 'boundingBox',
    'escapeHatchFound', 'escapeHatchEvidence', 'gestureLibrariesDetected',
    'message', 'severity', 'helpUrl', 'timestamp',
  ];

  test.each(requiredFields)('has required field: %s', (field) => {
    expect(violation).toHaveProperty(field);
  });

  test('ruleId is always "wcag-2.5.1-pointer-gestures"', () => {
    expect(violation.ruleId).toBe('wcag-2.5.1-pointer-gestures');
  });

  test('wcag is "2.5.1"', () => {
    expect(violation.wcag).toBe('2.5.1');
  });

  test('wcagLevel is "AA"', () => {
    expect(violation.wcagLevel).toBe('AA');
  });

  test('severity is "violation" when no escape hatch', () => {
    expect(violation.severity).toBe('violation');
  });

  test('severity is "warning" when escape hatch found', () => {
    const withHatch = buildViolation({
      finding:           mockFinding,
      escapeHatch:       { hasAlternative: true, evidence: ['Sibling <button> found'] },
      detectedLibraries: mockLibs,
      pageUrl:           'https://example.com',
      pageLang:          'en',
      layer:             'dom-pattern',
    });
    expect(withHatch.severity).toBe('warning');
    expect(withHatch.escapeHatchFound).toBe(true);
  });

  test('gestureLibrariesDetected is an array', () => {
    expect(Array.isArray(violation.gestureLibrariesDetected)).toBe(true);
    expect(violation.gestureLibrariesDetected).toContain('swiper');
  });

  test('timestamp is a valid ISO 8601 string', () => {
    expect(() => new Date(violation.timestamp)).not.toThrow();
    expect(isNaN(new Date(violation.timestamp).getTime())).toBe(false);
  });

  test('message mentions category', () => {
    expect(violation.message).toContain('carousels');
  });
});

/* ─────────────────────────────────────────────────────────────────────────
   3. adaptToReportFormat — flat array output
   ───────────────────────────────────────────────────────────────────────── */

describe('adaptToReportFormat', () => {
  const makeAuditResult = (extras = {}) => ({
    pageUrl:                  'https://example.com',
    pageLang:                 'en',
    gestureLibrariesDetected: ['swiper'],
    domFindingsCount:         1,
    violations: [
      {
        ruleId:                   'wcag-2.5.1-pointer-gestures',
        severity:                 'violation',
        pageUrl:                  'https://example.com',
        pageLang:                 'en',
        category:                 'carousels',
        selector:                 '.swiper-container',
        element:                  '<div class="swiper-container">',
        boundingBox:              { x: 0, y: 0, width: 400, height: 200 },
        escapeHatchFound:         false,
        escapeHatchEvidence:      [],
        gestureLibrariesDetected: ['swiper'],
        message:                  'Gesture-dependent widget detected (carousels) — no alternative',
        helpUrl:                  'https://www.w3.org/WAI/WCAG22/Understanding/pointer-gestures',
        layer:                    'dom-pattern',
        ...extras,
      },
    ],
    warnings: [],
    summary: { total: 1, violations: 1, warnings: 0, layers: { domPattern: 1, libraryDetected: 0, axeRule: 0 } },
  });

  test('returns an array', () => {
    const items = adaptToReportFormat(makeAuditResult());
    expect(Array.isArray(items)).toBe(true);
  });

  test('each item has required top-level fields', () => {
    const [item] = adaptToReportFormat(makeAuditResult());
    const required = ['id', 'rule', 'level', 'severity', 'url', 'lang', 'element', 'selector', 'message', 'helpUrl', 'details'];
    for (const f of required) expect(item).toHaveProperty(f);
  });

  test('id is prefixed with "wcag-2.5.1-"', () => {
    const [item] = adaptToReportFormat(makeAuditResult());
    expect(item.id).toMatch(/^wcag-2\.5\.1-\d+$/);
  });

  test('rule is "2.5.1 Pointer Gestures"', () => {
    const [item] = adaptToReportFormat(makeAuditResult());
    expect(item.rule).toBe('2.5.1 Pointer Gestures');
  });

  test('level is "AA"', () => {
    const [item] = adaptToReportFormat(makeAuditResult());
    expect(item.level).toBe('AA');
  });

  test('details contains all required sub-fields', () => {
    const [item] = adaptToReportFormat(makeAuditResult());
    const detailsFields = ['category', 'escapeHatchFound', 'escapeHatchEvidence', 'gestureLibraries', 'layer', 'boundingBox'];
    for (const f of detailsFields) expect(item.details).toHaveProperty(f);
  });

  test('violations and warnings both appear in the flat array', () => {
    const result = makeAuditResult();
    result.warnings = [{
      ...result.violations[0],
      severity: 'warning',
      escapeHatchFound: true,
    }];
    const items = adaptToReportFormat(result);
    expect(items).toHaveLength(2);
    expect(items.some(i => i.severity === 'violation')).toBe(true);
    expect(items.some(i => i.severity === 'warning')).toBe(true);
  });

  test('returns empty array for null input', () => {
    expect(adaptToReportFormat(null)).toEqual([]);
  });

  test('returns empty array for empty violations + warnings', () => {
    const result = makeAuditResult();
    result.violations = [];
    expect(adaptToReportFormat(result)).toEqual([]);
  });
});

/* ─────────────────────────────────────────────────────────────────────────
   4. Integration test stub (commented out — requires Playwright + fixture)
   ───────────────────────────────────────────────────────────────────────── */

/*
const { chromium } = require('playwright');
const { auditPointerGestures } = require('../index.js');
const { adaptToReportFormat } = require('../../../reporters/wcag-251-report-adapter.js');

const FIXTURE_URL = 'http://localhost:3000/fixture-swiper.html';

describe('Integration: auditPointerGestures against local fixture', () => {
  let browser, page;

  beforeAll(async () => {
    browser = await chromium.launch();
    page    = await browser.newPage();
    await page.goto(FIXTURE_URL, { waitUntil: 'networkidle' });
  }, 30_000);

  afterAll(() => browser?.close());

  test('detects Swiper carousel and reports at least one finding', async () => {
    const result = await auditPointerGestures(page, {
      pageUrl:    FIXTURE_URL,
      runAxeRule: true,
    });

    expect(result.domFindingsCount).toBeGreaterThan(0);
    expect(result.summary.total).toBeGreaterThan(0);
  });

  test('adaptToReportFormat produces flat array from carousel fixture', async () => {
    const result = await auditPointerGestures(page, { pageUrl: FIXTURE_URL });
    const items  = adaptToReportFormat(result);
    expect(Array.isArray(items)).toBe(true);
    if (items.length > 0) {
      expect(items[0]).toHaveProperty('id');
      expect(items[0]).toHaveProperty('details');
    }
  });
});
*/
