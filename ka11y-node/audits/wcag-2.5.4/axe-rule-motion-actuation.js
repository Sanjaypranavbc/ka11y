/**
 * @fileoverview Custom axe-core rule for static WCAG 2.5.4 Motion Actuation DOM analysis
 */

const motionActuationRule = {
  id: 'motion-actuation-2-5-4',
  selector: '*',  // runs on document body
  tags: ['wcag2a', 'wcag21a', 'wcag22a', 'wcag254', 'motion-actuation'],
  metadata: {
    description: 'Ensures device motion functionality has UI alternatives and can be disabled',
    help: 'Provide UI controls for motion-activated functionality and allow users to disable motion actuation',
    helpUrl: 'https://www.w3.org/WAI/WCAG21/Understanding/motion-actuation.html'
  },
  check: {
    id: 'motion-actuation-check',
    evaluate: function(node, options, virtualNode, context) {
      // Only runs on document.body — checks global state

      // Signal 1: ondevicemotion handler registered
      const hasMotionHandler =
        typeof window.ondevicemotion === 'function' ||
        typeof window.ondeviceorientation === 'function';

      if (!hasMotionHandler) return false; // no motion usage detected at DOM level

      // Signal 2: Check for disable control (simplified DOM check)
      const disableKeywords = ['disable motion','turn off motion','motion off',
                               'shake off','モーション無効','シェイク無効'];
      const allText = document.body.innerText.toLowerCase();
      const hasDisableText = disableKeywords.some(kw => allText.includes(kw.toLowerCase()));

      // Signal 3: Check for settings link
      const settingsLinks = [...document.querySelectorAll('a[href]')]
        .some(a => /settings|preferences|設定/.test(a.href + a.textContent));

      if (!hasDisableText && !settingsLinks) {
        return true; // violation: motion present, no disable control found
      }
      return false;
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