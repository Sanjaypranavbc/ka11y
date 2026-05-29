'use strict';

const {
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '2.4.7';
const RULE_ID = 'custom-focus-visible';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/focus-visible';
const MAX_ELEMENTS = 2000;
// Settle delay: allow CSS transitions and React/Vue re-renders to apply before capturing styles
const SETTLE_MS = 80;

const SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);
  // Collect element metadata once — include stable selectors (B11: DOM index shifts when
  // focus triggers DOM mutations; stable selectors survive re-queries after mutations).
  const elements = await page.evaluate((sel, max) => {
    const seen = new Set();
    const items = [];
    const idCounts = {};
    for (const el of document.querySelectorAll('[id]')) {
      idCounts[el.id] = (idCounts[el.id] || 0) + 1;
    }
    for (const el of document.querySelectorAll(sel)) {
      if (seen.has(el)) continue;
      seen.add(el);
      let stableSel = null;
      if (el.id && idCounts[el.id] === 1) stableSel = `#${CSS.escape(el.id)}`;
      items.push({ 
        idx: items.length, 
        stableSel, 
        tagName: el.tagName.toLowerCase(), 
        tag: el.tagName.toUpperCase(),
        target: stableSel ? [stableSel] : [el.tagName.toLowerCase()],
        id: el.id || null, 
        html: el.outerHTML.slice(0, 200) 
      });
      if (items.length >= max) break;
    }
    return items;
  }, SELECTOR, MAX_ELEMENTS);

  // Static CSS scan: detect global :focus { outline: none } resets without :focus-visible restoration
  const cssFindings = await page.evaluate(() => {
    const OUTLINE_RESET_RE = /outline\s*:\s*(?:none|0(?:px)?)\s*[;!]/i;
    const focusSelectors    = new Set();
    const focusVisSelectors = new Set();
    const issues            = [];

    function scanRules(rules) {
      if (!rules) return;
      for (const rule of rules) {
        try {
          if (rule.type === CSSRule.STYLE_RULE) {
            const sel = rule.selectorText || '';
            if (/:focus\b/.test(sel) && !/:focus-visible\b/.test(sel)) {
              if (OUTLINE_RESET_RE.test(rule.cssText)) focusSelectors.add(sel);
            }
            if (/:focus-visible\b/.test(sel)) focusVisSelectors.add(sel);
          } else if (rule.cssRules) {
            scanRules(rule.cssRules);
          }
        } catch (_) {}
      }
    }

    Array.from(document.styleSheets).forEach(sheet => {
      try { scanRules(sheet.cssRules); } catch (_) {}
    });

    for (const sel of focusSelectors) {
      const rootSel = sel.replace(/:focus\b[^,]*/g, '').trim().replace(/,\s*$/, '').trim();
      const hasRestoration = [...focusVisSelectors].some(vs => {
        const vsRoot = vs.replace(/:focus-visible\b[^,]*/g, '').trim().replace(/,\s*$/, '').trim();
        return vsRoot === rootSel || vsRoot === '' || rootSel === '';
      });
      if (!hasRestoration) {
        issues.push({
          type: 'focus-outline-reset',
          selector: sel,
          message: `"${sel}" resets outline without a :focus-visible restoration`,
        });
      }
    }
    return issues;
  });

  const violations = [];

  for (const el of elements) {
    // ── L-1: collapsed per-element round-trip ─────────────────────────────────
    // The original implementation made FOUR `page.evaluate()` calls per element
    // — capture-unfocused, focus, capture-focused, blur — each paying the CDP
    // round-trip cost (~10–50 ms over the wire). With 5 interactive checks ×
    // hundreds of elements that's the dominant per-page cost on heavy sites
    // (see ka11y-docs/internals/stage-timing.mdx; this was the kao.com
    // bottleneck).
    //
    // The whole dance now runs browser-side in ONE evaluate. The two
    // SETTLE_MS waits are kept (CSS transitions / React re-renders still
    // need them) but they happen inside the page context, so the cost is
    // 1 CDP RT + 160 ms wait instead of 4 CDP RTs + 160 ms wait.
    //
    // Stable-selector + idx fallback is preserved verbatim (B11: DOM index
    // shifts when focus triggers mutations).
    const sample = await page.evaluate(
      ({ sel, idx, stableSel, settleMs }) => {
        const findEl = () =>
          stableSel
            ? (document.querySelector(stableSel) ||
               Array.from(document.querySelectorAll(sel))[idx])
            : Array.from(document.querySelectorAll(sel))[idx];

        const capture = (node) => {
          const cs = window.getComputedStyle(node);
          const csAfter = window.getComputedStyle(node, '::after');
          return {
            outlineWidth:    cs.outlineWidth,
            outlineStyle:    cs.outlineStyle,
            outlineColor:    cs.outlineColor,
            boxShadow:       cs.boxShadow,
            borderColor:     cs.borderColor,
            borderWidth:     cs.borderWidth,
            backgroundColor: cs.backgroundColor,
            color:           cs.color,
            transform:       cs.transform,
            afterContent:    csAfter.content,
            afterBoxShadow:  csAfter.boxShadow,
            afterBorder:     csAfter.border,
            afterOpacity:    csAfter.opacity,
          };
        };

        const e1 = findEl();
        if (!e1) return null;

        // Unfocused snapshot (post-blur) — preserves original semantics.
        e1.blur();
        const unfocused = capture(e1);

        // Focus and wait for transitions to settle.
        e1.focus({ preventScroll: true });

        return new Promise((resolve) => {
          setTimeout(() => {
            // Re-resolve the element after the focus mutation in case the
            // page's onfocus handler re-rendered subtree (the original
            // stableSel-fallback path was specifically for this case).
            const e2 = findEl();
            if (!e2) {
              resolve({ unfocused, focused: null });
              return;
            }
            const focused = capture(e2);
            e2.blur();
            // Second settle so the NEXT iteration's `unfocused` capture
            // isn't tainted by the still-propagating focus removal.
            setTimeout(() => resolve({ unfocused, focused }), settleMs);
          }, settleMs);
        });
      },
      { sel: SELECTOR, idx: el.idx, stableSel: el.stableSel, settleMs: SETTLE_MS },
    );

    if (!sample) continue;
    const { unfocused, focused } = sample;
    if (!unfocused || !focused) continue;

    // ── Step 4: Determine if a visual change occurred ─────────────────────────
    // Verify the focused outline is not transparent before counting it visible.
    // Covers: transparent keyword, rgba/hsla with alpha=0, inherit/initial/unset/revert.
    const _oc = (focused.outlineColor || '').trim();
    const _outlineColorInvisible =
      /^(transparent|inherit|initial|unset|revert)$/i.test(_oc) ||
      /^rgba?\s*\([^)]*,\s*0\.?0*\s*\)$/i.test(_oc) ||
      /^hsla?\s*\([^)]*,\s*0%?\s*\)$/i.test(_oc);
    const outlineActuallyVisible =
      focused.outlineStyle !== 'none' &&
      focused.outlineWidth !== '0px' &&
      !_outlineColorInvisible;
    const hasVisibleOutline = outlineActuallyVisible;
    const outlineChanged =
      (focused.outlineWidth  !== unfocused.outlineWidth  ||
       focused.outlineStyle  !== unfocused.outlineStyle  ||
       focused.outlineColor  !== unfocused.outlineColor) &&
      outlineActuallyVisible;
    const boxShadowChanged   = focused.boxShadow       !== unfocused.boxShadow &&
                               focused.boxShadow       !== 'none';
    const borderChanged      = focused.borderColor     !== unfocused.borderColor ||
                               focused.borderWidth     !== unfocused.borderWidth;
    const bgChanged          = focused.backgroundColor !== unfocused.backgroundColor;
    const colorChanged       = focused.color           !== unfocused.color;
    const transformChanged   = focused.transform       !== unfocused.transform;
    const afterChanged       = focused.afterContent    !== unfocused.afterContent ||
                               focused.afterBoxShadow  !== unfocused.afterBoxShadow ||
                               focused.afterBorder     !== unfocused.afterBorder ||
                               focused.afterOpacity    !== unfocused.afterOpacity;
    // B16: opacity change alone is NOT a visible focus indicator — it reflects CSS animations
    // or transitions on child elements and produces false passes (e.g. a loading spinner
    // child transitioning 0→1 while the button itself has no focus style).
    const isVisible = hasVisibleOutline || outlineChanged || boxShadowChanged ||
                      borderChanged || bgChanged || colorChanged || transformChanged || afterChanged;

    if (!isVisible) {
      violations.push({
        html: el.html,
        element_id: el.id || null,
        target: el.target,
        tag: el.tag,
        tagName: el.tagName,
        id: el.id,
      });
    }
  }

  const cssRules = cssFindings.map(f => ({
    ruleId:      `${RULE_ID}-css-reset`,
    description: 'CSS :focus outline reset without :focus-visible restoration',
    impact:      'serious',
    status:      'incomplete',
    reason:      _t(sharedContext, 'CSS rule "{selector}" removes the focus outline for all pointer/keyboard users without restoring it via :focus-visible. Add a :focus-visible rule to preserve keyboard focus styling.', 'CSS ルール "{selector}" はすべてのユーザーの focus アウトラインを削除していますが、:focus-visible で復元されていません。キーボードフォーカス表示を維持するには :focus-visible ルールを追加してください。', { selector: f.selector }),
    selector:    f.selector,
    helpUrl:     HELP_URL,
  }));

  if (violations.length === 0 && cssRules.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: 'Focusable elements must have a visible focus indicator', impact: null, status: 'pass', reason: _t(sharedContext, 'All {count} sampled focusable elements have a visible focus indicator.', 'サンプリングしたフォーカス可能要素 {count} 件すべてに、視認できるフォーカスインジケーターがあります。', { count: elements.length }), helpUrl: HELP_URL }],
    };
  }

  if (violations.length === 0 && cssRules.length > 0) {
    return {
      successCriteriaId: SC,
      rules: cssRules,
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Focusable elements must have a visible focus indicator',
      impact: 'serious',
      status: 'fail',
      reason: _t(
        sharedContext,
        '{count} focusable element(s) lack a visible focus indicator: {sample}.',
        'フォーカス可能要素 {count} 件に、視認できるフォーカスインジケーターがありません: {sample}。',
        {
          count: violations.length,
          sample: violations.slice(0, 3).map(v => `<${v.tagName.toLowerCase()}${v.id ? ` id="${v.id}"` : ''}>`).join(', '),
        },
      ),
      elements: violations,
      helpUrl: HELP_URL,
    }, ...cssRules],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
