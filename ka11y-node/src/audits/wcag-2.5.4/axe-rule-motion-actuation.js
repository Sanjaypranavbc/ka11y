/**
 * @fileoverview Custom axe-core rule for static WCAG 2.5.4 Motion Actuation DOM analysis.
 *
 * axe convention: `evaluate()` returns `true` to mean the check **passed** and
 * `false` to mean it **failed**. With `any: [checkId]`, axe reports a violation
 * when the only "any" check returns `false`. Earlier versions of this file
 * inverted the semantics — the rule now follows the convention.
 *
 * Decision table (motion handler present at `window.on*`):
 *   | hasMotionHandler | hasDisableSignal | result   |
 *   |------------------|------------------|----------|
 *   | false            |        —         | pass (no motion at all) |
 *   | true             | true             | pass (some disable surface present) |
 *   | true             | false            | fail (motion detected, no disable surface) |
 */

const motionActuationRule = {
  id: 'motion-actuation-2-5-4',
  selector: 'body',
  tags: ['wcag2a', 'wcag21a', 'wcag22a', 'wcag254', 'motion-actuation'],
  metadata: {
    description: 'Ensures device motion functionality has UI alternatives and can be disabled',
    help: 'Provide UI controls for motion-activated functionality and allow users to disable motion actuation',
    helpUrl: 'https://www.w3.org/WAI/WCAG21/Understanding/motion-actuation.html'
  },
  check: {
    id: 'motion-actuation-check',
    evaluate: function (node, options, virtualNode, context) {
      // Signal 1: ondevicemotion handler registered on a property
      const hasMotionHandler =
        typeof window.ondevicemotion === 'function' ||
        typeof window.ondeviceorientation === 'function';

      // No motion handler at all → nothing to flag, the rule passes.
      if (!hasMotionHandler) return true;

      // Signal 2: visible disable control / settings link.
      const disableKeywords = [
        'disable motion', 'turn off motion', 'motion off',
        'shake off', 'モーション無効', 'シェイク無効'
      ];
      const allText = (document.body.innerText || '').toLowerCase();
      const hasDisableText = disableKeywords.some(kw => allText.includes(kw.toLowerCase()));

      const settingsLinks = Array.from(document.querySelectorAll('a[href]'))
        .some(a => /settings|preferences|設定/i.test((a.href || '') + (a.textContent || '')));

      // Motion present + no disable surface → check fails (axe will report a violation).
      if (!hasDisableText && !settingsLinks) return false;
      return true;
    },
    metadata: {
      impact: 'critical',
      messages: {
        pass: 'Motion actuation provides a UI alternative and can be disabled',
        fail: 'Motion actuation detected with no visible disable control or UI alternative'
      }
    }
  }
};

/**
 * Registers the custom motion actuation rule with an axe-core instance.
 * @param {Object} axeInstance - The axe-core object
 */
function registerMotionActuationRule(axeInstance) {
  axeInstance.configure({
    checks: [motionActuationRule.check],
    rules: [{
      id: motionActuationRule.id,
      selector: motionActuationRule.selector,
      tags: motionActuationRule.tags,
      any: [motionActuationRule.check.id],
      metadata: motionActuationRule.metadata
    }]
  });
}

module.exports = { motionActuationRule, registerMotionActuationRule };
