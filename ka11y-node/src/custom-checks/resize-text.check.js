'use strict';

/**
 * WCAG 1.4.4 Resize Text — outcome-based 200 % text-zoom test plus CSS unit scan.
 *
 *   C28 / G179 / SCR34  double every text size and look for clipped, cut-off or
 *                       overlapping text (loss of content)
 *   C17                 form controls whose text is cut off after zoom
 *   C12 / C13 / C14     proportion of font-size declarations in px vs em/rem/%/keywords
 *                       (advisory — px sizes still zoom in browsers, but not with
 *                       text-only zoom)
 *   G178                an on-page text-size control is credited as a mechanism
 *   G142                touch handlers that call preventDefault on touchmove/gesture
 *                       events can block pinch-zoom (advisory)
 */

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '1.4.4';
const RULE_ID = 'custom-resize-text';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/resize-text';
const MODE = 'interactive';
const FALLBACK_DESCRIPTION = 'Text must be resizable up to 200 percent without loss of content or functionality';

const MAX_ZOOM_ELEMENTS = 3500;

function _t(ctx, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, ctx, en);
}

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  // ── 1. CSSOM unit scan + text-size controls + touch hooks (no page mutation) ──
  const scanRaw = await page.evaluate(() => {
    const out = { px: 0, relative: 0, inlinePx: 0, textSizeControls: 0, touchBlockers: 0, textElements: 0 };
    try {
      const walk = (rules, depth) => {
        if (!rules || depth > 4) return;
        for (const r of rules) {
          try {
            if (r.style && r.style.fontSize) {
              const v = String(r.style.fontSize).trim();
              if (/^\d*\.?\d+px$/.test(v)) out.px++;
              else if (/(em|rem|%|vw|vh|ch|ex)$|^(xx-small|x-small|small|medium|large|x-large|xx-large|smaller|larger)$|^calc\(/.test(v)) out.relative++;
            }
            if (r.cssRules) walk(r.cssRules, depth + 1);
          } catch (_) { /* cross-origin */ }
        }
      };
      for (const sheet of document.styleSheets) { try { walk(sheet.cssRules, 0); } catch (_) { /* cross-origin sheet */ } }
      for (const el of document.querySelectorAll('[style*="font-size"]')) {
        if (/font-size\s*:\s*\d*\.?\d+px/i.test(el.getAttribute('style') || '')) out.inlinePx++; else out.relative++;
      }
    } catch (_) { /* ignore */ }
    try {
      const RE = /text[-\s]?size|font[-\s]?size|resize\s+text|larger\s+text|smaller\s+text|increase\s+(?:text|font)|decrease\s+(?:text|font)|文字サイズ|文字の大きさ|フォントサイズ|大きく|小さく|\bA\+|\bA-|\bA−/i;
      for (const el of document.querySelectorAll('button, a[href], [role="button"], input[type="range"], select')) {
        const txt = [(el.textContent || ''), el.getAttribute('aria-label') || '', el.getAttribute('title') || '', el.className || '', el.id || ''].join(' ');
        if (RE.test(txt)) out.textSizeControls++;
      }
    } catch (_) { /* ignore */ }
    try {
      const R = window.__ka11yRuntime;
      if (R && Array.isArray(R.docListeners)) {
        out.touchBlockers = R.docListeners.filter(l => /^(touchmove|touchstart|gesturestart|gesturechange|wheel)$/.test(l.type) && !l.passive && l.preventsDefault).length;
      }
    } catch (_) { /* ignore */ }
    out.textElements = document.querySelectorAll('p, li, a, button, label, h1, h2, h3, h4, h5, h6, td, th, dd, dt, span, input, textarea, select, figcaption, summary').length;
    return out;
  });
  const scan = scanRaw && typeof scanRaw === 'object' && !Array.isArray(scanRaw) ? scanRaw : {};

  // ── 2. 200 % text-zoom test ────────────────────────────────────────────────
  let zoomRaw = null;
  try {
    zoomRaw = await page.evaluate((maxEls) => {
      const out = { mode: 'text', applied: 0, clipped: [], cutControls: [], overlaps: [], skipped: false };
      const sel = (el) => el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : '') + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
      const visible = (el) => { const cs = window.getComputedStyle(el); if (cs.display === 'none' || cs.visibility === 'hidden') return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
      const hasOwnText = (el) => { for (const n of el.childNodes) if (n.nodeType === 3 && n.textContent.trim()) return true; return false; };
      const TEXT_SEL = 'p, li, a, button, label, h1, h2, h3, h4, h5, h6, td, th, dd, dt, span, div, figcaption, summary, legend, blockquote, small, strong, em';
      const all = Array.from(document.querySelectorAll('body *'));
      if (all.length > maxEls * 3) { out.skipped = true; return out; }
      const textEls = Array.from(document.querySelectorAll(TEXT_SEL)).filter(el => visible(el) && hasOwnText(el));
      const controls = Array.from(document.querySelectorAll('input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]), select, textarea, button')).filter(visible);

      // Apply: inline !important font-size = 2 × computed, remembering originals.
      const originals = [];
      const targets = all.length <= maxEls ? all : [...textEls, ...controls];
      const t0 = performance.now();
      for (const el of targets) {
        if (performance.now() - t0 > 1500) break;
        const cs = window.getComputedStyle(el);
        const px = parseFloat(cs.fontSize);
        if (!px || px <= 0) continue;
        originals.push([el, el.style.getPropertyValue('font-size'), el.style.getPropertyPriority('font-size')]);
        el.style.setProperty('font-size', (px * 2) + 'px', 'important');
        out.applied++;
      }
      // Force layout and measure.
      void document.body.offsetHeight;
      try {
        const clipAncestor = (el) => {
          let n = el.parentElement;
          while (n && n !== document.body) {
            const cs = window.getComputedStyle(n);
            if (/(hidden|clip)/.test(cs.overflow + cs.overflowX + cs.overflowY)) return n;
            n = n.parentElement;
          }
          return null;
        };
        let checked = 0;
        for (const el of textEls) {
          if (checked++ > 1200 || out.clipped.length >= 12) break;
          const own = window.getComputedStyle(el);
          if (/(hidden|clip)/.test(own.overflow + own.overflowX + own.overflowY) && (el.scrollHeight > el.clientHeight + 3 || el.scrollWidth > el.clientWidth + 3) && (el.textContent || '').trim().length > 1) {
            out.clipped.push({ target: sel(el), snippet: el.outerHTML.slice(0, 140), detail: `Text "${(el.textContent || '').trim().slice(0, 40)}" is cut off by its own overflow:hidden box (${el.scrollWidth}×${el.scrollHeight}px content in ${el.clientWidth}×${el.clientHeight}px) at 200 % text size (C28/G179)` });
            continue;
          }
          const a = clipAncestor(el);
          if (!a) continue;
          const r = el.getBoundingClientRect(), ar = a.getBoundingClientRect();
          const acs = window.getComputedStyle(a);
          const scrollableX = /(auto|scroll)/.test(acs.overflowX), scrollableY = /(auto|scroll)/.test(acs.overflowY);
          const overRight = !scrollableX && r.right > ar.right + 3 && r.width > 8;
          const overBottom = !scrollableY && r.bottom > ar.bottom + 3 && r.height > 8;
          if ((overRight || overBottom) && (el.textContent || '').trim().length > 1) {
            out.clipped.push({ target: sel(el), snippet: el.outerHTML.slice(0, 140), detail: `Text "${(el.textContent || '').trim().slice(0, 40)}" overflows its overflow:hidden container (${sel(a)}) by ${Math.round(Math.max(r.right - ar.right, r.bottom - ar.bottom))}px at 200 % text size — content is cut off (C28/G179)` });
          }
        }
        for (const c of controls) {
          if (out.cutControls.length >= 8) break;
          if (c.tagName === 'SELECT' || c.tagName === 'TEXTAREA') continue;
          const cs = window.getComputedStyle(c);
          if (cs.overflow === 'visible' && c.tagName === 'BUTTON') continue;
          if (c.scrollWidth > c.clientWidth + 4 && (c.value || c.textContent || '').trim()) {
            out.cutControls.push({ target: sel(c), snippet: c.outerHTML.slice(0, 140), detail: `Control text "${(c.value || c.textContent || '').trim().slice(0, 30)}" is cut off at 200 % text size (scrollWidth ${c.scrollWidth} > width ${c.clientWidth}) — avoid fixed px widths/heights on controls (C17)` });
          }
        }
        // Overlaps between sibling text blocks
        const blocks = textEls.filter(el => /^(P|LI|H[1-6]|DD|DT|FIGCAPTION|BLOCKQUOTE|LABEL|BUTTON|A)$/.test(el.tagName)).slice(0, 600);
        const byParent = new Map();
        for (const b of blocks) { const p = b.parentElement; if (!p) continue; if (!byParent.has(p)) byParent.set(p, []); byParent.get(p).push(b); }
        for (const sibs of byParent.values()) {
          if (out.overlaps.length >= 8) break;
          const rects = sibs.map(s => [s, s.getBoundingClientRect()]);
          for (let i = 0; i < rects.length; i++) for (let j = i + 1; j < rects.length; j++) {
            const [ea, a] = rects[i], [eb, b] = rects[j];
            const ix = Math.min(a.right, b.right) - Math.max(a.left, b.left);
            const iy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
            if (ix > 6 && iy > 6) {
              const contains = (a.left <= b.left && a.right >= b.right && a.top <= b.top && a.bottom >= b.bottom) || (b.left <= a.left && b.right >= a.right && b.top <= a.top && b.bottom >= a.bottom);
              if (contains) continue;
              const csa = window.getComputedStyle(ea), csb = window.getComputedStyle(eb);
              if (csa.position === 'absolute' || csb.position === 'absolute' || csa.position === 'fixed' || csb.position === 'fixed') continue;
              out.overlaps.push({ target: sel(ea), snippet: ea.outerHTML.slice(0, 140), detail: `"${(ea.textContent || '').trim().slice(0, 30)}" overlaps "${(eb.textContent || '').trim().slice(0, 30)}" by ${Math.round(ix)}×${Math.round(iy)}px at 200 % text size (C28/G179)` });
              if (out.overlaps.length >= 8) break;
            }
          }
        }
      } finally {
        for (const [el, v, p] of originals) { if (v) el.style.setProperty('font-size', v, p); else el.style.removeProperty('font-size'); }
      }
      return out;
    }, MAX_ZOOM_ELEMENTS);
  } catch (_) {
    zoomRaw = null;
  }
  const zoom = zoomRaw && typeof zoomRaw === 'object' && !Array.isArray(zoomRaw) ? zoomRaw : { clipped: [], cutControls: [], overlaps: [], skipped: true };
  const problems = [...(zoom.clipped || []), ...(zoom.cutControls || []), ...(zoom.overlaps || [])];
  const rules = [];
  const pxTotal = (scan.px || 0) + (scan.inlinePx || 0);
  const declTotal = pxTotal + (scan.relative || 0);
  const pxRatio = declTotal ? pxTotal / declTotal : 0;
  const hasControl = (scan.textSizeControls || 0) > 0;

  if (zoom.skipped) {
    rules.push({ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: 'moderate', status: 'incomplete', reason: _t(ctx,
      'Page is too large for the automated 200 % text-zoom test ({n} text elements) — verify manually that text can be enlarged to 200 % without clipping or overlap.',
      'ページが大きすぎるため自動の 200 % 文字拡大テストは実行できませんでした（テキスト要素 {n} 件）。文字を 200 % に拡大しても切れや重なりが生じないか手動で確認してください。', { n: scan.textElements || 0 }), helpUrl: HELP_URL });
  } else if (!problems.length) {
    rules.push({ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'pass', reason: _t(ctx,
      'Text doubled to 200 % on {n} element(s): no clipped text, cut-off controls or overlapping text detected{ctl}.',
      '{n} 件の要素で文字を 200 % に拡大: テキストの切れ、コントロールの見切れ、テキストの重なりは検出されませんでした{ctl}。',
      { n: zoom.applied || 0, ctl: hasControl ? _t(ctx, '; an on-page text-size control is also provided (G178)', '。ページ内に文字サイズ変更機能もあります（G178）') : '' }), helpUrl: HELP_URL });
  } else {
    rules.push({ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: hasControl ? 'moderate' : 'serious', status: hasControl ? 'incomplete' : 'fail', reason: _t(ctx,
      'At 200 % text size {c} text block(s) are clipped, {k} control(s) cut off their text and {o} text block(s) overlap — content is lost when text is enlarged{ctl}.',
      '文字サイズ 200 % で、テキストブロック {c} 件が切れ、コントロール {k} 件のテキストが見切れ、テキストブロック {o} 件が重なります。文字を拡大するとコンテンツが失われます{ctl}。',
      { c: (zoom.clipped || []).length, k: (zoom.cutControls || []).length, o: (zoom.overlaps || []).length, ctl: hasControl ? _t(ctx, '; an on-page text-size control exists — verify it avoids these problems (G178)', '。ページ内の文字サイズ変更機能でこれらの問題が起きないか確認してください（G178）') : '' }),
      elements: problems, helpUrl: HELP_URL });
  }
  if (declTotal >= 5 && pxRatio > 0.8) {
    rules.push({ ruleId: `${RULE_ID}-units`, description: FALLBACK_DESCRIPTION, impact: 'minor', status: 'incomplete', reason: _t(ctx,
      '{pct}% of font-size declarations ({px} of {total}) use px. Browser zoom still scales them, but text-only zoom (user stylesheets, "font size" browser setting) does not — prefer em/rem/% (C12/C13/C14).',
      'font-size 宣言の {pct}%（{total} 件中 {px} 件）が px 単位です。ブラウザのズームでは拡大されますが、文字のみの拡大（ユーザースタイルシートやブラウザの文字サイズ設定）では拡大されません。em/rem/% を推奨します（C12/C13/C14）。',
      { pct: Math.round(pxRatio * 100), px: pxTotal, total: declTotal }), helpUrl: HELP_URL });
  }
  if ((scan.touchBlockers || 0) > 0) {
    rules.push({ ruleId: `${RULE_ID}-touch-zoom`, description: FALLBACK_DESCRIPTION, impact: 'moderate', status: 'incomplete', reason: _t(ctx,
      '{n} non-passive touch/gesture handler(s) on document/window call preventDefault() — this can block pinch-zoom on touch devices; verify zooming still works (G142).',
      'document/window 上の非 passive なタッチ/ジェスチャーハンドラー {n} 件が preventDefault() を呼んでいます。タッチ端末でピンチズームが妨げられる可能性があります。ズームが機能するか確認してください（G142）。', { n: scan.touchBlockers }), helpUrl: HELP_URL });
  }
  return { successCriteriaId: SC, rules };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
