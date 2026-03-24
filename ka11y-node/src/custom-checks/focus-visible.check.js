'use strict';

const SC = '2.4.7';
const RULE_ID = 'custom-focus-visible';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/focus-visible';
const MAX_ELEMENTS = 30;

async function run(page) {
  const violations = await page.evaluate((maxEl) => {
    const SELECTOR = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
    const elements = Array.from(document.querySelectorAll(SELECTOR)).slice(0, maxEl);
    const results = [];

    for (const el of elements) {
      // Capture unfocused styles
      el.blur();
      const before = window.getComputedStyle(el);
      const unfocused = {
        outlineWidth: before.outlineWidth,
        outlineStyle: before.outlineStyle,
        boxShadow:    before.boxShadow,
        borderColor:  before.borderColor,
        backgroundColor: before.backgroundColor,
      };

      el.focus({ preventScroll: true });
      const after = window.getComputedStyle(el);
      const focused = {
        outlineWidth: after.outlineWidth,
        outlineStyle: after.outlineStyle,
        boxShadow:    after.boxShadow,
        borderColor:  after.borderColor,
        backgroundColor: after.backgroundColor,
      };

      el.blur();

      const hasVisibleOutline =
        focused.outlineStyle !== 'none' && focused.outlineWidth !== '0px';
      const outlineChanged =
        focused.outlineWidth !== unfocused.outlineWidth ||
        focused.outlineStyle !== unfocused.outlineStyle;
      const boxShadowChanged = focused.boxShadow !== unfocused.boxShadow;
      const borderChanged    = focused.borderColor !== unfocused.borderColor;
      const bgChanged        = focused.backgroundColor !== unfocused.backgroundColor;

      const isVisible = hasVisibleOutline || outlineChanged || boxShadowChanged || borderChanged || bgChanged;

      if (!isVisible) {
        results.push({
          tagName: el.tagName.toLowerCase(),
          id:   el.id || null,
          html: el.outerHTML.slice(0, 200),
        });
      }
    }

    return results;
  }, MAX_ELEMENTS);

  if (violations.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: 'Focusable elements must have a visible focus indicator', impact: null, status: 'pass', reason: 'All sampled focusable elements have a visible focus indicator.', helpUrl: HELP_URL }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Focusable elements must have a visible focus indicator',
      impact: 'serious',
      status: 'fail',
      reason: `${violations.length} focusable element(s) lack a visible focus indicator: ${violations.slice(0, 3).map(v => `<${v.tagName}${v.id ? ` id="${v.id}"` : ''}>`).join(', ')}.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run };