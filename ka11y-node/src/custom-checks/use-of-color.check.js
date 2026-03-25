'use strict';

const SC = '1.4.1';
const RULE_ID = 'custom-use-of-color';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/use-of-color';

// Maximum links to sample (performance guard)
const MAX_LINKS = 80;

async function run(page) {
  const data = await page.evaluate((maxLinks) => {
    /**
     * Returns true if two color strings are visually distinct.
     * Compares the rgb(r,g,b) components; if all channels differ by < 15 we
     * treat them as "same colour" (allows for minor rounding differences).
     */
    function colorsDiffer(a, b) {
      const parse = s => {
        const m = s.match(/\d+/g);
        return m ? m.slice(0, 3).map(Number) : null;
      };
      const ca = parse(a), cb = parse(b);
      if (!ca || !cb) return false; // can't compare
      return ca.some((v, i) => Math.abs(v - cb[i]) > 15);
    }

    /**
     * Walk up the DOM to find the first ancestor that is NOT an <a>, collecting
     * its computed text color and background — used to compare against the link.
     */
    function getAncestorTextStyle(el) {
      let node = el.parentElement;
      while (node && node !== document.body) {
        if (node.tagName !== 'A') {
          const cs = window.getComputedStyle(node);
          return { color: cs.color, background: cs.backgroundColor };
        }
        node = node.parentElement;
      }
      return null;
    }

    // Candidate selectors: links that appear inside typical text containers
    const SELECTORS = [
      'p a[href]',
      'li a[href]',
      'td a[href]',
      'th a[href]',
      'blockquote a[href]',
      'article a[href]',
      'section a[href]',
      'dd a[href]',
    ].join(', ');

    const seen = new Set();
    const violations = [];
    const checked = [];

    for (const link of document.querySelectorAll(SELECTORS)) {
      if (seen.has(link)) continue;
      seen.add(link);
      if (seen.size > maxLinks) break;

      const linkText = (link.textContent || '').trim();
      if (!linkText) continue; // skip icon-only links — no text to confuse with surrounding text

      const ls = window.getComputedStyle(link);

      // 1. Text decoration check (underline / overline / line-through are visual cues)
      const hasTextDecoration = ls.textDecorationLine !== 'none' && ls.textDecorationLine !== '';

      // 2. Bottom border (some designs fake underline via border-bottom)
      const borderBottomWidth = parseFloat(ls.borderBottomWidth) || 0;
      const hasBorderBottom   = borderBottomWidth > 0 && ls.borderBottomStyle !== 'none';

      // 3. Outline (rare but valid)
      const outlineWidth = parseFloat(ls.outlineWidth) || 0;
      const hasOutline   = outlineWidth > 0 && ls.outlineStyle !== 'none';

      // 4. Background colour change vs ancestor
      const ancestor = getAncestorTextStyle(link);
      const hasBgChange = ancestor
        ? colorsDiffer(ls.backgroundColor, ancestor.background)
        : ls.backgroundColor !== 'rgba(0, 0, 0, 0)' && ls.backgroundColor !== 'transparent';

      // 5. Font-weight substantially heavier than ancestor
      const linkFontWeight     = parseInt(ls.fontWeight, 10) || 400;
      const ancestorFontWeight = ancestor ? (parseInt(window.getComputedStyle(link.parentElement).fontWeight, 10) || 400) : 400;
      const hasFontWeightCue   = linkFontWeight >= ancestorFontWeight + 200;

      // 6. Font style difference (e.g. italic vs normal)
      const hasFontStyleCue = ancestor
        ? ls.fontStyle !== window.getComputedStyle(link.parentElement).fontStyle
        : false;

      const hasNonColorCue = hasTextDecoration || hasBorderBottom || hasOutline ||
                             hasBgChange || hasFontWeightCue || hasFontStyleCue;

      if (!hasNonColorCue) {
        // Confirm the link colour actually differs from surrounding text (it IS being
        // distinguished by colour, just without any other cue)
        const colorDiffers = ancestor ? colorsDiffer(ls.color, ancestor.color) : true;
        if (colorDiffers) {
          violations.push({
            html: link.outerHTML.slice(0, 150),
            id:   link.id || null,
            text: linkText.slice(0, 60),
          });
        }
      }

      checked.push(link.id || linkText.slice(0, 30));
    }

    return { violations, checkedCount: checked.length };
  }, MAX_LINKS);

  if (data.violations.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Color must not be the only visual means of conveying information',
        impact: null,
        status: 'pass',
        reason: data.checkedCount > 0
          ? `${data.checkedCount} inline link(s) checked — all have a non-color visual cue (underline, border, background, or font weight).`
          : 'No inline text links found to check.',
        helpUrl: HELP_URL,
      }],
    };
  }

  const sample = data.violations.slice(0, 3).map(v => `"${v.text}"`).join(', ');

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Color must not be the only visual means of conveying information',
      impact: 'serious',
      status: 'fail',
      reason: `${data.violations.length} inline link(s) appear to be distinguished from surrounding text by colour alone (no underline, border, background, or font-weight difference): ${sample}. Add a non-color visual cue such as underline or border-bottom.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };