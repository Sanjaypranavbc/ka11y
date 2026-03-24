'use strict';

const SC = '2.4.7';
const RULE_ID = 'custom-focus-visible';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/focus-visible';
const MAX_ELEMENTS = 50; // Increased from 30

async function run(page) {
  const violations = await page.evaluate((maxEl) => {
    const SELECTOR = [
      'a[href]',
      'button:not([disabled])',
      'input:not([disabled]):not([type="hidden"])',
      'select:not([disabled])',
      'textarea:not([disabled])',
      '[tabindex]:not([tabindex="-1"])',
    ].join(', ');

    const seen = new Set();
    const elements = [];
    for (const el of document.querySelectorAll(SELECTOR)) {
      if (!seen.has(el)) { seen.add(el); elements.push(el); }
      if (elements.length >= maxEl) break;
    }

    const results = [];

    for (const el of elements) {
      // Capture unfocused styles
      el.blur();
      const before = window.getComputedStyle(el);
      const unfocused = {
        outlineWidth:    before.outlineWidth,
        outlineStyle:    before.outlineStyle,
        outlineColor:    before.outlineColor,
        boxShadow:       before.boxShadow,
        borderColor:     before.borderColor,
        borderWidth:     before.borderWidth,
        backgroundColor: before.backgroundColor,
        color:           before.color,
        opacity:         before.opacity,
      };

      el.focus({ preventScroll: true });
      const after = window.getComputedStyle(el);
      const focused = {
        outlineWidth:    after.outlineWidth,
        outlineStyle:    after.outlineStyle,
        outlineColor:    after.outlineColor,
        boxShadow:       after.boxShadow,
        borderColor:     after.borderColor,
        borderWidth:     after.borderWidth,
        backgroundColor: after.backgroundColor,
        color:           after.color,
        opacity:         after.opacity,
      };
      el.blur();

      // An element passes if ANY visual property changed meaningfully on focus
      const hasVisibleOutline =
        focused.outlineStyle !== 'none' && focused.outlineWidth !== '0px';
      const outlineChanged =
        focused.outlineWidth  !== unfocused.outlineWidth  ||
        focused.outlineStyle  !== unfocused.outlineStyle  ||
        focused.outlineColor  !== unfocused.outlineColor;
      const boxShadowChanged   = focused.boxShadow       !== unfocused.boxShadow;
      const borderChanged      = focused.borderColor     !== unfocused.borderColor ||
                                 focused.borderWidth     !== unfocused.borderWidth;
      const bgChanged          = focused.backgroundColor !== unfocused.backgroundColor;
      const colorChanged       = focused.color           !== unfocused.color;
      const opacityChanged     = focused.opacity         !== unfocused.opacity;

      const isVisible = hasVisibleOutline || outlineChanged || boxShadowChanged ||
                        borderChanged || bgChanged || colorChanged || opacityChanged;

      if (!isVisible) {
        results.push({
          tagName: el.tagName.toLowerCase(),
          id:   el.id   || null,
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