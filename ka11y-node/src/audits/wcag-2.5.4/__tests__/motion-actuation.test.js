/**
 * @fileoverview Tests for WCAG 2.5.4 Motion Actuation
 */
const { classifyMotionAsEssential } = require('../essential-motion-classifier.js');
const { buildViolation } = require('../violation-builder.js');
const { adaptToReportFormat, generateManualChecklistHTML } = require('../../../../reporters/wcag-254-report-adapter.js');
const { motionActuationRule } = require('../axe-rule-motion-actuation.js');

describe('WCAG 2.5.4 Motion Actuation', () => {

  test('classifyMotionAsEssential returns likelyEssential: false but includes soft signals for pedometer page without opt-in', async () => {
     const fakePage = {
        evaluate: jest.fn().mockResolvedValue({
           hasExplicitOptIn: false,
           text: 'best pedometer and fitness app',
           hasCanvas: false,
           hasAriaLive: false,
           hasAriaRoles: false
        })
     };
     const result = await classifyMotionAsEssential(fakePage, {});
     expect(result.likelyEssential).toBe(false);
     expect(result.softSignals).toContain('Pedometer / fitness context detected');
  });

  test('classifyMotionAsEssential returns likelyEssential: true when explicit opt-in is present', async () => {
     const fakePage = {
        evaluate: jest.fn().mockResolvedValue({
           hasExplicitOptIn: true,
           text: 'random page',
           hasCanvas: false,
           hasAriaLive: false,
           hasAriaRoles: false
        })
     };
     const result = await classifyMotionAsEssential(fakePage, {});
     expect(result.likelyEssential).toBe(true);
     expect(result.reason).toContain('Explicit opt-in attribute');
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

  // ── axe rule polarity (regression: previously inverted) ──────────────────
  describe('axe-rule-motion-actuation evaluate() polarity', () => {
    function runEvaluateIn(documentMock, windowMock) {
      // Mirror the way axe-core invokes the check inside the page: bind
      // `document` and `window` into scope and call the function body.
      const fn = motionActuationRule.check.evaluate;
      const ctx = { document: documentMock, window: windowMock };
      // eslint-disable-next-line no-new-func
      return new Function('document', 'window', `return (${fn.toString()}).call(this, null, {}, null, null);`)
        .call(ctx, documentMock, windowMock);
    }

    test('passes when no motion handler is registered', () => {
      const result = runEvaluateIn(
        { body: { innerText: '' }, querySelectorAll: () => [] },
        { ondevicemotion: null, ondeviceorientation: null }
      );
      expect(result).toBe(true);
    });

    test('fails when motion handler is registered and no disable surface exists', () => {
      const result = runEvaluateIn(
        { body: { innerText: 'fun shake game' }, querySelectorAll: () => [] },
        { ondevicemotion: function () {} }
      );
      expect(result).toBe(false);
    });

    test('passes when motion handler + "disable motion" copy is present', () => {
      const result = runEvaluateIn(
        { body: { innerText: 'Tap to disable motion controls' }, querySelectorAll: () => [] },
        { ondevicemotion: function () {} }
      );
      expect(result).toBe(true);
    });

    test('passes when motion handler + a settings link is present', () => {
      const result = runEvaluateIn(
        {
          body: { innerText: 'shake the phone' },
          querySelectorAll: () => [{ href: '/settings', textContent: 'Settings' }]
        },
        { ondeviceorientation: function () {} }
      );
      expect(result).toBe(true);
    });
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