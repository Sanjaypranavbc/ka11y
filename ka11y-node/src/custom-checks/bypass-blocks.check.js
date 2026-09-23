'use strict';

/**
 * WCAG 2.4.1 Bypass Blocks — which bypass mechanisms exist, beyond axe's `bypass`.
 *
 *   G1     skip-to-main link at the top of the page
 *   G123   link at the start of a repeated block that jumps to its end
 *   G124   list of in-page links near the top (table of contents)
 *   SCR28  navigation that is collapsed by default (expandable menu) counts as bypass
 *   Advisory when the only mechanism is landmarks/headings and a long nav precedes main.
 */

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '2.4.1';
const RULE_ID = 'custom-bypass-blocks';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/bypass-blocks';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'A mechanism must be available to bypass blocks of content repeated on multiple pages';

function _t(ctx, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, ctx, en);
}

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  const raw = await page.evaluate(() => {
    const out = { mechanisms: [], issues: [], navLinksBeforeMain: 0, hasMain: false, headings: 0 };
    const text = (el) => (el ? (el.textContent || '') : '').replace(/\s+/g, ' ').trim();
    const SKIP_RE = /skip|jump\s+to|go\s+to\s+(?:main|content)|main\s+content|コンテンツへ|本文へ|メインコンテンツ|スキップ|ナビゲーションを飛ばす/i;
    const hidden = (el) => { const cs = window.getComputedStyle(el); return cs.display === 'none'; };
    const targetOf = (a) => { const h = a.getAttribute('href') || ''; if (!h.startsWith('#') || h === '#') return null; try { return document.getElementById(decodeURIComponent(h.slice(1))) || document.querySelector(`[name="${CSS.escape(h.slice(1))}"]`); } catch (_) { return null; } };
    const links = Array.from(document.querySelectorAll('a[href]'));
    const main = document.querySelector('main, [role="main"]');
    out.hasMain = !!main;
    out.headings = document.querySelectorAll('h1, h2, h3, h4, h5, h6, [role="heading"]').length;

    // ── G1: skip link among the first links ─────────────────────────────────
    const first = links.slice(0, 8);
    const skip = first.find(a => (a.getAttribute('href') || '').startsWith('#') && SKIP_RE.test(text(a) + ' ' + (a.getAttribute('aria-label') || '')));
    if (skip) {
      const t = targetOf(skip);
      if (!t) out.issues.push({ type: 'skip-link-broken-target', technique: 'G1', target: 'a[href="' + (skip.getAttribute('href') || '') + '"]', snippet: skip.outerHTML.slice(0, 150), detail: `Skip link "${text(skip)}" points to "${skip.getAttribute('href')}" but no element with that id/name exists (G1)` });
      else {
        out.mechanisms.push('skip link (G1)');
        const focusable = t.matches('a, button, input, select, textarea, [tabindex]') || t.hasAttribute('tabindex');
        if (!focusable && !/^(MAIN|H1|H2|H3|H4|H5|H6|SECTION|ARTICLE|DIV)$/.test(t.tagName)) out.issues.push({ type: 'skip-target-not-focusable', technique: 'G1', target: t.tagName.toLowerCase() + (t.id ? '#' + CSS.escape(t.id) : ''), snippet: t.outerHTML.slice(0, 150), detail: 'Skip link target is not a sectioning element and has no tabindex="-1" — focus may not move (G1)' });
      }
    }

    // ── G123: skip-to-end-of-block links inside nav/aside ───────────────────
    for (const a of links.slice(0, 60)) {
      if (a === skip) continue;
      const block = a.closest('nav, aside, [role="navigation"], [role="complementary"], header, [role="banner"]');
      if (!block) continue;
      if (!(a.getAttribute('href') || '').startsWith('#')) continue;
      if (!SKIP_RE.test(text(a) + ' ' + (a.getAttribute('aria-label') || ''))) continue;
      const t = targetOf(a);
      if (t && (block.compareDocumentPosition(t) & Node.DOCUMENT_POSITION_FOLLOWING) && !block.contains(t)) { out.mechanisms.push('block-end skip link (G123)'); break; }
    }

    // ── G124: in-page link list near the top ───────────────────────────────
    const topLinks = links.slice(0, 30);
    const inPage = topLinks.filter(a => { const h = a.getAttribute('href') || ''; return h.startsWith('#') && h.length > 1 && targetOf(a); });
    if (inPage.length >= 3) {
      const list = inPage[0].closest('ul, ol, nav');
      if (list && inPage.filter(a => list.contains(a)).length >= 3) out.mechanisms.push(`in-page link list of ${inPage.length} anchors (G124)`);
    }

    // ── SCR28: collapsed navigation ─────────────────────────────────────────
    for (const btn of document.querySelectorAll('nav button[aria-expanded="false"], [role="navigation"] button[aria-expanded="false"], header button[aria-expanded="false"], button[aria-controls][aria-expanded="false"]')) {
      const id = btn.getAttribute('aria-controls');
      const target = id ? document.getElementById(id) : (btn.closest('nav') && btn.closest('nav').querySelector('ul, ol'));
      if (target && (hidden(target) || target.hidden)) { out.mechanisms.push('navigation collapsed by default (SCR28)'); break; }
    }

    // Landmarks / headings (axe bypass accepts these)
    if (main) out.mechanisms.push('main landmark');
    if (out.headings) out.mechanisms.push(`${out.headings} heading(s)`);

    // How much repeated content precedes main?
    if (main) {
      for (const a of links) { if (main.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_PRECEDING) out.navLinksBeforeMain++; else break; }
    } else {
      out.navLinksBeforeMain = document.querySelectorAll('nav a[href], header a[href], [role="navigation"] a[href], [role="banner"] a[href]').length;
    }
    return out;
  });

  const data = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : { mechanisms: [], issues: [] };
  const mechanisms = Array.isArray(data.mechanisms) ? data.mechanisms : [];
  const issues = Array.isArray(data.issues) ? data.issues : [];
  const hasSkip = mechanisms.some(m => /G1\)|G123|G124|SCR28/.test(m));

  if (issues.length) {
    return { successCriteriaId: SC, rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: 'serious', status: 'fail',
      reason: _t(ctx, 'Skip mechanism is broken: {detail}', 'スキップ機構が機能していません: {detail}', { detail: issues[0].detail }), elements: issues, helpUrl: HELP_URL }] };
  }
  if (!hasSkip && (data.navLinksBeforeMain || 0) > 15) {
    return { successCriteriaId: SC, rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: 'moderate', status: 'incomplete',
      reason: _t(ctx, '{n} navigation links precede the main content and the only bypass mechanisms are {m}. Keyboard users without landmark navigation must tab through all of them — add a skip link (G1) or collapse the menu by default (SCR28).',
        'メインコンテンツの前にナビゲーションリンクが {n} 件あり、バイパス手段は {m} のみです。ランドマーク移動を使えないキーボード利用者はすべてをタブ移動する必要があります。スキップリンク（G1）を追加するか、メニューを既定で折りたたんでください（SCR28）。',
        { n: data.navLinksBeforeMain, m: mechanisms.join(', ') || _t(ctx, 'none', 'なし') }),
      elements: [{ target: 'nav', detail: `${data.navLinksBeforeMain} links before main content; mechanisms: ${mechanisms.join(', ') || 'none'}` }], helpUrl: HELP_URL }] };
  }
  return { successCriteriaId: SC, rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: mechanisms.length ? 'pass' : 'incomplete',
    reason: mechanisms.length
      ? _t(ctx, 'Bypass mechanism(s) available: {m}{n}.', '利用可能なバイパス手段: {m}{n}。', { m: mechanisms.join(', '), n: data.navLinksBeforeMain ? _t(ctx, ` (${data.navLinksBeforeMain} link(s) precede main content)`, `（メインコンテンツの前にリンク ${data.navLinksBeforeMain} 件）`) : '' })
      : _t(ctx, 'No bypass mechanism detected (no skip link, main landmark or headings).', 'バイパス手段が検出されませんでした（スキップリンク、main ランドマーク、見出しなし）。'), helpUrl: HELP_URL }] };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
