/**
 * @fileoverview WCAG 2.5.4 Motion Actuation - Audit Orchestrator
 */
const { detectMotionEventListeners } = require('./motion-event-detector.js');
const { detectMotionLibraries } = require('./motion-library-detector.js');
const { classifyMotionAsEssential } = require('./essential-motion-classifier.js');
const { validateDisableControl } = require('./disable-control-validator.js');
const { buildViolation } = require('./violation-builder.js');
const { motionActuationRule, registerMotionActuationRule } = require('./axe-rule-motion-actuation.js');
const { injectMotionDetector, extractMotionRegistry } = require('./motion-listener-detector.js');

async function auditMotionActuation(page, options = {}) {
  const {
    pageUrl = '',
    runAxeRule = true,
    axeScriptPath = 'node_modules/axe-core/axe.min.js',
    skipIfNoMotionDetected = true
  } = options;

  let lang = 'en';
  try {
    lang = await page.evaluate(() => document.documentElement.lang || 'en');
  } catch (e) {}

  const motionEvidence = await detectMotionEventListeners(page);
  const detectedLibraries = await detectMotionLibraries(page);

  const isMotionDetected =
    motionEvidence.confidence !== 'none' ||
    detectedLibraries.size > 0 ||
    !!motionEvidence.hasAddEventListenerMotionHandler;

  if (skipIfNoMotionDetected && !isMotionDetected
      && motionEvidence.inlineScriptMatches.length === 0
      && !motionEvidence.hasOnDeviceMotionHandler
      && !motionEvidence.hasAddEventListenerMotionHandler) {
     return {
       pageUrl,
       pageLang: lang,
       motionDetected: false,
       motionEvidence,
       motionLibrariesDetected: [],
       essentialClassification: { likelyEssential: false, reason: 'no motion detected', softSignals: [] },
       disableControlFound: false,
       violations: [],
       warnings: [],
       manualReviewItems: [],
       summary: { total: 0, violations: 0, warnings: 0, requirementAFailed: false, requirementBFailed: false, confidence: 'none', layers: { eventHandler: 0, addEventListener: 0, inlineScript: 0, libraryDetected: 0, axeRule: 0 } }
     };
  }

  const essentialClassification = await classifyMotionAsEssential(page, motionEvidence);
  const disableControl = await validateDisableControl(page);

  const violations = [];
  const warnings = [];
  const manualReviewItems = [];

  let requirementAFailed = false;
  let requirementBFailed = false;

  if (isMotionDetected) {
     // UI Alternative Check.
     //
     // The accessible name of an alternative control should describe the *action*,
     // not the gesture. A shake-to-undo gesture's alternative is typically labelled
     // "Undo", not "Shake". We scan for action verbs (English + Japanese) and
     // additionally treat a control whose label or nearby text *also* mentions
     // a motion keyword as a strong signal (covers labels like "Refresh — or shake").
     let uiAlternativeFound = false;
     try {
       uiAlternativeFound = await page.evaluate(() => {
          const ACTION_PATTERNS = [
             // English action verbs that commonly substitute for motion
             'undo', 'redo', 'cancel', 'reset', 'refresh', 'reload',
             'submit', 'send', 'next', 'previous', 'back', 'skip',
             'rotate', 'flip', 'pan', 'zoom in', 'zoom out',
             'roll', 'shuffle', 'randomize', 'random', 'random number',
             // Japanese
             '元に戻す', 'やり直し', 'キャンセル', 'リセット', '更新',
             '送信', '次へ', '前へ', '戻る', 'スキップ',
             '回転', '反転', '拡大', '縮小', 'シャッフル', 'ランダム'
          ];
          const MOTION_PATTERNS = [
             'motion', 'shake', 'tilt', 'gyro', 'accelero',
             'モーション', 'シェイク', '傾き', 'ジャイロ'
          ];

          const controls = Array.from(document.querySelectorAll(
             'button, a[href], input[type="button"], input[type="submit"], [role="button"], [role="link"], [role="menuitem"]'
          ));

          for (const el of controls) {
             const label = (
                (el.textContent || '') + ' ' +
                (el.getAttribute('aria-label') || '') + ' ' +
                (el.getAttribute('title') || '') + ' ' +
                (el.getAttribute('value') || '')
             ).toLowerCase().trim();
             if (!label) continue;

             const matchesAction = ACTION_PATTERNS.some(p => label.includes(p.toLowerCase()));
             if (!matchesAction) continue;

             // Strong signal: action verb + motion keyword somewhere on the
             // element or a 2-ancestor container (e.g. "Shake or tap Undo").
             const ctx = el.closest('section, article, dialog, [role="region"], [role="dialog"], main, body');
             const ctxText = (ctx ? (ctx.textContent || '') : '').toLowerCase();
             const motionNearby = MOTION_PATTERNS.some(p => ctxText.includes(p.toLowerCase()));

             if (motionNearby || matchesAction) return true;
          }
          return false;
       });
     } catch(e) {}

     if (!uiAlternativeFound) {
        requirementAFailed = true;
        const violationA = buildViolation({
           motionEvidence, disableControl, detectedLibraries, essentialClassification,
           requirement: 'ui-alternative', pageUrl, pageLang: lang, layer: 'event-handler'
        });
        manualReviewItems.push(violationA);
        if (violationA.severity === 'violation') violations.push(violationA);
        else warnings.push(violationA);
     }

     if (!disableControl.hasDisableControl) {
        requirementBFailed = true;
        const violationB = buildViolation({
           motionEvidence, disableControl, detectedLibraries, essentialClassification,
           requirement: 'disable-control', pageUrl, pageLang: lang, layer: 'event-handler'
        });
        manualReviewItems.push(violationB);
        if (violationB.severity === 'violation') violations.push(violationB);
        else warnings.push(violationB);
     }
  }

  let axeRuleLayerCount = 0;
  if (runAxeRule && isMotionDetected) {
     try {
        await page.addScriptTag({ path: axeScriptPath });
        const evaluateFnBody = motionActuationRule.check.evaluate.toString()
          .replace(/^function\s*\([^)]*\)\s*\{/, '')
          .replace(/\}$/, '')
          .trim();

        const axeViolations = await page.evaluate(async (rule, checkId, evalFnBody, checkMeta, ruleMeta) => {
           const evaluateFn = new Function('node', 'options', 'virtualNode', 'context', evalFnBody);
           // eslint-disable-next-line no-undef
           axe.configure({
              checks: [{ id: checkId, evaluate: evaluateFn, metadata: checkMeta }],
              rules: [{ id: rule.id, selector: rule.selector, tags: rule.tags, any: [checkId], metadata: ruleMeta }]
           });
           // eslint-disable-next-line no-undef
           const res = await axe.run(document, { runOnly: { type: 'rule', values: [rule.id] } });
           return res.violations;
        }, motionActuationRule, motionActuationRule.check.id, evaluateFnBody, motionActuationRule.check.metadata, motionActuationRule.metadata);

        for (const v of axeViolations) {
           axeRuleLayerCount++;
           const axeVio = buildViolation({
              motionEvidence, disableControl, detectedLibraries, essentialClassification,
              requirement: 'disable-control', pageUrl, pageLang: lang, layer: 'axe-rule'
           });
           manualReviewItems.push(axeVio);
           if (axeVio.severity === 'violation') violations.push(axeVio);
           else warnings.push(axeVio);
        }
     } catch (e) {
        console.warn('[wcag-2.5.4] axe-core layer skipped:', e.message);
     }
  }

  return {
     pageUrl,
     pageLang: lang,
     motionDetected: isMotionDetected,
     motionEvidence,
     motionLibrariesDetected: [...detectedLibraries.keys()],
     essentialClassification,
     disableControlFound: disableControl.hasDisableControl,
     violations,
     warnings,
     manualReviewItems,
     summary: {
        total: manualReviewItems.length,
        violations: violations.length,
        warnings: warnings.length,
        requirementAFailed,
        requirementBFailed,
        confidence: motionEvidence.confidence,
        layers: {
           eventHandler: motionEvidence.hasOnDeviceMotionHandler ? 1 : 0,
           addEventListener: motionEvidence.addEventListenerMatches ? motionEvidence.addEventListenerMatches.length : 0,
           inlineScript: motionEvidence.inlineScriptMatches.length,
           libraryDetected: detectedLibraries.size,
           axeRule: axeRuleLayerCount
        }
     }
  };
}

module.exports = {
  auditMotionActuation,
  injectMotionDetector,
  extractMotionRegistry,
};
