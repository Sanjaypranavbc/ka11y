/**
 * @fileoverview Tests for WCAG 2.5.4 Motion Actuation
 */
const { classifyMotionAsEssential } = require('../essential-motion-classifier.js');
const { buildViolation } = require('../violation-builder.js');
const { adaptToReportFormat, generateManualChecklistHTML } = require('../../../../reporters/wcag-254-report-adapter.js');
const { motionActuationRule } = require('../axe-rule-motion-actuation.js');

// Real-DOM polarity tests use Puppeteer (Playwright is not installed in this repo).
const puppeteer = require('puppeteer');
const axeCore   = require('axe-core');

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

  // ── axe rule polarity (real DOM via Puppeteer) ──────────────────────────
  describe('axe-rule-motion-actuation evaluate() polarity', () => {
    let browser;
    let page;

    // Stringified rule definition — passed into the page so the in-page axe
    // instance can re-construct the check.evaluate function.
    const ruleConfig = {
      ruleId:        motionActuationRule.id,
      ruleSelector:  motionActuationRule.selector,
      ruleTags:      motionActuationRule.tags,
      ruleMetadata:  motionActuationRule.metadata,
      checkId:       motionActuationRule.check.id,
      checkMetadata: motionActuationRule.check.metadata,
      evaluateBody:  motionActuationRule.check.evaluate.toString(),
    };

    beforeAll(async () => {
      browser = await puppeteer.launch({ args: ['--no-sandbox', '--disable-setuid-sandbox'] });
    }, 30000);

    afterAll(async () => {
      if (browser) await browser.close();
    });

    beforeEach(async () => {
      page = await browser.newPage();
    });

    afterEach(async () => {
      if (page) await page.close();
    });

    /**
     * Loads HTML, injects axe-core, registers the motion-actuation rule on
     * the in-page axe instance, and returns axe.run() results filtered to
     * the rule under test.
     */
    async function runRuleOnHTML(html, beforeRunScript = '') {
      await page.setContent(`<!doctype html><html><body>${html}</body></html>`,
        { waitUntil: 'domcontentloaded' });
      await page.addScriptTag({ content: axeCore.source });
      if (beforeRunScript) {
        await page.evaluate((s) => {
          // eslint-disable-next-line no-new-func
          new Function(s)();
        }, beforeRunScript);
      }
      const results = await page.evaluate((cfg) => {
        // Reconstruct evaluate function inside the page.
        // eslint-disable-next-line no-new-func
        const evaluateFn = new Function(`return (${cfg.evaluateBody});`)();
        // eslint-disable-next-line no-undef
        axe.configure({
          checks: [{
            id:       cfg.checkId,
            evaluate: evaluateFn,
            metadata: cfg.checkMetadata,
          }],
          rules: [{
            id:       cfg.ruleId,
            selector: cfg.ruleSelector,
            tags:     cfg.ruleTags,
            any:      [cfg.checkId],
            metadata: cfg.ruleMetadata,
          }],
        });
        // eslint-disable-next-line no-undef
        return axe.run(document, {
          runOnly: { type: 'rule', values: [cfg.ruleId] },
        });
      }, ruleConfig);

      // Filter to just our rule (defensive; runOnly should already do this).
      const filterById = (arr) =>
        (arr || []).filter(r => r.id === ruleConfig.ruleId);
      return {
        violations: filterById(results.violations),
        passes:     filterById(results.passes),
        incomplete: filterById(results.incomplete),
      };
    }

    test('passes when no motion handler is registered', async () => {
      const out = await runRuleOnHTML('<p>Static page, no motion.</p>');
      expect(out.violations).toHaveLength(0);
      expect(out.passes.length + out.incomplete.length).toBeGreaterThan(0);
    }, 30000);

    test('fails when motion handler is registered and no disable surface exists', async () => {
      const out = await runRuleOnHTML(
        '<p>fun shake game</p>',
        'window.ondevicemotion = function () {};'
      );
      expect(out.violations.length).toBeGreaterThanOrEqual(1);
    }, 30000);

    test('passes when motion handler + "disable motion" copy is present', async () => {
      const out = await runRuleOnHTML(
        '<p>Tap to disable motion controls</p>',
        'window.ondevicemotion = function () {};'
      );
      expect(out.violations).toHaveLength(0);
    }, 30000);

    test('passes when motion handler + a settings link is present', async () => {
      const out = await runRuleOnHTML(
        '<p>shake the phone</p><a href="/settings">Settings</a>',
        'window.ondeviceorientation = function () {};'
      );
      expect(out.violations).toHaveLength(0);
    }, 30000);
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
