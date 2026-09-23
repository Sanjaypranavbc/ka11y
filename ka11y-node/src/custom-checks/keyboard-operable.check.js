'use strict';

/**
 * WCAG 2.1.1 Keyboard — listener enumeration plus interaction simulation.
 *
 *   G90 / SCR2 / SCR20 / SCR35  elements with mouse/pointer handlers registered via
 *       addEventListener (or React/jQuery props) but no keyboard handler and no native
 *       keyboard semantics; hover-only handlers without focus equivalents
 *   G202 / SCR29  simulation: focus the element, press Enter and Space, compare the DOM
 *       reaction with a click — a control that reacts to click only fails
 *   G216  sliders: arrow keys must move the value; a single click on the track must too
 *
 * Inline on* attributes are covered by keyboard-no-exception (2.1.3); this check reads
 * the runtime listener registry installed by runtimeHooks.js.
 */

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '2.1.1';
const RULE_ID = 'custom-keyboard-operable';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/keyboard';
const MODE = 'interactive';
const FALLBACK_DESCRIPTION = 'All functionality must be operable through a keyboard interface';

const MAX_SIMULATIONS = 10;
const SETTLE_MS = 140;
const MARK = 'data-ka11y-kbd';

function _t(ctx, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, ctx, en);
}

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);
  const issues = [];
  let verifiedOperable = 0;
  let navigated = false;
  const onNav = () => { navigated = true; };
  if (typeof page.on === 'function') page.on('framenavigated', onNav);

  try {
    // ── Phase 1: enumerate handlers ─────────────────────────────────────────
    const enumRaw = await page.evaluate((mark) => {
      const out = { registryAvailable: false, checked: 0, mouseOnly: [], hoverOnly: [], candidates: [], sliders: [] };
      const R = window.__ka11yRuntime;
      out.registryAvailable = !!(R && typeof R.listenersOf === 'function');
      const sel = (el) => el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : '') + (el.className && typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
      const visible = (el) => { const cs = window.getComputedStyle(el); if (cs.display === 'none' || cs.visibility === 'hidden') return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
      const NATIVE = 'a[href], button, input, select, textarea, summary, details, label, video[controls], audio[controls], iframe, [contenteditable="true"]';
      const MOUSE = /^(click|dblclick|mousedown|mouseup|pointerdown|pointerup|touchstart|touchend)$/;
      const HOVER = /^(mouseover|mouseenter|pointerover|pointerenter)$/;
      const KEY = /^(keydown|keyup|keypress)$/;
      const FOCUS = /^(focus|focusin|blur|focusout)$/;
      const jq = window.jQuery && window.jQuery._data ? window.jQuery : null;
      const types = (el) => {
        const t = new Set(R && R.listenersOf ? R.listenersOf(el) : []);
        for (const a of el.attributes) if (/^on(click|dblclick|mousedown|mouseup|keydown|keyup|keypress|mouseover|mouseenter|focus|blur|touchstart|pointerdown)$/i.test(a.name)) t.add(a.name.slice(2).toLowerCase());
        try {
          const k = Object.keys(el).find(x => x.startsWith('__reactProps'));
          if (k && el[k]) { const p = el[k]; if (p.onClick || p.onMouseDown || p.onMouseUp || p.onPointerDown) t.add('click'); if (p.onKeyDown || p.onKeyUp || p.onKeyPress) t.add('keydown'); if (p.onMouseEnter || p.onMouseOver) t.add('mouseover'); if (p.onFocus) t.add('focus'); }
        } catch (_) { /* ignore */ }
        try { if (jq) { const ev = jq._data(el, 'events'); if (ev) for (const name of Object.keys(ev)) t.add(name); } } catch (_) { /* ignore */ }
        try { if (el._vei) for (const name of Object.keys(el._vei)) t.add(name.replace(/^on/, '').toLowerCase()); } catch (_) { /* ignore */ }
        return Array.from(t);
      };
      const focusable = (el) => el.matches(NATIVE) || (el.hasAttribute('tabindex') && el.getAttribute('tabindex') !== '-1') || el.isContentEditable;
      let n = 0, idx = 0;
      for (const el of document.querySelectorAll('body *')) {
        if (n++ > 6000) break;
        if (el.matches(NATIVE) || el.closest(NATIVE)) continue;
        if (el.closest('[aria-hidden="true"]') || !visible(el)) continue;
        const t = types(el);
        if (!t.length) continue;
        const hasMouse = t.some(x => MOUSE.test(x)), hasKey = t.some(x => KEY.test(x)), hasHover = t.some(x => HOVER.test(x)), hasFocus = t.some(x => FOCUS.test(x));
        if (!hasMouse && !hasHover) continue;
        if (el.querySelector(NATIVE) && !el.hasAttribute('role')) continue; // delegating container for real controls
        out.checked++;
        const role = (el.getAttribute('role') || '').toLowerCase();
        const cs = window.getComputedStyle(el);
        const looksInteractive = cs.cursor === 'pointer' || role || el.hasAttribute('tabindex');
        if (hasMouse && !hasKey && !focusable(el)) {
          if (!looksInteractive) continue; // background analytics / delegated tracking
          out.mouseOnly.push({ target: sel(el), snippet: el.outerHTML.slice(0, 140), types: t.join(','), detail: `Click/pointer handler (${t.filter(x => MOUSE.test(x)).join(', ')}) on a non-focusable <${el.tagName.toLowerCase()}> with no keyboard handler — unreachable and inoperable by keyboard (G90/SCR20/SCR2)` });
          continue;
        }
        if (hasHover && !hasMouse && !hasFocus && !focusable(el) && looksInteractive) {
          out.hoverOnly.push({ target: sel(el), snippet: el.outerHTML.slice(0, 140), types: t.join(','), detail: 'Hover-only handler (mouseover/mouseenter) with no focus equivalent and no keyboard access — content revealed on hover is unavailable to keyboard users (SCR2)' });
          continue;
        }
        if (hasMouse && focusable(el) && out.candidates.length < 40) {
          const isLinkLike = role === 'link' || el.hasAttribute('data-href') || el.hasAttribute('data-url') || /\bhref\b|location|navigate/i.test(el.getAttribute('onclick') || '');
          el.setAttribute(mark, String(idx));
          out.candidates.push({ idx: idx++, target: sel(el), snippet: el.outerHTML.slice(0, 140), role, hasKey, isLinkLike, inForm: !!el.closest('form') });
        }
      }
      for (const s of document.querySelectorAll('input[type="range"]:not([disabled]), [role="slider"]')) {
        if (!visible(s) || out.sliders.length >= 4) continue;
        s.setAttribute(mark, 'slider-' + out.sliders.length);
        out.sliders.push({ id: 'slider-' + out.sliders.length, native: s.tagName === 'INPUT', target: sel(s), snippet: s.outerHTML.slice(0, 140) });
      }
      return out;
    }, MARK);
    const en = enumRaw && typeof enumRaw === 'object' && !Array.isArray(enumRaw) ? enumRaw : { mouseOnly: [], hoverOnly: [], candidates: [], sliders: [] };

    for (const m of (en.mouseOnly || [])) issues.push({ type: 'mouse-only-handler', technique: 'G90', severity: 'fail', ...m });
    for (const h of (en.hoverOnly || [])) issues.push({ type: 'hover-only-handler', technique: 'SCR2', severity: 'fail', ...h });

    // ── Phase 2: simulate keyboard vs click on focusable custom controls ──────
    const candidates = (en.candidates || []).filter(c => !c.isLinkLike).slice(0, MAX_SIMULATIONS);
    const canSimulate = page.keyboard && typeof page.keyboard.press === 'function';
    for (const c of candidates) {
      if (navigated || !canSimulate) break;
      try {
        const before = await page.evaluate((mark, idx) => {
          const el = document.querySelector(`[${mark}="${idx}"]`);
          if (!el) return null;
          el.scrollIntoView({ block: 'center', inline: 'nearest' });
          el.focus({ preventScroll: true });
          const target = el.getAttribute('aria-controls') ? document.getElementById(el.getAttribute('aria-controls').split(/\s+/)[0]) : null;
          const state = () => JSON.stringify({ e: el.getAttribute('aria-expanded'), p: el.getAttribute('aria-pressed'), c: el.getAttribute('aria-checked'), s: el.getAttribute('aria-selected'), cls: el.className, t: target ? [target.hidden, window.getComputedStyle(target).display, target.className] : null, h: location.href });
          window.__ka11yKbd = { count: 0, state, obs: null };
          const related = (node) => {
            if (!node) return false;
            const n = node.nodeType === 1 ? node : node.parentElement;
            if (!n) return false;
            if (el.contains(n) || (target && target.contains(n))) return true;
            if (n.matches && n.matches('[role="dialog"], [role="alertdialog"], [role="menu"], [role="listbox"], [role="tooltip"], [aria-modal="true"], dialog')) return true;
            const cs = window.getComputedStyle(n);
            return cs.position === 'fixed' || cs.position === 'absolute';
          };
          const obs = new MutationObserver(ms => {
            for (const m of ms) {
              if (m.type === 'attributes' && m.target === document.documentElement && m.attributeName === 'class') { window.__ka11yKbd.count++; continue; }
              if (related(m.target)) { window.__ka11yKbd.count++; continue; }
              for (const a of m.addedNodes) if (a.nodeType === 1 && related(a)) { window.__ka11yKbd.count++; break; }
            }
          });
          obs.observe(document.documentElement, { childList: true, subtree: true, attributes: true, characterData: false });
          window.__ka11yKbd.obs = obs;
          return { focused: document.activeElement === el, state: state() };
        }, MARK, c.idx);
        if (!before || !before.focused) { issues.push({ type: 'not-focusable-programmatically', technique: 'G202', severity: 'review', target: c.target, snippet: c.snippet, detail: 'Element could not receive focus even though it has tabindex/role — verify keyboard reachability' }); continue; }

        const read = () => page.evaluate(() => { const k = window.__ka11yKbd; return k ? { count: k.count, state: k.state() } : null; });
        await page.keyboard.press('Enter'); await sleep(SETTLE_MS);
        const afterEnter = await read();
        if (navigated) { verifiedOperable++; break; }
        await page.evaluate(() => { const k = window.__ka11yKbd; if (k) k.count = 0; });
        await page.keyboard.press('Space'); await sleep(SETTLE_MS);
        const afterSpace = await read();
        if (navigated) { verifiedOperable++; break; }
        const keyReacted = !!(afterEnter && (afterEnter.count > 0 || afterEnter.state !== before.state)) || !!(afterSpace && (afterSpace.count > 0 || afterSpace.state !== before.state));
        if (keyReacted) {
          verifiedOperable++;
          // best-effort undo: toggle back with the same key
          await page.keyboard.press('Escape').catch(() => {});
          await page.evaluate(() => { const k = window.__ka11yKbd; if (k && k.obs) k.obs.disconnect(); delete window.__ka11yKbd; });
          continue;
        }
        if (c.inForm) {
          // Do not click inside forms (could submit); rely on the handler evidence instead.
          issues.push({ type: 'keyboard-no-reaction-unverified', technique: 'G202', severity: 'review', target: c.target, snippet: c.snippet, detail: `Focusable custom control did not react to Enter or Space${c.hasKey ? ' although it has a key handler' : ' and has no keyboard handler'} — inside a form, click was not simulated; verify manually (G202/SCR29)` });
          await page.evaluate(() => { const k = window.__ka11yKbd; if (k && k.obs) k.obs.disconnect(); delete window.__ka11yKbd; });
          continue;
        }
        // Compare with a click.
        await page.evaluate((mark, idx) => { const k = window.__ka11yKbd; if (k) k.count = 0; const el = document.querySelector(`[${mark}="${idx}"]`); if (el) el.click(); }, MARK, c.idx);
        await sleep(SETTLE_MS);
        const afterClick = await read();
        const clickReacted = navigated || !!(afterClick && (afterClick.count > 0 || afterClick.state !== before.state));
        if (clickReacted) {
          issues.push({ type: 'keyboard-inoperable-verified', technique: 'G202', severity: 'fail', target: c.target, snippet: c.snippet, detail: `Custom control reacts to a mouse click (${navigated ? 'navigation' : (afterClick.count + ' DOM change(s)')}) but not to Enter or Space when focused — add a keydown handler for Enter/Space or use a native <button> (G202/SCR29/SCR35)` });
          if (!navigated) { await page.evaluate((mark, idx) => { const el = document.querySelector(`[${mark}="${idx}"]`); if (el) el.click(); }, MARK, c.idx).catch(() => {}); await sleep(80); }
        } else {
          // Neither reacted — the handler may be a no-op or need real pointer coordinates; not a keyboard failure.
        }
        await page.evaluate(() => { const k = window.__ka11yKbd; if (k && k.obs) k.obs.disconnect(); delete window.__ka11yKbd; }).catch(() => {});
      } catch (_) { /* continue with the next candidate */ }
    }
    if (navigated && typeof page.goBack === 'function') { try { await page.goBack({ waitUntil: 'load', timeout: 8000 }); } catch (_) { /* ignore */ } }

    // ── Phase 3: sliders (G216) ──────────────────────────────────────────────
    for (const s of (en.sliders || [])) {
      if (!canSimulate) break;
      try {
        const v0 = await page.evaluate((mark, id) => { const el = document.querySelector(`[${mark}="${id}"]`); if (!el) return null; el.scrollIntoView({ block: 'center' }); el.focus({ preventScroll: true }); const r = el.getBoundingClientRect(); return { v: el.tagName === 'INPUT' ? el.value : el.getAttribute('aria-valuenow'), x: r.left + r.width * 0.85, y: r.top + r.height / 2, w: r.width }; }, MARK, s.id);
        if (!v0) continue;
        await page.keyboard.press('ArrowRight'); await sleep(80);
        const v1 = await page.evaluate((mark, id) => { const el = document.querySelector(`[${mark}="${id}"]`); return el ? (el.tagName === 'INPUT' ? el.value : el.getAttribute('aria-valuenow')) : null; }, MARK, s.id);
        if (v1 === v0.v) {
          await page.keyboard.press('ArrowLeft'); await sleep(80);
          const v1b = await page.evaluate((mark, id) => { const el = document.querySelector(`[${mark}="${id}"]`); return el ? (el.tagName === 'INPUT' ? el.value : el.getAttribute('aria-valuenow')) : null; }, MARK, s.id);
          if (v1b === v0.v) issues.push({ type: 'slider-keyboard-inoperable', technique: 'G216', severity: 'fail', target: s.target, snippet: s.snippet, detail: 'Slider value does not change with Arrow keys — keyboard users cannot operate it (G202/G216)' });
        } else {
          await page.keyboard.press('ArrowLeft').catch(() => {});
        }
        if (page.mouse && typeof page.mouse.click === 'function' && v0.w > 20) {
          const vb = await page.evaluate((mark, id) => { const el = document.querySelector(`[${mark}="${id}"]`); return el ? (el.tagName === 'INPUT' ? el.value : el.getAttribute('aria-valuenow')) : null; }, MARK, s.id);
          await page.mouse.click(v0.x, v0.y); await sleep(80);
          const vc = await page.evaluate((mark, id) => { const el = document.querySelector(`[${mark}="${id}"]`); return el ? (el.tagName === 'INPUT' ? el.value : el.getAttribute('aria-valuenow')) : null; }, MARK, s.id);
          if (vc === vb) issues.push({ type: 'slider-no-single-point-activation', technique: 'G216', severity: 'review', target: s.target, snippet: s.snippet, detail: 'A single click on the slider track did not move the value — provide single-point activation (click on track or +/- buttons) in addition to dragging (G216)' });
        }
      } catch (_) { /* ignore slider */ }
    }
  } finally {
    if (typeof page.off === 'function') page.off('framenavigated', onNav);
    await page.evaluate((mark) => { for (const el of document.querySelectorAll(`[${mark}]`)) el.removeAttribute(mark); const k = window.__ka11yKbd; if (k && k.obs) k.obs.disconnect(); delete window.__ka11yKbd; }, MARK).catch(() => {});
  }

  if (!issues.length) {
    return { successCriteriaId: SC, rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'pass', reason: _t(ctx,
      'No mouse-only or hover-only handlers found on custom controls; {v} custom control(s) verified to react to Enter/Space.',
      'カスタムコントロールにマウス専用/ホバー専用のハンドラーはありません。{v} 件のカスタムコントロールが Enter/Space に反応することを確認しました。', { v: verifiedOperable }), helpUrl: HELP_URL }] };
  }
  const fails = issues.filter(i => i.severity === 'fail');
  const reviews = issues.filter(i => i.severity !== 'fail');
  const rules = [];
  if (fails.length) rules.push({ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: 'critical', status: 'fail', reason: _t(ctx,
    '{n} control(s) are operable only with a mouse ({types}). Every function must be reachable and activatable with the keyboard: use native controls or add tabindex="0" plus Enter/Space key handling.',
    '{n} 件のコントロールがマウスでしか操作できません（{types}）。すべての機能はキーボードで到達・実行できる必要があります。ネイティブコントロールを使うか、tabindex="0" と Enter/Space のキー処理を追加してください。',
    { n: fails.length, types: [...new Set(fails.map(i => i.type))].join(', ') }), elements: fails, helpUrl: HELP_URL });
  if (reviews.length) rules.push({ ruleId: `${RULE_ID}-review`, description: FALLBACK_DESCRIPTION, impact: 'moderate', status: 'incomplete', reason: _t(ctx,
    '{n} control(s) need manual keyboard verification ({types}).', '{n} 件のコントロールはキーボード操作の手動確認が必要です（{types}）。',
    { n: reviews.length, types: [...new Set(reviews.map(i => i.type))].join(', ') }), elements: reviews, helpUrl: HELP_URL });
  return { successCriteriaId: SC, rules };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
