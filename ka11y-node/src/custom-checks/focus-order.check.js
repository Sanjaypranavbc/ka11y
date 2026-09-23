'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '2.4.3';
const RULE_ID = 'custom-focus-order';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/focus-order';
const MODE = 'interactive';
const FALLBACK_DESCRIPTION = 'Navigation order must preserve meaning — focusable elements must follow a logical sequence';

const MAX_TABS = 15;
const SETTLE_MS = 40;

function _t(ctx, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, ctx, en);
}

function _pass(ctx, reason) {
  return {
    successCriteriaId: SC,
    rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'pass', reason, helpUrl: HELP_URL }],
  };
}

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  // ── Check 1: positive tabindex values (primary WCAG failure indicator) ──
  const positiveTabindex = await page.evaluate(() => {
    const issues = [];
    for (const el of document.querySelectorAll('[tabindex]')) {
      const val = parseInt(el.getAttribute('tabindex'), 10);
      if (val > 0) {
        issues.push({
          target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
          snippet: el.outerHTML.slice(0, 120),
          tabindex: val,
          detail: `tabindex="${val}" overrides natural DOM focus order — use tabindex="0" instead`,
        });
        if (issues.length >= 20) break;
      }
    }
    return issues;
  });

  // ── Check 2: tab sequence vs DOM order divergence ──────────────────────
  // Collect (domIndex, tabSequenceIndex) pairs then compare
  const domOrder = await page.evaluate(() => {
    const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]):not([type="hidden"]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
    const all = Array.from(document.querySelectorAll('*'));
    return Array.from(document.querySelectorAll(FOCUSABLE)).map(el => ({
      domIndex: all.indexOf(el),
      id: el.id || null,
      tag: el.tagName.toLowerCase(),
      snippet: el.outerHTML.slice(0, 80),
    }));
  });

  const tabSequence = [];
  for (let i = 0; i < Math.min(MAX_TABS, domOrder.length); i++) {
    await page.keyboard.press('Tab');
    await new Promise(r => setTimeout(r, SETTLE_MS));
    const info = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body || el === document.documentElement) return null;
      const all = Array.from(document.querySelectorAll('*'));
      return { domIndex: all.indexOf(el), id: el.id || null, tag: el.tagName.toLowerCase(), snippet: el.outerHTML.slice(0, 80) };
    });
    if (!info) break;
    tabSequence.push(info);
  }

  // Detect order inversions: if tab sequence dom indices are not monotonically
  // increasing we have a focus order problem
  const orderViolations = [];
  for (let i = 1; i < tabSequence.length; i++) {
    const prev = tabSequence[i - 1];
    const curr = tabSequence[i];
    // Allow small backwards jumps (skip links, landmarks) but flag big inversions
    if (curr.domIndex < prev.domIndex - 5) {
      orderViolations.push({
        target: curr.tag + (curr.id ? `#${curr.id}` : ''),
        snippet: curr.snippet,
        detail: `Tab step ${i + 1} jumps from DOM position ${prev.domIndex} back to ${curr.domIndex} — focus order may not match visual reading order`,
      });
      if (orderViolations.length >= 5) break;
    }
  }

  // ── Check 3 (SCR26): content revealed by an expander must follow the trigger ────
  const expanderIssues = [];
  try {
    const expanders = await page.evaluate(() => Array.from(document.querySelectorAll('[aria-expanded="false"][aria-controls]'))
      .filter(el => el.tagName === 'BUTTON' || el.getAttribute('role') === 'button' || el.tagName === 'SUMMARY')
      .slice(0, 5)
      .map((el, i) => { el.setAttribute('data-ka11y-exp', String(i)); return { i, tag: el.tagName.toLowerCase(), id: el.id || null, snippet: el.outerHTML.slice(0, 80) }; }));
    for (const ex of (Array.isArray(expanders) ? expanders : [])) {
      const res = await page.evaluate((i) => {
        const el = document.querySelector(`[data-ka11y-exp="${i}"]`);
        if (!el) return null;
        const target = document.getElementById((el.getAttribute('aria-controls') || '').split(/\s+/)[0]);
        if (!target) return null;
        el.click();
        return new Promise(r => setTimeout(() => {
          const cs = window.getComputedStyle(target);
          const visible = cs.display !== 'none' && cs.visibility !== 'hidden' && !target.hidden;
          const follows = !!(el.compareDocumentPosition(target) & Node.DOCUMENT_POSITION_FOLLOWING);
          if (el.getAttribute('aria-expanded') === 'true') el.click(); // restore
          r({ visible, follows });
        }, 200));
      }, ex.i);
      if (res && res.visible && !res.follows) {
        expanderIssues.push({ target: ex.tag + (ex.id ? `#${ex.id}` : ''), snippet: ex.snippet, detail: 'Content revealed by this expander is placed before the trigger in DOM order — keyboard users must move backwards to reach it (SCR26)' });
      }
    }
    await page.evaluate(() => { for (const el of document.querySelectorAll('[data-ka11y-exp]')) el.removeAttribute('data-ka11y-exp'); });
  } catch (_) { /* best effort */ }

  // ── Check 4 (G59 / H102): dialog focus management — focus moves in, Escape returns it ──
  const dialogIssues = [];
  try {
    const openers = await page.evaluate(() => Array.from(document.querySelectorAll('button[aria-haspopup="dialog"], [role="button"][aria-haspopup="dialog"], button[data-toggle="modal"], button[data-bs-toggle="modal"], button[data-modal-target], button[data-micromodal-trigger], button[data-a11y-dialog-show]'))
      .slice(0, 2)
      .map((el, i) => { el.setAttribute('data-ka11y-dlg', String(i)); return { i, tag: el.tagName.toLowerCase(), id: el.id || null, snippet: el.outerHTML.slice(0, 80) }; }));
    for (const op of (Array.isArray(openers) ? openers : [])) {
      const res = await page.evaluate((i) => {
        const el = document.querySelector(`[data-ka11y-dlg="${i}"]`);
        if (!el) return null;
        el.focus({ preventScroll: true });
        el.click();
        return new Promise(r => setTimeout(() => {
          const dlg = Array.from(document.querySelectorAll('dialog[open], [role="dialog"], [role="alertdialog"], [aria-modal="true"]')).find(d => { const cs = window.getComputedStyle(d); return cs.display !== 'none' && cs.visibility !== 'hidden' && d.getBoundingClientRect().width > 0; });
          if (!dlg) return r({ opened: false });
          r({ opened: true, focusInside: dlg.contains(document.activeElement) });
        }, 350));
      }, op.i);
      if (!res || !res.opened) continue;
      const target = op.tag + (op.id ? `#${op.id}` : '');
      if (!res.focusInside) dialogIssues.push({ target, snippet: op.snippet, detail: 'Opening the dialog did not move keyboard focus into it — focus stays behind the dialog (G59/H102)' });
      if (page.keyboard && page.keyboard.press) { await page.keyboard.press('Escape'); await new Promise(r => setTimeout(r, 300)); }
      const after = await page.evaluate((i) => {
        const el = document.querySelector(`[data-ka11y-dlg="${i}"]`);
        const dlg = Array.from(document.querySelectorAll('dialog[open], [role="dialog"], [role="alertdialog"], [aria-modal="true"]')).find(d => { const cs = window.getComputedStyle(d); return cs.display !== 'none' && cs.visibility !== 'hidden' && d.getBoundingClientRect().width > 0; });
        return { stillOpen: !!dlg, focusRestored: document.activeElement === el };
      }, op.i);
      if (after && !after.stillOpen && !after.focusRestored) dialogIssues.push({ target, snippet: op.snippet, detail: 'After closing the dialog with Escape, focus was not returned to the element that opened it (G59/H102)' });
      if (after && after.stillOpen) {
        await page.evaluate(() => { const b = document.querySelector('dialog[open] button[aria-label*="close" i], [role="dialog"] button[aria-label*="close" i], [role="dialog"] .close, [role="dialog"] [class*="close" i], dialog[open] button'); if (b) b.click(); }).catch(() => {});
      }
    }
    await page.evaluate(() => { for (const el of document.querySelectorAll('[data-ka11y-dlg]')) el.removeAttribute('data-ka11y-dlg'); });
  } catch (_) { /* best effort */ }

  // Combine findings
  const allViolations = [
    ...positiveTabindex.map(v => ({ ...v, type: 'positive-tabindex' })),
    ...orderViolations.map(v => ({ ...v, type: 'order-inversion' })),
    ...expanderIssues.map(v => ({ ...v, type: 'expander-order' })),
    ...dialogIssues.map(v => ({ ...v, type: 'dialog-focus' })),
  ];

  if (!allViolations.length) {
    return _pass(ctx, _t(ctx,
      'No positive tabindex values or focus order inversions detected across {n} focusable elements.',
      'フォーカス可能要素 {n} 件でポジティブ tabindex やフォーカス順の逆転は検出されませんでした。',
      { n: tabSequence.length }));
  }

  const hasPositive = positiveTabindex.length > 0 || dialogIssues.length > 0;
  const status = hasPositive ? 'fail' : 'incomplete';

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: hasPositive ? 'serious' : 'moderate',
      status,
      reason: _t(ctx,
        '{pos} element(s) use positive tabindex (disrupts natural order); {inv} focus order inversion(s); {exp} expander(s) reveal content before the trigger (SCR26); {dlg} dialog focus-management problem(s) (G59/H102).',
        '{pos} 件の要素がポジティブ tabindex を使用しています（自然な順序を乱す）; {inv} 件のフォーカス順の逆転; {exp} 件の展開コントロールがトリガーより前にコンテンツを表示（SCR26）; {dlg} 件のダイアログのフォーカス管理の問題（G59/H102）。',
        { pos: positiveTabindex.length, inv: orderViolations.length, exp: expanderIssues.length, dlg: dialogIssues.length }),
      elements: allViolations,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
