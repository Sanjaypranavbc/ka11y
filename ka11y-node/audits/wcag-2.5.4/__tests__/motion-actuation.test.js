/**
 * @fileoverview Tests for WCAG 2.5.4 Motion Actuation
 */
import { classifyMotionAsEssential } from '../essential-motion-classifier.js';
import { buildViolation } from '../violation-builder.js';
import { adaptToReportFormat, generateManualChecklistHTML } from '../../../reporters/wcag-254-report-adapter.js';

describe('WCAG 2.5.4 Motion Actuation', () => {

  test('classifyMotionAsEssential returns likelyEssential: true for pedometer page', async () => {
     const fakePage = {
        evaluate: jest.fn().mockResolvedValue({
           text: 'best pedometer and fitness app',
           hasCanvas: false,
           hasAriaLive: false,
           hasAriaRoles: false
        })
     };
     const result = await classifyMotionAsEssential(fakePage, {});
     expect(result.likelyEssential).toBe(true);
     expect(result.reason).toContain('fitness');
  });

  test('buildViolation sets correct severity based on essential status', () => {
     const violation = buildViolation({
        motionEvidence: { rawEvidence: [], confidence: 'high' },
        disableControl: { hasDisableControl: false, evidence: [] },
        detectedLibraries: new Map(),
        essentialClassification: { likelyEssential: true, reason: 'Test' },
        requirement: 'disable-control',
        pageUrl: 'http://test.com',
        pageLang: 'en',
        layer: 'event-handler'
     });
     expect(violation.severity).toBe('warning');
     expect(violation.impact).toBe('moderate');
     expect(violation.manualReviewRequired).toBe(true);
  });

  test('adaptToReportFormat outputs flat array with manualReviewRequired', () => {
     const auditResult = {
        manualReviewItems: [{
           severity: 'violation',
           pageUrl: 'http://test.com',
           pageLang: 'en',
           requirement: 'ui-alternative',
           message: 'Test message',
           helpUrl: 'http://help',
           motionLibrariesDetected: [],
           motionEvidence: [],
           disableControlFound: false,
           disableControlEvidence: [],
           likelyEssential: false,
           essentialReason: null,
           confidence: 'high',
           layer: 'event-handler'
        }]
     };
     const formatted = adaptToReportFormat(auditResult);
     expect(Array.isArray(formatted)).toBe(true);
     expect(formatted[0].manualReviewRequired).toBe(true);
     expect(formatted[0].rule).toBe('2.5.4 Motion Actuation');
  });

  test('generateManualChecklistHTML returns valid HTML string with 5 items', () => {
     const html = generateManualChecklistHTML({
        pageUrl: 'http://test.com',
        summary: { confidence: 'high' },
        motionLibrariesDetected: []
     });
     expect(html).toContain('<div class="wcag-254-checklist">');
     expect((html.match(/<li/g) || []).length).toBe(5);
  });

  /*
  // Integration Test Stub
  test('Integration: auditMotionActuation local HTML fixture', async () => {
     import { chromium } from 'playwright';
     import { auditMotionActuation } from '../index.js';

     const browser = await chromium.launch();
     const page = await browser.newPage();
     // Make sure you have a local fixture running that uses devicemotion
     await page.goto('http://localhost:3000/fixture-motion.html');

     const result = await auditMotionActuation(page, { pageUrl: 'http://localhost:3000/fixture-motion.html' });
     expect(result.motionDetected).toBe(true);
     expect(result.manualReviewItems.length).toBeGreaterThan(0);

     await browser.close();
  });
  */
});