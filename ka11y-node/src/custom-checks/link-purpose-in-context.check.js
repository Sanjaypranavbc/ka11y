'use strict';

/**
 * WCAG 2.4.4 Link Purpose (In Context) — programmatically determined link context.
 *
 * The 2.4.9 check flags generic link text on its own. Under 2.4.4 the same link
 * passes when its purpose can be determined from the link together with its
 * programmatically determined context (G53, H77 list item, H78 paragraph,
 * H79 table cell/headers, H80 preceding heading, H81 nested list, ARIA7/ARIA8
 * aria-labelledby/aria-label). Only links whose context does NOT disambiguate
 * them, or identical generic links in the same context pointing elsewhere, fail.
 */

const { buildKeywordPattern, getKeywordList, getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '2.4.4';
const RULE_ID = 'custom-link-purpose-in-context';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/link-purpose-in-context';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'The purpose of each link must be determinable from the link text together with its programmatically determined context';
const MAX_LINKS = 2000;

function _t(ctx, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, ctx, en);
}

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);
  const genericPattern = buildKeywordPattern(getKeywordList('link_purpose', 'generic_link_keywords', ctx))
    || 'click here|here|read more|more|learn more|details|link|this|continue|go|next|previous|view|see more|download|こちら|詳細|もっと見る|続きを読む|詳しく|リンク|次へ|前へ';

  const raw = await page.evaluate((maxLinks, genericRe) => {
    const re = new RegExp(`^(?:${genericRe})[\\s.。:：>»→]*$`, 'i');
    const out = { checked: 0, generic: 0, resolvedByContext: 0, issues: [] };
    const text = (el) => (el ? (el.textContent || '') : '').replace(/\s+/g, ' ').trim();
    const sel = (el) => 'a' + (el.id ? `#${CSS.escape(el.id)}` : '') + `[href="${(el.getAttribute('href') || '').slice(0, 60)}"]`;
    const hidden = (el) => { const cs = window.getComputedStyle(el); return cs.display === 'none' || cs.visibility === 'hidden'; };
    const wordCount = (s) => (s.match(/[A-Za-z0-9À-ɏ]+/g) || []).length + Math.floor((s.match(/[぀-ヿ㐀-鿿]/g) || []).length / 2);
    const accName = (a) => {
      let name = (a.getAttribute('aria-label') || '').trim();
      if (!name) { const ids = (a.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean); name = ids.map(id => { const n = document.getElementById(id); return n ? text(n) : ''; }).join(' ').trim(); }
      if (!name) { const img = a.querySelector('img[alt]'); if (img && !text(a)) name = (img.getAttribute('alt') || '').trim(); }
      if (!name) name = text(a);
      if (!name) name = (a.getAttribute('title') || '').trim();
      return name;
    };
    const contextOf = (a, name) => {
      const found = [];
      const strip = (s) => s.replace(name, ' ').replace(/\s+/g, ' ').trim();
      // ARIA7/ARIA8 handled by accName. H78 paragraph / H77 list item / H79 table cell
      const p = a.closest('p, dd, figcaption, blockquote');
      if (p) { const t = strip(text(p)); if (wordCount(t) >= 3) found.push({ kind: 'sentence', text: t }); }
      const li = a.closest('li');
      if (li && !found.length) { const t = strip(text(li)); if (wordCount(t) >= 2) found.push({ kind: 'list-item', text: t }); }
      if (li && !found.length) { const parentLi = li.parentElement && li.parentElement.closest('li'); if (parentLi) { const t = strip(text(parentLi.firstChild && parentLi.firstChild.nodeType === 3 ? parentLi.firstChild : parentLi).slice(0, 200)); if (wordCount(t) >= 2) found.push({ kind: 'parent-list-item', text: t }); } }
      const td = a.closest('td, th');
      if (td && !found.length) {
        const t = strip(text(td)); if (wordCount(t) >= 2) found.push({ kind: 'table-cell', text: t });
        const table = td.closest('table');
        if (!found.length && table) {
          const row = td.parentElement; const colIdx = Array.from(row.cells).indexOf(td);
          const rowHeader = row.querySelector('th'); const colHeader = table.querySelector(`thead th:nth-child(${colIdx + 1}), tr:first-child th:nth-child(${colIdx + 1})`);
          const t2 = [rowHeader ? text(rowHeader) : '', colHeader ? text(colHeader) : ''].join(' ').trim();
          if (wordCount(t2) >= 1) found.push({ kind: 'table-headers', text: t2 });
        }
      }
      if (!found.length) {
        // H80: preceding heading in the same container
        let node = a; let heading = null;
        for (let hops = 0; hops < 4 && node && !heading; hops++) {
          let s = node.previousElementSibling;
          while (s && !heading) { if (/^H[1-6]$/.test(s.tagName)) heading = s; else if (s.querySelector) heading = Array.from(s.querySelectorAll('h1,h2,h3,h4,h5,h6')).pop() || null; s = s.previousElementSibling; }
          node = node.parentElement;
          if (!node || /^(MAIN|BODY|ARTICLE|SECTION)$/.test(node.tagName)) { if (node && node !== document.body) { const h = node.querySelector('h1,h2,h3,h4,h5,h6'); if (h && (h.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_FOLLOWING)) heading = heading || h; } break; }
        }
        if (heading) { const t = text(heading); if (wordCount(t) >= 1) found.push({ kind: 'preceding-heading', text: t }); }
      }
      if (!found.length) {
        // Card pattern: link inside a container that has a heading/title text
        const card = a.closest('article, li, section, [class*="card" i], [class*="item" i], [class*="teaser" i]');
        if (card) { const h = card.querySelector('h1,h2,h3,h4,h5,h6,[class*="title" i]'); if (h) { const t = text(h); if (wordCount(t) >= 1 && !re.test(t)) found.push({ kind: 'container-heading', text: t }); } }
      }
      const db = (a.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean).map(id => { const n = document.getElementById(id); return n ? text(n) : ''; }).join(' ').trim();
      if (db) found.push({ kind: 'aria-describedby', text: db });
      return found;
    };

    const seen = new Set();
    const byContext = {};
    for (const a of document.querySelectorAll('a[href]')) {
      if (seen.size >= maxLinks) break;
      if (seen.has(a)) continue; seen.add(a);
      if (hidden(a) || a.closest('[aria-hidden="true"]')) continue;
      const name = accName(a);
      if (!name) continue;
      out.checked++;
      if (!re.test(name)) continue;
      out.generic++;
      const ctxs = contextOf(a, name);
      if (ctxs.length) {
        out.resolvedByContext++;
        const key = ctxs[0].kind + '|' + ctxs[0].text.toLowerCase().slice(0, 120) + '|' + name.toLowerCase();
        (byContext[key] = byContext[key] || []).push({ href: a.href, el: a });
        continue;
      }
      out.issues.push({ type: 'generic-link-no-context', target: sel(a), snippet: a.outerHTML.slice(0, 160), text: name.slice(0, 60),
        detail: `Link text "${name.slice(0, 40)}" is generic and no programmatic context (same sentence, list item, table cell/headers, preceding heading, aria-describedby) disambiguates it (G53/H77–H81)` });
      if (out.issues.length > 40) break;
    }
    // Same generic text + same context but different destinations → context does not disambiguate
    for (const group of Object.values(byContext)) {
      const hrefs = new Set(group.map(g => g.href));
      if (hrefs.size > 1) {
        const a = group[0].el;
        out.issues.push({ type: 'generic-links-same-context-different-targets', target: sel(a), snippet: a.outerHTML.slice(0, 160), text: accName(a).slice(0, 60),
          detail: `${group.length} links with the same generic text share the same context but point to ${hrefs.size} different destinations — the context cannot tell them apart (F63/G53)` });
      }
    }
    return out;
  }, MAX_LINKS, genericPattern);

  const data = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : { issues: [], checked: 0 };
  const issues = Array.isArray(data.issues) ? data.issues : [];
  if (!issues.length) {
    return { successCriteriaId: SC, rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'pass', reason: data.checked
      ? _t(ctx, '{n} link(s) checked; {g} generic link text(s) are disambiguated by their programmatic context (sentence, list item, table cell, heading or aria-describedby).', 'リンク {n} 件を確認。汎用的なリンクテキスト {g} 件はプログラム的なコンテキスト（文、リスト項目、表のセル、見出し、aria-describedby）で区別できます。', { n: data.checked, g: data.resolvedByContext || 0 })
      : _t(ctx, 'No links found to check.', '確認対象のリンクは見つかりませんでした。'), helpUrl: HELP_URL }] };
  }
  const sample = issues.slice(0, 3).map(i => `"${i.text}"`).join(', ');
  return {
    successCriteriaId: SC,
    rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: 'moderate', status: 'fail',
      reason: _t(ctx, '{n} link(s) cannot be understood from the link text plus its context: {sample}. Put the link in a descriptive sentence, list item or table cell, precede it with a heading, or use aria-describedby/aria-label.',
        'リンクテキストとそのコンテキストからでは目的が分からないリンクが {n} 件あります: {sample}。説明的な文・リスト項目・表のセルに配置するか、見出しを前置するか、aria-describedby/aria-label を使ってください。',
        { n: issues.length, sample }),
      elements: issues, helpUrl: HELP_URL }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
