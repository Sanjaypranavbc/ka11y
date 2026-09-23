'use strict';

const {
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '1.3.2';
const RULE_ID = 'custom-meaningful-sequence';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/meaningful-sequence';
// MAX_CONTAINERS limits how many flex/grid containers are inspected (not total elements).
const MAX_CONTAINERS = 2000;

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

function _formatViolationDetail(violation, context) {
  if (violation && typeof violation.reason === 'string' && violation.reason.trim()) {
    return violation.reason;
  }

  const orders = Array.isArray(violation && violation.orders)
    ? violation.orders.join(', ')
    : '';

  switch (violation && violation.reasonCode) {
    case 'grid-explicit-placement':
      return _t(
        context,
        'Grid container has children with explicit grid-column or grid-row placement, potentially reordering visual presentation from DOM order',
        'Grid コンテナ内で grid-column または grid-row が明示されている子要素があり、DOM 順序と異なる視覚順になる可能性があります。',
      );
    case 'grid-auto-flow-dense':
      return _t(
        context,
        'Grid container uses grid-auto-flow: dense, which may place items out of DOM order to fill grid holes',
        'Grid コンテナで grid-auto-flow: dense が使われており、グリッドの隙間を埋めるために DOM 順序外に要素が配置される可能性があります。',
      );
    case 'multi-column-layout':
      return _t(
        context,
        'Element uses multi-column layout (column-count > 1); content may visually flow across columns in an order that diverges from DOM order',
        '複数カラムレイアウト（column-count > 1）が使われており、コンテンツが DOM 順序と異なるカラム順で表示される可能性があります。',
      );
    case 'mixed-floats':
      return _t(
        context,
        'Container has mixed floated (left/right) and non-floated siblings, which may reorder visual presentation from DOM order',
        'float 指定された兄弟要素（left/right）と非 float 要素が混在しており、DOM 順序と異なる視覚順になる可能性があります。',
      );
    case 'flex-direction-reverse':
      return _t(
        context,
        'flex-direction: {flexDir} reverses DOM order visually',
        'flex-direction: {flexDir} により DOM 順序が視覚的に反転しています。',
        { flexDir: violation && violation.flexDir },
      );
    case 'css-order-reorders':
      return _t(
        context,
        'CSS order property reorders children from DOM sequence (orders: [{orders}])',
        'CSS の order プロパティにより子要素が DOM 順序から並び替えられています（order: [{orders}]）。',
        { orders },
      );
    case 'positioned-reorders':
      return _t(
        context,
        'Absolutely/fixed positioned children are displayed in a different order (top-to-bottom, left-to-right) than their DOM order — the reading sequence exposed to assistive technology differs from the visual one (G57/C6/C27)',
        'absolute/fixed 配置の子要素が DOM 順序と異なる順（上から下、左から右）で表示されています。支援技術に伝わる読み順が視覚的な順序と異なります（G57/C6/C27）。',
      );
    case 'letter-spaced-words':
      return _t(
        context,
        'Heading spells a word with spaces between letters ("W O R D") — screen readers announce single letters; use CSS letter-spacing instead (C8)',
        '見出しで単語の文字間にスペースが入っています（「W O R D」）。スクリーンリーダーは一文字ずつ読み上げます。代わりに CSS の letter-spacing を使ってください（C8）。',
      );
    case 'mixed-direction-no-dir':
      return _t(
        context,
        'Text mixes right-to-left and left-to-right scripts without a dir attribute, <bdi>/<bdo>, or Unicode RLM/LRM marks — inline reading order may render incorrectly (H34/H56)',
        '右横書きと左横書きの文字が混在していますが、dir 属性・<bdi>/<bdo>・Unicode の RLM/LRM が使われていません。インラインの読み順が正しく表示されない可能性があります（H34/H56）。',
      );
    default:
      return '';
  }
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);
  const violations = await page.evaluate((maxC) => {
    const results = [];
    let containerCount = 0;

    for (const el of document.querySelectorAll('*')) {
      const style = window.getComputedStyle(el);
      const display = style.display;

      const isFlex = display === 'flex' || display === 'inline-flex';
      const isGrid = display === 'grid' || display === 'inline-grid';
      const colCount = parseInt(style.columnCount, 10);
      const isMultiCol = !isFlex && !isGrid && colCount > 1;
      if (!isFlex && !isGrid && !isMultiCol) continue;
      if (containerCount++ >= maxC) break;

      // Multi-column layout: visual reading order may diverge from DOM order
      if (isMultiCol) {
        results.push({
          tagName: el.tagName.toLowerCase(),
          element_id: el.id || null,
          target: el.id ? [`#${CSS.escape(el.id)}`] : [el.tagName.toLowerCase()],
          tag: el.tagName.toUpperCase(),
          display,
          flexDir: null,
          orders: null,
          reasonCode: 'multi-column-layout',
          html: el.outerHTML.slice(0, 150),
        });
        continue;
      }

      const children = Array.from(el.children).filter(ch => {
        // Only consider visible children — exclude all common hiding patterns
        const cs = window.getComputedStyle(ch);
        return cs.display !== 'none' &&
               cs.visibility !== 'hidden' &&
               cs.visibility !== 'collapse' &&
               cs.opacity !== '0';
      });
      if (children.length < 2) continue;

      // Bug fix 1: detect flex-direction reversal (visually reverses DOM order)
      const flexDir = style.flexDirection || '';
      const isReversed = flexDir === 'row-reverse' || flexDir === 'column-reverse';

      // B13: RTL layout exemption — row-reverse is the CORRECT implementation for
      // Arabic, Hebrew, Persian, and Urdu sites. Flag it only when the document/element
      // writing direction is LTR. column-reverse is still flagged regardless of directionality.
      if (flexDir === 'row-reverse') {
        const docDir  = (document.documentElement.getAttribute('dir') || '').toLowerCase();
        const docLang = document.documentElement.getAttribute('lang') || '';
        const isRtlDoc = docDir === 'rtl' ||
          /^(ar|he|fa|ur|yi|arc|ckb)\b/i.test(docLang);
        const isRtlEl  = !!el.closest('[dir="rtl"]');
        if (isRtlDoc || isRtlEl) continue; // correct usage for RTL — skip
      }

      // Valid UI Pattern Exemption: If a flex container is reversed but ONLY contains 
      // interactive elements (like a button group), it rarely breaks meaning.
      if (isReversed) {
         const allInteractive = children.every(ch => {
             const t = ch.tagName.toLowerCase();
             return ['button', 'a', 'input', 'select'].includes(t) || ch.hasAttribute('role');
         });
         if (allInteractive) continue; // Skip to PASS
      }

      // Bug fix 2: detect CSS order property — use parseInt with radix 10
      // Note: parseInt('auto', 10) = NaN; we treat NaN as 0 (default order)
      const orders = children.map(ch => {
        const o = parseInt(window.getComputedStyle(ch).order, 10);
        return isNaN(o) ? 0 : o;
      });
      const hasExplicitOrder = !orders.every(o => o === 0);

      // Check if the order property actually reorders relative to DOM position
      // (ascending order = same as DOM → no reordering issue)
      let orderReorders = false;
      if (hasExplicitOrder) {
        const domIndices = orders.map((_, i) => i);
        const visualOrder = [...orders.keys()].sort((a, b) => orders[a] - orders[b]);
        orderReorders = visualOrder.some((vi, di) => vi !== domIndices[di]);
      }

      // Grid auto-flow dense: may place items out of DOM order
      if (isGrid) {
        const gridAutoFlow = style.gridAutoFlow || '';
        if (gridAutoFlow.includes('dense')) {
          results.push({
            tagName: el.tagName.toLowerCase(),
            element_id: el.id || null,
            target: el.id ? [`#${CSS.escape(el.id)}`] : [el.tagName.toLowerCase()],
            tag: el.tagName.toUpperCase(),
            display,
            flexDir: null,
            orders: null,
            reasonCode: 'grid-auto-flow-dense',
            html: el.outerHTML.slice(0, 150),
          });
          continue;
        }
      }

      // Grid explicit placement: grid-row or grid-column (start or end) on children
      if (isGrid) {
        const hasGridPlacement = children.some(ch => {
          const ccs = window.getComputedStyle(ch);
          return ccs.gridColumnStart !== 'auto' || ccs.gridRowStart !== 'auto' ||
                 ccs.gridColumnEnd   !== 'auto' || ccs.gridRowEnd   !== 'auto';
        });
        if (hasGridPlacement) {
          results.push({
            tagName: el.tagName.toLowerCase(),
            element_id: el.id || null,
            target: el.id ? [`#${CSS.escape(el.id)}`] : [el.tagName.toLowerCase()],
            tag: el.tagName.toUpperCase(),
            display,
            flexDir: null,
            orders: null,
            reasonCode: 'grid-explicit-placement',
            html: el.outerHTML.slice(0, 150),
          });
          continue;
        }
      }

      // Float reordering: mixed floated/non-floated siblings
      if (children.length >= 2) {
        const floats = children.map(ch => window.getComputedStyle(ch).float);
        const hasFloated = floats.some(f => f === 'left' || f === 'right');
        const hasNonFloated = floats.some(f => f === 'none');
        if (hasFloated && hasNonFloated) {
          results.push({
            tagName: el.tagName.toLowerCase(),
            element_id: el.id || null,
            target: el.id ? [`#${CSS.escape(el.id)}`] : [el.tagName.toLowerCase()],
            tag: el.tagName.toUpperCase(),
            display,
            flexDir: null,
            orders: null,
            reasonCode: 'mixed-floats',
            html: el.outerHTML.slice(0, 150),
          });
          continue;
        }
      }

      if (!isReversed && !orderReorders) continue;

      results.push({
        tagName: el.tagName.toLowerCase(),
        element_id: el.id || null,
        target: el.id ? [`#${CSS.escape(el.id)}`] : [el.tagName.toLowerCase()],
        tag: el.tagName.toUpperCase(),
        display,
        flexDir: flexDir || null,
        orders: hasExplicitOrder ? orders : null,
        reasonCode: isReversed ? 'flex-direction-reverse' : 'css-order-reorders',
        html: el.outerHTML.slice(0, 150),
      });
    }

    // ── H34 / H56: bidirectional text without explicit direction handling ────
    const RTL_RE = /[\u0590-\u08FF\uFB1D-\uFDFF\uFE70-\uFEFF]/;
    const LTR_RE = /[A-Za-z\u00C0-\u024F]{2,}/;
    const BIDI_CTRL_RE = /[\u200E\u200F\u202A-\u202E\u2066-\u2069]/;
    let bidiChecked = 0;
    for (const el of document.querySelectorAll('p, li, td, th, h1, h2, h3, h4, h5, h6, dd, blockquote, figcaption, label, span, a')) {
      if (bidiChecked++ > 1500) break;
      const text = (el.textContent || '').trim();
      if (text.length < 4 || text.length > 2000) continue;
      if (!RTL_RE.test(text) || !LTR_RE.test(text)) continue;
      if (BIDI_CTRL_RE.test(text)) continue;
      if (el.closest('[dir]') || el.querySelector('[dir], bdi, bdo')) continue;
      results.push({
        tagName: el.tagName.toLowerCase(),
        element_id: el.id || null,
        target: el.id ? [`#${CSS.escape(el.id)}`] : [el.tagName.toLowerCase()],
        tag: el.tagName.toUpperCase(),
        display: null,
        flexDir: null,
        orders: null,
        reasonCode: 'mixed-direction-no-dir',
        html: el.outerHTML.slice(0, 150),
      });
      if (results.length >= 60) break;
    }

    // ── G57 / C6 / SCR27: positioned siblings whose visual order differs from DOM order ──
    let posChecked = 0;
    for (const el of document.querySelectorAll('div, section, article, main, ul, ol, form, header, footer, li, figure')) {
      if (posChecked++ > 2000 || results.length >= 80) break;
      const kids = Array.from(el.children).filter(ch => {
        const cs = window.getComputedStyle(ch);
        if (cs.display === 'none' || cs.visibility === 'hidden') return false;
        const r = ch.getBoundingClientRect();
        return r.width > 20 && r.height > 12 && (ch.textContent || '').trim().length > 0;
      });
      if (kids.length < 2 || kids.length > 40) continue;
      const positioned = kids.filter(ch => /^(absolute|fixed)$/.test(window.getComputedStyle(ch).position));
      if (!positioned.length) continue;
      if (positioned.every(p => window.getComputedStyle(p).position === 'fixed') && el.closest('nav, header, footer, [role="navigation"], [role="banner"]')) continue;
      const rects = kids.map(ch => ({ ch, r: ch.getBoundingClientRect() }));
      const visual = [...rects].sort((a, b) => (Math.abs(a.r.top - b.r.top) > 8 ? a.r.top - b.r.top : a.r.left - b.r.left));
      let inversions = 0;
      for (let i = 0; i < visual.length; i++) if (visual[i].ch !== rects[i].ch) inversions++;
      if (inversions < 2) continue;
      results.push({
        tagName: el.tagName.toLowerCase(),
        element_id: el.id || null,
        target: el.id ? [`#${CSS.escape(el.id)}`] : [el.tagName.toLowerCase()],
        tag: el.tagName.toUpperCase(),
        display: null, flexDir: null, orders: null,
        reasonCode: 'positioned-reorders',
        html: el.outerHTML.slice(0, 150),
      });
    }

    // ── C8: words spelled out with spaces between letters in headings ────────
    for (const h of document.querySelectorAll('h1, h2, h3, h4, h5, h6, [role="heading"]')) {
      if (results.length >= 90) break;
      const t = (h.textContent || '').trim();
      if (!/(?:^|\s)(?:[A-Za-z]\s){3,}[A-Za-z](?:\s|$)/.test(t)) continue;
      results.push({
        tagName: h.tagName.toLowerCase(),
        element_id: h.id || null,
        target: h.id ? [`#${CSS.escape(h.id)}`] : [h.tagName.toLowerCase()],
        tag: h.tagName.toUpperCase(),
        display: null, flexDir: null, orders: null,
        reasonCode: 'letter-spaced-words',
        html: h.outerHTML.slice(0, 150),
      });
    }

    return results;
  }, MAX_CONTAINERS);

  if (violations.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: 'Reading and navigation order must be programmatically determinable', impact: null, status: 'pass', reason: _t(sharedContext, 'Up to {count} flex/grid containers inspected — no CSS reordering (flex-direction reverse or order property) found that diverges from DOM order.', '最大 {count} 件の flex/grid コンテナを確認しましたが、DOM 順序と食い違う CSS による並び替え（flex-direction の反転や order プロパティ）は検出されませんでした。', { count: MAX_CONTAINERS }), helpUrl: HELP_URL }],
    };
  }

  const sample = violations
    .slice(0, 3)
    .map(v => _formatViolationDetail(v, sharedContext))
    .filter(Boolean)
    .join('; ');

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Reading and navigation order must be programmatically determinable',
      impact: 'moderate',
      status: 'incomplete',
      reason: _t(sharedContext, '{count} flex/grid container(s) visually reorder content relative to DOM order. Verify the DOM order matches the intended reading sequence. Details: {sample}.', 'flex/grid コンテナ {count} 件で、DOM 順序に対して視覚的な並び替えが行われています。DOM 順序が意図した読み上げ・閲覧順と一致しているか確認してください。詳細: {sample}。', { count: violations.length, sample }),
      elements: violations,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
