'use strict';

/**
 * WCAG 1.4.3 Contrast (Minimum) — alternate presentations (G174).
 *
 * axe and the Python contrast engine measure the default presentation. This check
 * finds theme / high-contrast toggles (G174), colour-selection tools (G175) and
 * prefers-contrast / forced-colors media queries, then activates the toggle and
 * re-samples text contrast in the alternate mode so both results are reported.
 */

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '1.4.3';
const RULE_ID = 'custom-contrast-alternate-theme';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum';
const MODE = 'interactive';
const FALLBACK_DESCRIPTION = 'Text must have a contrast ratio of at least 4.5:1 (3:1 for large text), in the default or a conforming alternate presentation';

function _t(ctx, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, ctx, en);
}

// Runs inside the page: sample text contrast against the nearest opaque background.
function sampleContrastInPage(limit) {
  const parse = (c) => { const m = String(c || '').match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(',').map(x => parseFloat(x)); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const ratio = (a, b) => { const l1 = lum(a), l2 = lum(b); return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05); };
  const blend = (fg, bg) => ({ r: fg.r * fg.a + bg.r * (1 - fg.a), g: fg.g * fg.a + bg.g * (1 - fg.a), b: fg.b * fg.a + bg.b * (1 - fg.a), a: 1 });
  const bgOf = (el) => {
    let n = el;
    while (n && n !== document.documentElement) {
      const cs = window.getComputedStyle(n);
      if (cs.backgroundImage && cs.backgroundImage !== 'none') return null; // gradient / image — unknown
      const c = parse(cs.backgroundColor);
      if (c && c.a > 0.95) return c;
      n = n.parentElement;
    }
    const root = parse(window.getComputedStyle(document.documentElement).backgroundColor);
    return root && root.a > 0.95 ? root : { r: 255, g: 255, b: 255, a: 1 };
  };
  const out = { sampled: 0, failing: 0, worst: null, unknown: 0 };
  let n = 0;
  for (const el of document.querySelectorAll('p, a, li, h1, h2, h3, h4, h5, h6, span, button, label, td, th, dd, dt, figcaption, small, summary')) {
    if (out.sampled >= limit || n++ > 4000) break;
    let own = false; for (const c of el.childNodes) if (c.nodeType === 3 && c.textContent.trim().length > 1) { own = true; break; }
    if (!own) continue;
    const cs = window.getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) < 0.1) continue;
    const r = el.getBoundingClientRect(); if (r.width < 4 || r.height < 4) continue;
    const fg = parse(cs.color); if (!fg) continue;
    const bg = bgOf(el); if (!bg) { out.unknown++; continue; }
    const f = fg.a < 1 ? blend(fg, bg) : fg;
    const size = parseFloat(cs.fontSize); const bold = parseInt(cs.fontWeight, 10) >= 700 || cs.fontWeight === 'bold';
    const large = size >= 24 || (bold && size >= 18.66);
    const need = large ? 3 : 4.5;
    const rt = ratio(f, bg);
    out.sampled++;
    if (rt < need) { out.failing++; if (!out.worst || rt < out.worst.ratio) out.worst = { ratio: Math.round(rt * 100) / 100, need, text: (el.textContent || '').trim().slice(0, 40), fg: cs.color, bg: `rgb(${Math.round(bg.r)}, ${Math.round(bg.g)}, ${Math.round(bg.b)})` }; }
  }
  return out;
}

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);
  const MARK = 'data-ka11y-theme';

  const detRaw = await page.evaluate((mark) => {
    const out = { toggles: [], pickers: 0, mediaQueries: [], forcedColorsSupport: false };
    const THEME_RE = /high[-\s_]?contrast|contrast|dark[-\s_]?mode|light[-\s_]?mode|night[-\s_]?mode|colou?r[-\s_]?scheme|colou?r[-\s_]?theme|theme[-\s_]?(toggle|switch|select|mode|btn|button)|(toggle|switch|select)[-\s_]?theme|ハイコントラスト|コントラスト|ダークモード|ライトモード|テーマ|配色|色の設定|色を変更/i;
    const text = (el) => [(el.textContent || ''), el.getAttribute('aria-label') || '', el.getAttribute('title') || '', el.className || '', el.id || '', el.getAttribute('name') || ''].join(' ').replace(/\s+/g, ' ');
    const visible = (el) => { const cs = window.getComputedStyle(el); return cs.display !== 'none' && cs.visibility !== 'hidden'; };
    let i = 0;
    for (const el of document.querySelectorAll('button, [role="button"], [role="switch"], input[type="checkbox"], input[type="radio"], select, a[href^="#"], a[href*="theme"], a[href*="contrast"]')) {
      if (!visible(el) || el.closest('[aria-hidden="true"]')) continue;
      const t = text(el);
      if (!THEME_RE.test(t)) continue;
      if (el.tagName === 'SELECT' && !Array.from(el.options).some(o => THEME_RE.test(o.textContent || ''))) continue;
      el.setAttribute(mark, String(i));
      out.toggles.push({ idx: i++, target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''), snippet: el.outerHTML.slice(0, 140), label: t.trim().slice(0, 60), kind: el.tagName === 'SELECT' ? 'select' : (el.type === 'checkbox' || el.getAttribute('role') === 'switch') ? 'switch' : 'button' });
      if (out.toggles.length >= 3) break;
    }
    for (const p of document.querySelectorAll('input[type="color"]')) {
      const l = (p.labels && p.labels[0] ? p.labels[0].textContent : '') + ' ' + (p.getAttribute('aria-label') || '') + ' ' + (p.name || '') + ' ' + (p.id || '');
      if (/background|foreground|text|colou?r|背景|文字|色/i.test(l)) out.pickers++;
    }
    try {
      const seen = new Set();
      const walk = (rules, depth) => { if (!rules || depth > 3) return; for (const r of rules) { try { if (r.media && r.media.mediaText) { const m = r.media.mediaText; if (/prefers-contrast|forced-colors|prefers-color-scheme|inverted-colors/.test(m)) seen.add(m.replace(/\s+/g, ' ').slice(0, 60)); } if (r.cssRules) walk(r.cssRules, depth + 1); } catch (_) { /* ignore */ } } };
      for (const s of document.styleSheets) { try { walk(s.cssRules, 0); } catch (_) { /* cross-origin */ } }
      out.mediaQueries = Array.from(seen);
    } catch (_) { /* ignore */ }
    return out;
  }, MARK);
  const det = detRaw && typeof detRaw === 'object' && !Array.isArray(detRaw) ? detRaw : { toggles: [], mediaQueries: [] };
  const toggles = Array.isArray(det.toggles) ? det.toggles : [];
  const mqs = Array.isArray(det.mediaQueries) ? det.mediaQueries : [];

  const cleanup = () => page.evaluate((mark) => { for (const el of document.querySelectorAll(`[${mark}]`)) el.removeAttribute(mark); }, MARK).catch(() => {});

  if (!toggles.length) {
    await cleanup();
    const notes = [];
    if (mqs.length) notes.push(_t(ctx, `stylesheet responds to ${mqs.join(', ')} (G174 via user preference)`, `スタイルシートが ${mqs.join(', ')} に対応しています（ユーザー設定による G174）`));
    if (det.pickers) notes.push(_t(ctx, `${det.pickers} colour picker(s) for text/background (G175)`, `文字/背景の色選択 ${det.pickers} 件（G175）`));
    return { successCriteriaId: SC, rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: notes.length ? 'pass' : 'not_applicable',
      reason: notes.length ? _t(ctx, 'No theme/contrast toggle on the page, but: {n}. Default-presentation contrast is measured by the contrast rules.', 'ページにテーマ/コントラスト切替はありませんが: {n}。既定表示のコントラストはコントラストルールで測定されます。', { n: notes.join('; ') })
        : _t(ctx, 'No alternate presentation (theme/high-contrast toggle, colour picker or prefers-contrast styles) detected — contrast is judged on the default presentation by the contrast rules.', '代替表示（テーマ/ハイコントラスト切替、色選択、prefers-contrast スタイル）は検出されませんでした。コントラストは既定表示についてコントラストルールで判定されます。'), helpUrl: HELP_URL }] };
  }

  // Measure default, activate toggle, measure again, restore.
  let before = null, after = null, changed = false, restored = true;
  const t = toggles[0];
  try {
    before = await page.evaluate(sampleContrastInPage, 80);
    const activate = () => page.evaluate((mark, idx) => {
      const el = document.querySelector(`[${mark}="${idx}"]`); if (!el) return null;
      const sig = () => [document.documentElement.className, document.documentElement.getAttribute('data-theme'), document.body.className, window.getComputedStyle(document.body).backgroundColor, window.getComputedStyle(document.body).color].join('|');
      const s0 = sig();
      if (el.tagName === 'SELECT') { const o = Array.from(el.options).find(x => x.index !== el.selectedIndex); if (o) { el.value = o.value; el.dispatchEvent(new Event('change', { bubbles: true })); } }
      else el.click();
      return { s0, sig: null };
    }, MARK, t.idx);
    const a0 = await activate();
    await new Promise(r => setTimeout(r, 450));
    const sigNow = await page.evaluate(() => [document.documentElement.className, document.documentElement.getAttribute('data-theme'), document.body.className, window.getComputedStyle(document.body).backgroundColor, window.getComputedStyle(document.body).color].join('|'));
    changed = !!(a0 && sigNow !== a0.s0);
    after = await page.evaluate(sampleContrastInPage, 80);
    // restore
    await activate();
    await new Promise(r => setTimeout(r, 300));
    const sigBack = await page.evaluate(() => [document.documentElement.className, document.documentElement.getAttribute('data-theme'), document.body.className, window.getComputedStyle(document.body).backgroundColor, window.getComputedStyle(document.body).color].join('|'));
    restored = !a0 || sigBack === a0.s0;
    if (!restored) {
      // try once more (three-state toggles) then give up
      await activate(); await new Promise(r => setTimeout(r, 300));
      const sig3 = await page.evaluate(() => [document.documentElement.className, document.documentElement.getAttribute('data-theme'), document.body.className, window.getComputedStyle(document.body).backgroundColor, window.getComputedStyle(document.body).color].join('|'));
      restored = !a0 || sig3 === a0.s0;
    }
  } catch (_) { /* fall through with what we have */ }
  await cleanup();

  const b = before && typeof before === 'object' ? before : { sampled: 0, failing: 0 };
  const a = after && typeof after === 'object' ? after : null;
  const el = [{ target: t.target, snippet: t.snippet, detail: `Toggle "${t.label}" (${t.kind}); default: ${b.failing}/${b.sampled} sampled text elements below threshold${a ? `; alternate mode: ${a.failing}/${a.sampled}` : ''}${changed ? '' : ' — activating the toggle produced no visible change'}${restored ? '' : ' (restore may have failed)'}` }];
  const worst = (x) => x && x.worst ? ` (worst ${x.worst.ratio}:1 for "${x.worst.text}", needs ${x.worst.need}:1)` : '';

  if (!changed) {
    return { successCriteriaId: SC, rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: 'minor', status: 'incomplete', reason: _t(ctx,
      'A theme/contrast control "{l}" was found but activating it did not change the presentation (it may need a page reload or open a menu) — verify the alternate presentation manually (G174). Default presentation: {f} of {s} sampled text elements below the contrast threshold{w}.',
      'テーマ/コントラスト切替「{l}」が見つかりましたが、操作しても表示は変わりませんでした（再読み込みが必要か、メニューを開くだけの可能性があります）。代替表示は手動で確認してください（G174）。既定表示: サンプル {s} 件中 {f} 件がコントラスト基準未満{w}。',
      { l: t.label, f: b.failing, s: b.sampled, w: worst(b) }), elements: el, helpUrl: HELP_URL }] };
  }
  if (b.failing === 0) {
    return { successCriteriaId: SC, rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'pass', reason: _t(ctx,
      'Default presentation passes on {s} sampled text elements; alternate theme "{l}" measured too: {af} of {as} below threshold{w} (G174).',
      '既定表示はサンプル {s} 件すべてで基準を満たします。代替テーマ「{l}」も測定: {as} 件中 {af} 件が基準未満{w}（G174）。',
      { s: b.sampled, l: t.label, af: a ? a.failing : 0, as: a ? a.sampled : 0, w: worst(a) }), elements: el, helpUrl: HELP_URL }] };
  }
  if (a && a.failing === 0 && a.sampled > 0) {
    return { successCriteriaId: SC, rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: 'moderate', status: 'incomplete', reason: _t(ctx,
      'Default presentation has {f} of {s} sampled text elements below the contrast threshold{w}, but the alternate theme "{l}" passes on all {as} samples. G174 allows this only if the toggle is itself accessible, conforming and available on every page — verify.',
      '既定表示ではサンプル {s} 件中 {f} 件がコントラスト基準未満{w}ですが、代替テーマ「{l}」は {as} 件すべてで基準を満たします。G174 では切替自体がアクセシブルで適合し、すべてのページで利用できる場合のみ許容されます。確認してください。',
      { f: b.failing, s: b.sampled, w: worst(b), l: t.label, as: a.sampled }), elements: el, helpUrl: HELP_URL }] };
  }
  return { successCriteriaId: SC, rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: 'serious', status: 'incomplete', reason: _t(ctx,
    'Both presentations have low-contrast text: default {f}/{s}{w}; alternate theme "{l}" {af}/{as}{aw}. Neither the default nor the alternate version conforms (G174).',
    'どちらの表示にも低コントラストのテキストがあります: 既定 {s} 件中 {f} 件{w}、代替テーマ「{l}」{as} 件中 {af} 件{aw}。既定版も代替版も適合していません（G174）。',
    { f: b.failing, s: b.sampled, w: worst(b), l: t.label, af: a ? a.failing : '?', as: a ? a.sampled : '?', aw: worst(a) }), elements: el, helpUrl: HELP_URL }] };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION, sampleContrastInPage };
