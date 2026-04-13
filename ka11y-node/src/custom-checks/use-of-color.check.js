'use strict';

const {
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '1.4.1';
const RULE_ID = 'custom-use-of-color';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/use-of-color';

// Maximum links to sample (performance guard)
const MAX_LINKS = 150;

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);
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
     * its computed text color, background, fontWeight, and fontStyle — used to
     * compare against the link's own styles.
     */
    function getAncestorTextStyle(el) {
      let node = el.parentElement;
      while (node && node !== document.body) {
        if (node.tagName !== 'A') {
          const cs = window.getComputedStyle(node);
          return {
            color:       cs.color,
            background:  cs.backgroundColor,
            fontWeight:  cs.fontWeight,
            fontStyle:   cs.fontStyle,
          };
        }
        node = node.parentElement;
      }
      return null;
    }

    // Candidate selectors: links that appear inside typical text containers.
    // B12: 'section a[href]' removed — it matched virtually every link on modern
    // pages (nav cards, hero CTAs, standalone card links) because almost all content
    // lives in <section>. WCAG 1.4.1 applies to links within a block of TEXT that are
    // distinguished from surrounding non-link text solely by colour; standalone links
    // with no surrounding text are not subject to the criterion.
    // 'article a[href]' narrowed to 'article > p a[href]' for the same reason.
    const SELECTORS = [
      'p a[href]',
      'li a[href]',
      'td a[href]',
      'th a[href]',
      'blockquote a[href]',
      'article > p a[href]',
      'dd a[href]',
      'section > p a[href]',
      'svg a[href]',
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
      // When there is no non-<a> ancestor available, compare against the
      // transparent sentinel via colorsDiffer so all browser-normalised
      // transparent string variants (rgba(0,0,0,0), rgba(0, 0, 0, 0),
      // transparent) are handled uniformly by the digit-extraction parser.
      const hasBgChange = ancestor
        ? colorsDiffer(ls.backgroundColor, ancestor.background)
        : colorsDiffer(ls.backgroundColor, 'rgba(0, 0, 0, 0)');

      // 5. Font-weight substantially heavier than ancestor
      // Use ancestor.fontWeight (from getAncestorTextStyle) — NOT link.parentElement
      // which could itself be an <a> element and give incorrect comparison values.
      const linkFontWeight     = parseInt(ls.fontWeight, 10) || 400;
      const ancestorFontWeight = ancestor ? (parseInt(ancestor.fontWeight, 10) || 400) : 400;
      // B17: threshold reduced from 200 to 100. Many design systems use 400→500
      // (normal→medium) as a visually meaningful non-color cue; the original 200-unit
      // delta required 400→600 (semi-bold) and produced false violations for those systems.
      const hasFontWeightCue   = linkFontWeight >= ancestorFontWeight + 100;

      // 6. Font style difference (e.g. italic vs normal)
      const hasFontStyleCue = ancestor
        ? ls.fontStyle !== ancestor.fontStyle
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
          ? _t(sharedContext, '{count} inline link(s) checked — all have a non-color visual cue (underline, border, background, or font weight).', 'インラインリンク {count} 件を確認しましたが、すべてに色以外の視覚的手がかり（下線、境界線、背景、文字の太さなど）がありました。', { count: data.checkedCount })
          : _t(sharedContext, 'No inline text links found to check.', '確認対象のインラインテキストリンクは見つかりませんでした。'),
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
      reason: _t(sharedContext, '{count} inline link(s) appear to be distinguished from surrounding text by colour alone (no underline, border, background, or font-weight difference): {sample}. Add a non-color visual cue such as underline or border-bottom.', '周囲のテキストとの差が色だけになっているように見えるインラインリンクが {count} 件検出されました（下線、境界線、背景、文字の太さの違いなし）: {sample}。下線や border-bottom など、色以外の視覚的手がかりを追加してください。', { count: data.violations.length, sample }),
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
