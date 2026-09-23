'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '2.2.2';
const RULE_ID = 'custom-pause-stop-hide';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Moving, blinking, or auto-updating content must be pausable, stoppable, or hideable';

// Minimum animation duration to flag (skip loading spinners which are short/essential)
const MIN_ANIM_DURATION_MS = 1000;
// Animation names likely to indicate motion (not just fade or colour change)
const MOTION_KEYWORDS = /scroll|slide|move|marquee|ticker|rotate|spin|bounce|translate|carousel/i;

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

  const data = await page.evaluate((opts) => {
    const issues = [];

    // ── 1. <marquee> elements (definite fail) ────────────────────────────────
    for (const el of document.querySelectorAll('marquee')) {
      const text = (el.textContent || '').trim();
      if (!text) continue;
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) continue;
      issues.push({
        type: 'marquee',
        severity: 'fail',
        target: 'marquee' + (el.id ? `#${CSS.escape(el.id)}` : ''),
        snippet: el.outerHTML.slice(0, 120),
        detail: '<marquee> scrolls text continuously with no pause control',
      });
    }

    // ── 2. <blink> elements (definite fail) ──────────────────────────────────
    for (const el of document.querySelectorAll('blink')) {
      issues.push({
        type: 'blink',
        severity: 'fail',
        target: 'blink',
        snippet: el.outerHTML.slice(0, 120),
        detail: '<blink> causes text to flash continuously — no pause control',
      });
    }

    // ── 3. CSS text-decoration: blink ────────────────────────────────────────
    for (const el of document.querySelectorAll('*')) {
      const cs = window.getComputedStyle(el);
      if ((cs.textDecorationLine || '').includes('blink')) {
        issues.push({
          type: 'css-blink',
          severity: 'fail',
          target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
          snippet: el.outerHTML.slice(0, 120),
          detail: 'text-decoration: blink causes blinking text with no pause control',
        });
        if (issues.length >= 30) break;
      }
    }

    // ── 4. Infinite CSS animations with motion keywords ──────────────────────
    const checked = new Set();
    for (const el of document.querySelectorAll('[style*="animation"],[class]')) {
      if (checked.has(el)) continue;
      checked.add(el);
      const cs = window.getComputedStyle(el);
      if (!cs.animationName || cs.animationName === 'none') continue;
      if (cs.animationIterationCount !== 'infinite') continue;
      const durationMs = parseFloat(cs.animationDuration) * 1000;
      if (isNaN(durationMs) || durationMs < opts.minDurationMs) continue;
      if (!(new RegExp(opts.motionKeywords, 'i')).test(cs.animationName)) continue;

      const rect = el.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) continue;

      // G186: a pause/stop control anywhere on the page — by text, aria-label, title or svg title
      const CTRL_RE = /pause|stop|一時停止|停止|⏸|⏹/i;
      const hasPauseControl = Array.from(document.querySelectorAll('button, [role="button"], a[href], input[type="button"], [aria-pressed]')).some(b =>
        CTRL_RE.test([(b.textContent || ''), b.getAttribute('aria-label') || '', b.getAttribute('title') || '', ...Array.from(b.querySelectorAll('svg title, img[alt]')).map(x => x.getAttribute('alt') || x.textContent || '')].join(' ')));

      issues.push({
        type: 'css-animation',
        severity: 'incomplete',
        target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
        snippet: el.outerHTML.slice(0, 120),
        detail: `Infinite animation "${cs.animationName}" (${Math.round(durationMs)}ms) — ${hasPauseControl ? 'a pause/stop control may be present; verify it controls this animation' : 'no pause/stop/hide control detected on page'}`,
      });
      if (issues.length >= 20) break;
    }

    // ── 5. aria-live assertive regions with content ───────────────────────────
    for (const el of document.querySelectorAll('[aria-live="assertive"],[role="alert"]')) {
      const text = (el.textContent || '').trim();
      if (!text) continue;
      issues.push({
        type: 'aria-live',
        severity: 'incomplete',
        target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
        snippet: el.outerHTML.slice(0, 120),
        detail: 'aria-live="assertive" / role="alert" region has content — if it auto-updates repeatedly, a pause mechanism may be required',
      });
      if (issues.length >= 20) break;
    }

    return { issues };
  }, { minDurationMs: MIN_ANIM_DURATION_MS, motionKeywords: MOTION_KEYWORDS.source });

  if (!data || !Array.isArray(data.issues)) {
    return _pass(ctx, _t(ctx, 'No moving, blinking or auto-updating content detected.', '動く・点滅する・自動更新するコンテンツは検出されませんでした。'));
  }

  // ── Phase 2: JS-driven motion, blinking and auto-updating text (G4/G11/SCR22/G186/G191/SCR36) ──
  // Three DOM snapshots 700 ms apart: text that changes twice = auto-updating; visibility
  // that toggles off and back on = blinking; position that keeps moving = scripted motion.
  let reduceMotion = false;
  try {
    const snap = () => page.evaluate(() => {
      const out = {}; let i = 0;
      for (const el of document.querySelectorAll('body *')) {
        if (i++ > 4000) break;
        if (el.children.length > 3) continue;
        const cs = window.getComputedStyle(el);
        const r = el.getBoundingClientRect();
        if (r.width < 8 || r.height < 8) continue;
        const t = (el.textContent || '').trim();
        if (!t && !el.matches('img, svg, canvas')) continue;
        el.__ka11yPs = el.__ka11yPs || ('p' + i);
        out[el.__ka11yPs] = { t: t.slice(0, 80), v: (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) < 0.15) ? 0 : 1, x: Math.round(r.left), y: Math.round(r.top) };
      }
      return out;
    });
    const sleep = (ms) => new Promise(r => setTimeout(r, ms));
    const s1 = await snap(); await sleep(700); const s2 = await snap(); await sleep(700); const s3 = await snap();
    if (s1 && s2 && s3 && typeof s1 === 'object' && !Array.isArray(s1)) {
      const changing = [], blinking = [], moving = [];
      for (const k of Object.keys(s1)) {
        const a = s1[k], b = s2[k], c = s3[k];
        if (!a || !b || !c) continue;
        if (a.t !== b.t && b.t !== c.t) changing.push(k);
        else if (a.v === c.v && a.v !== b.v) blinking.push(k);
        else if (a.v && b.v && c.v && ((Math.abs(a.x - b.x) > 4 && Math.abs(b.x - c.x) > 4) || (Math.abs(a.y - b.y) > 4 && Math.abs(b.y - c.y) > 4))) moving.push(k);
      }
      const ids = [...changing.slice(0, 8), ...blinking.slice(0, 8), ...moving.slice(0, 8)];
      const info = await page.evaluate((wanted) => {
        const CTRL_RE = /pause|stop|play|mute|一時停止|停止|再生|⏸|⏹/i;
        const nameOf = (el) => [(el.textContent || ''), el.getAttribute('aria-label') || '', el.getAttribute('title') || '', ...Array.from(el.querySelectorAll('svg title, img[alt]')).map(x => x.getAttribute('alt') || x.textContent || '')].join(' ');
        const pageControls = Array.from(document.querySelectorAll('button, [role="button"], a[href], input[type="button"], [aria-pressed]')).filter(el => CTRL_RE.test(nameOf(el))).length;
        const REDUCE_RE = /reduce\s+motion|no\s+animation|static\s+version|stop\s+animation|disable\s+animation|turn\s+off\s+animation|アニメーションを停止|動きを減らす|アニメーションなし|静止版/i;
        let reduce = Array.from(document.querySelectorAll('button, a[href], [role="button"], [role="switch"], input[type="checkbox"], label')).some(el => REDUCE_RE.test(nameOf(el)));
        try { for (const s of document.styleSheets) { for (const r of s.cssRules) { if (r.media && /prefers-reduced-motion/.test(r.media.mediaText)) { reduce = true; break; } } if (reduce) break; } } catch (_) { /* cross-origin */ }
        const R = window.__ka11yRuntime;
        if (R && Array.isArray(R.matchMedia) && R.matchMedia.some(m => /prefers-reduced-motion/.test(m.query))) reduce = true;
        const found = {};
        for (const el of document.querySelectorAll('body *')) {
          if (!el.__ka11yPs || !wanted.includes(el.__ka11yPs)) continue;
          const scope = el.closest('section, figure, article, [class*="carousel" i], [class*="slider" i], [class*="ticker" i], [class*="banner" i], div') || el.parentElement;
          const nearControl = !!scope && Array.from(scope.querySelectorAll('button, [role="button"], a[href], [aria-pressed]')).some(c => CTRL_RE.test(nameOf(c)));
          found[el.__ka11yPs] = { target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''), snippet: el.outerHTML.slice(0, 120), nearControl, isTimer: /^\d{1,2}:\d{2}(?::\d{2})?$/.test((el.textContent || '').trim()), isLive: !!el.closest('[aria-live], [role="status"], [role="log"], [role="timer"]') };
        }
        return { pageControls, reduce, found };
      }, ids);
      const inf = info && typeof info === 'object' && !Array.isArray(info) ? info : { pageControls: 0, reduce: false, found: {} };
      reduceMotion = !!inf.reduce;
      const push = (k, type, what) => {
        const f = inf.found && inf.found[k]; if (!f) return;
        if (f.isTimer && type === 'auto-updating-text') return; // a clock/countdown is a time limit, not 2.2.2 content
        const controlled = f.nearControl || inf.pageControls > 0;
        data.issues.push({ type, severity: controlled ? 'incomplete' : (type === 'js-motion' ? 'fail' : 'incomplete'), target: f.target, snippet: f.snippet,
          detail: `${what} (observed over 1.4 s)${controlled ? ' — a pause/stop control exists; verify it controls this content (G186)' : ' — no pause/stop/hide control found on the page (G4/G186)'}` });
      };
      for (const k of changing.slice(0, 8)) push(k, 'auto-updating-text', 'Text updates automatically by script');
      for (const k of blinking.slice(0, 8)) push(k, 'js-blink', 'Element blinks (visibility toggles) by script — must stop within 5 s or be pausable (G11/SCR22)');
      for (const k of moving.slice(0, 8)) push(k, 'js-motion', 'Element moves continuously by script (ticker/scroller)');
    }
  } catch (_) { /* best effort */ }

  // G191 / SCR36: an on-page "reduce motion / static version" mechanism, or honouring
  // prefers-reduced-motion, satisfies the pause requirement for CSS animations.
  if (reduceMotion) {
    for (const i of data.issues) if (i.type === 'css-animation' || i.type === 'js-motion') { i.severity = 'incomplete'; i.detail += ' — a reduced-motion mechanism exists (G191/SCR36); verify it stops this animation'; }
  }

  if (!data.issues.length) {
    return _pass(ctx, _t(ctx,
      'No <marquee>, <blink>, CSS blink, infinite motion animations, scripted blinking, moving or auto-updating content without pause controls detected{rm}.',
      'marquee、blink、CSS blink、無限モーションアニメーション、スクリプトによる点滅・移動・自動更新コンテンツで一時停止コントロールのないものは検出されませんでした{rm}。',
      { rm: reduceMotion ? _t(ctx, ' (a reduce-motion mechanism is provided — G191)', '（動きを減らす手段が提供されています — G191）') : '' }));
  }

  const hasDefiniteFail = data.issues.some(i => i.severity === 'fail');
  const status = hasDefiniteFail ? 'fail' : 'incomplete';

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: hasDefiniteFail ? 'critical' : 'moderate',
      status,
      reason: _t(ctx,
        '{n} instance(s) of potentially non-pausable moving or auto-updating content ({types}). Ensure users can pause, stop, or hide any content that moves, blinks, or updates automatically.',
        '{n} 件の一時停止できない可能性のある動き・自動更新コンテンツが検出されました（{types}）。',
        {
          n: data.issues.length,
          types: [...new Set(data.issues.map(i => i.type))].join(', '),
        }),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
