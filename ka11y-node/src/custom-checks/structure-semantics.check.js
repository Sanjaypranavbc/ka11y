'use strict';

/**
 * WCAG 1.3.1 Info and Relationships — structural semantics beyond axe-core.
 *
 *   ARIA12  role="heading" must carry aria-level 1–6
 *   ARIA20  role="region" must have an accessible name
 *   H49     emphasis conveyed only by CSS bold/italic on generic inline elements
 *   ARIA24  icon-font glyphs must be aria-hidden or role="img" with a name
 *   H39     large data tables should have a caption / accessible name
 *   H85     long flat <select> lists whose option labels look grouped need <optgroup>
 *   H48     runs of adjacent links that are not in a list
 *   ARIA17  related radio/checkbox controls need fieldset/legend or role=group/radiogroup
 *   H71     fieldset must have a non-empty legend
 *   G115    fake controls, fake headings and fake tables built from generic elements
 *   H63     irregular tables (rowspan/colspan, multi-row headers) need headers/id
 *   G140    layout tables, <font>/<center>, and lists faked with <br> + bullet characters
 */

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '1.3.1';
const RULE_ID = 'custom-structure-semantics';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/info-and-relationships';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Information, structure and relationships conveyed through presentation must be programmatically determinable';

function _t(ctx, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, ctx, en);
}

function _rule(ruleId, status, impact, reason, elements) {
  const r = { ruleId, description: FALLBACK_DESCRIPTION, impact, status, reason, helpUrl: HELP_URL };
  if (elements && elements.length) r.elements = elements;
  return r;
}

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  const raw = await page.evaluate(() => {
    const out = { issues: [], counts: {} };
    const sel = (el) => el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : '');
    const hiddenFromAT = (el) => !!el.closest('[aria-hidden="true"]');
    const visible = (el) => {
      const cs = window.getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') return false;
      const r = el.getBoundingClientRect();
      return r.width > 0 || r.height > 0;
    };
    const accName = (el) => {
      const bits = [el.getAttribute('aria-label') || ''];
      for (const id of (el.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean)) {
        const ref = document.getElementById(id);
        if (ref) bits.push(ref.textContent || '');
      }
      return bits.join(' ').replace(/\s+/g, ' ').trim();
    };
    const R = window.__ka11yRuntime;
    const hasListener = (el, re) => !!(R && typeof R.hasListener === 'function' && R.hasListener(el, re));
    const add = (type, technique, el, detail, severity) => {
      out.issues.push({ type, technique, severity: severity || 'fail', target: sel(el), snippet: el.outerHTML.slice(0, 160), detail });
    };
    const bodyFont = parseFloat(window.getComputedStyle(document.body).fontSize) || 16;

    // ── ARIA12 ───────────────────────────────────────────────────────────────
    try {
      for (const el of document.querySelectorAll('[role="heading"]')) {
        const lvl = parseInt(el.getAttribute('aria-level') || '', 10);
        if (!(lvl >= 1 && lvl <= 6)) add('heading-role-no-level', 'ARIA12', el, `role="heading" ${isNaN(lvl) ? 'has no aria-level' : `has aria-level="${lvl}"`} — a valid level 1–6 is required so the heading fits the outline (ARIA12)`);
      }
    } catch (_) { /* ignore */ }

    // ── ARIA20 ───────────────────────────────────────────────────────────────
    try {
      for (const el of document.querySelectorAll('[role="region"]')) {
        if (hiddenFromAT(el)) continue;
        if (!accName(el)) add('region-no-name', 'ARIA20', el, 'role="region" without aria-label/aria-labelledby is not exposed as a landmark — name it or use a more specific landmark role (ARIA20)');
      }
    } catch (_) { /* ignore */ }

    // ── H49: emphasis via CSS only ───────────────────────────────────────────
    try {
      let n = 0, flagged = 0;
      for (const el of document.querySelectorAll('p span, p div, li span, td span, dd span, blockquote span')) {
        if (n++ > 2500 || flagged >= 15) break;
        if (el.children.length || el.closest('a, button, strong, em, b, i, h1, h2, h3, h4, h5, h6, code, pre, label, [role]')) continue;
        const text = (el.textContent || '').trim();
        if (text.length < 2 || text.length > 80) continue;
        const parentText = (el.parentElement.textContent || '').trim();
        if (parentText.length <= text.length + 10) continue; // whole block styled — not emphasis within
        const cs = window.getComputedStyle(el), pcs = window.getComputedStyle(el.parentElement);
        const boldNow = parseInt(cs.fontWeight, 10) >= 600 || cs.fontWeight === 'bold' || cs.fontWeight === 'bolder';
        const boldParent = parseInt(pcs.fontWeight, 10) >= 600 || pcs.fontWeight === 'bold';
        const italicNow = cs.fontStyle === 'italic' && pcs.fontStyle !== 'italic';
        if ((boldNow && !boldParent) || italicNow) {
          flagged++;
          add('css-only-emphasis', 'H49', el, `"${text.slice(0, 40)}" is emphasised only with CSS ${boldNow ? 'bold' : 'italic'} on a <${el.tagName.toLowerCase()}> — use <strong>/<em> so the emphasis is programmatically determinable (H49)`, 'review');
        }
      }
    } catch (_) { /* ignore */ }

    // ── ARIA24: icon fonts ───────────────────────────────────────────────────
    try {
      const ICON_CLASS = /(^|\s)(fa|fas|far|fab|fal|fad|fa-[\w-]+|material-icons|material-symbols[\w-]*|glyphicon|glyphicon-[\w-]+|icon-[\w-]+|bi-[\w-]+|mdi|mdi-[\w-]+|ion-[\w-]+|icofont-[\w-]+|dashicons[\w-]*|feather[\w-]*|lucide[\w-]*)(\s|$)/;
      let n = 0;
      for (const el of document.querySelectorAll('i, span, em')) {
        if (n++ > 4000) break;
        const cls = el.getAttribute('class') || '';
        if (!ICON_CLASS.test(cls)) continue;
        if (hiddenFromAT(el) || !visible(el)) continue;
        const role = el.getAttribute('role') || '';
        const ownText = (el.textContent || '').trim();
        if (role === 'img' && accName(el)) continue;
        if (role === 'presentation' || role === 'none') continue;
        const parentCtl = el.closest('a, button, [role="button"], [role="link"], [role="tab"], [role="menuitem"]');
        if (ownText && /material/.test(cls)) {
          add('icon-font-ligature-read', 'ARIA24', el, `Icon-font ligature "${ownText.slice(0, 20)}" is read aloud as text — add aria-hidden="true" (and a name on the control) or role="img" + aria-label (ARIA24)`);
          continue;
        }
        if (parentCtl) {
          const ctlName = accName(parentCtl) || (parentCtl.textContent || '').replace(ownText, '').trim() || (parentCtl.querySelector('img[alt]') ? parentCtl.querySelector('img[alt]').getAttribute('alt') : '');
          if (ctlName) continue; // control is named; unannounced glyph is harmless
          add('icon-font-only-control', 'ARIA24', el, 'Icon-font glyph is the only content of a control with no accessible name — give the icon role="img" + aria-label or label the control (ARIA24)');
          continue;
        }
        if (!role) add('icon-font-no-role', 'ARIA24', el, 'Standalone icon-font glyph has neither aria-hidden="true" (decorative) nor role="img" + aria-label (meaningful) (ARIA24)', 'review');
        if (out.issues.length > 120) break;
      }
    } catch (_) { /* ignore */ }

    // ── Tables: H39, H63, G140 layout tables ─────────────────────────────────
    try {
      for (const table of document.querySelectorAll('table')) {
        if (hiddenFromAT(table) || !visible(table)) continue;
        const role = (table.getAttribute('role') || '').toLowerCase();
        const rows = Array.from(table.rows || []);
        const cols = rows.length ? Math.max(...rows.map(r => r.cells.length)) : 0;
        const ths = table.querySelectorAll('th').length;
        const hasCaption = !!(table.caption && (table.caption.textContent || '').trim()) || !!accName(table);
        if (role === 'presentation' || role === 'none') continue;
        out.counts.tables = (out.counts.tables || 0) + 1;
        // H39: big data tables without caption
        if (ths > 0 && rows.length > 3 && cols > 3 && !hasCaption) {
          add('data-table-no-caption', 'H39', table, `Data table (${rows.length}×${cols}) has no <caption> or aria-label — add one so the table's purpose is announced (H39)`, 'review');
        }
        // H63: irregular tables need headers/id
        const spanned = table.querySelectorAll('td[rowspan]:not([rowspan="1"]), td[colspan]:not([colspan="1"]), th[rowspan]:not([rowspan="1"]), th[colspan]:not([colspan="1"])').length;
        const headerRows = rows.filter(r => r.cells.length && Array.from(r.cells).every(c => c.tagName === 'TH')).length;
        if (ths > 0 && (spanned > 0 || headerRows > 1)) {
          const usesHeaders = table.querySelectorAll('td[headers]').length > 0;
          if (!usesHeaders) add('irregular-table-no-headers', 'H63', table, `Table with ${spanned ? spanned + ' spanned cell(s)' : ''}${spanned && headerRows > 1 ? ' and ' : ''}${headerRows > 1 ? headerRows + ' header rows' : ''} relies on scope only — use headers/id associations for cells with multiple headers (H63)`, 'review');
        }
        // G140: layout tables
        if (ths === 0 && !hasCaption && rows.length >= 1 && cols >= 2) {
          const cells = Array.from(table.querySelectorAll('td'));
          const layoutish = cells.filter(c => c.querySelector('img, form, input, button, nav, ul, table, h1, h2, h3, div')).length;
          if (cells.length && layoutish >= cells.length * 0.5) {
            add('layout-table-no-role', 'G140', table, `Table has no header cells and its cells hold layout content (images/forms/blocks) — it is a layout table: add role="presentation" or move to CSS layout (G140)`, 'review');
          }
        }
      }
    } catch (_) { /* ignore */ }

    // ── H85: optgroup ────────────────────────────────────────────────────────
    try {
      for (const s of document.querySelectorAll('select')) {
        if (s.querySelector('optgroup')) continue;
        const labels = Array.from(s.options).map(o => (o.label || o.textContent || '').trim()).filter(Boolean);
        if (labels.length < 15) continue;
        const SEP = /\s[-–:/|>]\s|[:：/]/;
        const withSep = labels.filter(l => SEP.test(l)).length;
        const prefixes = {};
        for (const l of labels) { const p = l.split(SEP)[0].trim().toLowerCase(); if (p && p !== l.toLowerCase()) prefixes[p] = (prefixes[p] || 0) + 1; }
        const groups = Object.values(prefixes).filter(c => c >= 3).length;
        if (withSep >= labels.length * 0.5 && groups >= 2) {
          add('select-needs-optgroup', 'H85', s, `<select> with ${labels.length} options whose labels repeat ${groups} prefixes ("A - x", "A - y", ...) — group them with <optgroup label> (H85)`, 'review');
        }
      }
    } catch (_) { /* ignore */ }

    // ── H48: adjacent links not in a list ────────────────────────────────────
    try {
      const seenParents = new Set();
      let flagged = 0;
      for (const a of document.querySelectorAll('a[href]')) {
        const parent = a.parentElement;
        if (!parent || seenParents.has(parent) || flagged >= 10) continue;
        seenParents.add(parent);
        if (parent.closest('ul, ol, nav, [role="list"], [role="navigation"], [role="menu"], [role="menubar"], [role="tablist"], table, p, h1, h2, h3, h4, h5, h6')) continue;
        if (hiddenFromAT(parent) || !visible(parent)) continue;
        // count runs of anchors separated only by whitespace / <br> / separators like | ·
        let run = 0, best = 0;
        for (const node of parent.childNodes) {
          if (node.nodeType === 1 && node.tagName === 'A' && node.hasAttribute('href')) { run++; best = Math.max(best, run); continue; }
          if (node.nodeType === 3 && /^[\s|·•,\/]*$/.test(node.textContent)) continue;
          if (node.nodeType === 1 && (node.tagName === 'BR' || (node.tagName === 'SPAN' && /^[\s|·•,\/]*$/.test(node.textContent)))) continue;
          run = 0;
        }
        if (best >= 4) {
          flagged++;
          add('link-group-not-list', 'H48', parent, `${best} adjacent links are laid out as siblings (with <br>/separators) instead of a list — mark them up as <ul>/<ol> so users learn the count and can jump between items (H48)`, 'review');
        }
      }
    } catch (_) { /* ignore */ }

    // ── ARIA17 / H71: grouping of related controls, legends ──────────────────
    try {
      const inGroup = (el) => !!el.closest('fieldset, [role="group"], [role="radiogroup"]');
      const byName = {};
      for (const r of document.querySelectorAll('input[type="radio"]')) {
        if (hiddenFromAT(r)) continue;
        const key = (r.form ? 'f' + Array.from(document.forms).indexOf(r.form) : 'nf') + '|' + (r.name || '');
        (byName[key] = byName[key] || []).push(r);
      }
      for (const group of Object.values(byName)) {
        if (group.length < 2) continue;
        if (group.every(inGroup)) continue;
        add('radio-group-ungrouped', 'ARIA17', group[0], `${group.length} radio buttons share name="${group[0].name}" but are not inside <fieldset>/<legend> or role="radiogroup" with a name — the question they answer is not associated with them (ARIA17/H71)`);
      }
      // checkbox clusters: ≥3 checkboxes under the same parent container without a group
      const cbParents = new Map();
      for (const cb of document.querySelectorAll('input[type="checkbox"]')) {
        if (hiddenFromAT(cb) || inGroup(cb)) continue;
        const p = cb.closest('ul, ol, div, td, form, section') || cb.parentElement;
        if (!p) continue;
        cbParents.set(p, (cbParents.get(p) || 0) + 1);
      }
      for (const [p, count] of cbParents) {
        if (count >= 3 && !p.closest('table')) add('checkbox-group-ungrouped', 'ARIA17', p, `${count} related checkboxes share a container without <fieldset>/<legend> or role="group" + name — the group's purpose is not programmatically associated (ARIA17)`, 'review');
      }
      for (const fs of document.querySelectorAll('fieldset')) {
        if (hiddenFromAT(fs)) continue;
        const legend = fs.querySelector(':scope > legend');
        const legendText = legend ? (legend.textContent || '').trim() : '';
        if (!legend || !legendText) {
          if (!accName(fs)) add('fieldset-empty-legend', 'H71', fs, legend ? '<fieldset> has an empty <legend> — the group has no name (H71)' : '<fieldset> has no <legend> (or aria-label) naming the group (H71)');
        }
      }
    } catch (_) { /* ignore */ }

    // ── G115: fake controls / headings / tables ───────────────────────────────
    try {
      let n = 0, fakeCtl = 0;
      const CLICK_RE = /^(click|mousedown|mouseup|pointerdown|pointerup|touchstart|touchend)$/;
      for (const el of document.querySelectorAll('div, span, li, p, img, svg, td')) {
        if (n++ > 5000 || fakeCtl >= 20) break;
        if (el.getAttribute('role') || el.closest('a[href], button, [role="button"], [role="link"], [role="tab"], [role="menuitem"], [role="option"], [role="checkbox"], [role="switch"], [role="treeitem"], label, summary')) continue;
        const inline = el.hasAttribute('onclick') || el.hasAttribute('onmousedown');
        let listener = hasListener(el, CLICK_RE);
        if (!listener && !inline) {
          // React attaches props on the element; delegated handlers are invisible to the registry.
          try {
            const key = Object.keys(el).find(k => k.startsWith('__reactProps'));
            if (key && el[key] && typeof el[key].onClick === 'function') listener = true;
          } catch (_) { /* ignore */ }
        }
        if (!listener && !inline) continue;
        if (!visible(el) || hiddenFromAT(el)) continue;
        if (el.querySelector('a[href], button, input, select, textarea, [role="button"], [role="link"]')) continue; // container delegating to real controls
        const cs = window.getComputedStyle(el);
        if (cs.cursor !== 'pointer' && !inline) continue; // only elements that visually present as controls
        fakeCtl++;
        add('fake-control-no-role', 'G115', el, `<${el.tagName.toLowerCase()}> has a click handler and pointer cursor but no role, name or keyboard focus — use <button>/<a> or add role, tabindex="0" and key handling (G115)`);
      }
      // Fake headings: styled div/span/p that look like headings
      let fh = 0, m = 0;
      for (const el of document.querySelectorAll('div, span, p, b, strong')) {
        if (m++ > 4000 || fh >= 12) break;
        if (el.closest('h1, h2, h3, h4, h5, h6, [role="heading"], a, button, nav, li, table, label, header, footer')) continue;
        if (el.children.length > 1) continue;
        const text = (el.textContent || '').trim();
        if (text.length < 3 || text.length > 100 || /[.!?。]\s*\S/.test(text)) continue;
        if (!visible(el) || hiddenFromAT(el)) continue;
        const cs = window.getComputedStyle(el);
        if (cs.display.includes('inline') && el.tagName !== 'SPAN' && el.tagName !== 'B' && el.tagName !== 'STRONG') continue;
        const size = parseFloat(cs.fontSize) || bodyFont;
        const bold = parseInt(cs.fontWeight, 10) >= 600 || cs.fontWeight === 'bold';
        if (!(size >= bodyFont * 1.35 && bold) && !(size >= bodyFont * 1.7)) continue;
        // Must be followed by body content (a paragraph or list) to be a heading candidate
        const next = el.nextElementSibling || (el.parentElement && el.parentElement.nextElementSibling);
        if (!next || !/^(P|UL|OL|DIV|SECTION|TABLE|DL|FIGURE|ARTICLE)$/.test(next.tagName)) continue;
        if ((next.textContent || '').trim().length < 40) continue;
        fh++;
        add('fake-heading', 'G115', el, `"${text.slice(0, 50)}" is styled as a heading (${Math.round(size)}px${bold ? ', bold' : ''}) but is a <${el.tagName.toLowerCase()}> — use <h1>–<h6> so it appears in the heading outline (G115)`, 'review');
      }
      // Fake tables: CSS display:table on non-table elements, or grids of repeated text cells
      let ft = 0;
      for (const el of document.querySelectorAll('div, ul, section')) {
        if (ft >= 6) break;
        if (el.getAttribute('role') === 'table' || el.getAttribute('role') === 'grid' || el.closest('table, [role="table"], [role="grid"]')) continue;
        const cs = window.getComputedStyle(el);
        const kids = Array.from(el.children).filter(visible);
        if (cs.display === 'table' && kids.length >= 3 && kids.every(k => window.getComputedStyle(k).display === 'table-row')) {
          const cols = kids.map(k => k.children.length);
          if (cols[0] >= 2 && cols.every(c => c === cols[0])) {
            ft++;
            add('fake-table-css', 'G115', el, `${kids.length}×${cols[0]} block uses CSS display:table/table-row on <${el.tagName.toLowerCase()}> — tabular data needs a real <table> with <th> (or role="table"/"row"/"columnheader") (G115)`, 'review');
          }
        }
      }
    } catch (_) { /* ignore */ }

    // ── G140: obsolete presentational elements, <br>-built lists ────────────
    try {
      for (const el of document.querySelectorAll('font, center')) {
        if (!visible(el)) continue;
        add('presentational-element', 'G140', el, `<${el.tagName.toLowerCase()}> is a presentational element — move styling to CSS (G140)`);
        if (out.issues.length > 200) break;
      }
      const BULLET = /^\s*(?:[•·●○■□▪▫‣⁃◦\-–—*]|[①-⑳]|\(?\d{1,2}[.)]|[a-z][.)])\s+\S/;
      let fl = 0;
      for (const el of document.querySelectorAll('p, div, td, dd, span')) {
        if (fl >= 10) break;
        if (el.closest('ul, ol, li, pre, code, table th, nav') || !el.querySelector(':scope > br')) continue;
        if (!visible(el) || hiddenFromAT(el)) continue;
        const html = el.innerHTML;
        const lines = html.split(/<br\s*\/?>/i).map(h => h.replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').trim()).filter(Boolean);
        if (lines.length < 3) continue;
        const bulleted = lines.filter(l => BULLET.test(l)).length;
        if (bulleted >= 3 && bulleted >= lines.length * 0.6) {
          fl++;
          add('fake-list-br', 'G140', el, `${bulleted} lines start with bullet/number characters and are separated by <br> — use <ul>/<ol> so the list structure is exposed (G140)`);
        }
      }
    } catch (_) { /* ignore */ }

    return out;
  });

  const data = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : { issues: [] };
  const issues = Array.isArray(data.issues) ? data.issues : [];

  if (!issues.length) {
    return {
      successCriteriaId: SC,
      rules: [_rule(RULE_ID, 'pass', null, _t(ctx,
        'No additional structure/relationship issues: heading roles carry levels, regions are named, icon fonts are handled, radio/checkbox groups are grouped, legends are present, no fake headings/controls/tables/lists or presentational elements detected.',
        '追加の構造・関係性の問題はありません: heading ロールにレベルがあり、region に名前があり、アイコンフォントは適切に処理され、ラジオ/チェックボックスはグループ化され、legend が存在し、疑似見出し/コントロール/テーブル/リストや表示専用要素は検出されませんでした。'))],
    };
  }

  const fails = issues.filter(i => i.severity === 'fail');
  const reviews = issues.filter(i => i.severity !== 'fail');
  const summarize = (list) => [...new Set(list.map(i => `${i.technique}:${i.type}`))].join(', ');
  const rules = [];
  if (fails.length) {
    rules.push(_rule(RULE_ID, 'fail', 'serious', _t(ctx,
      '{n} structure/relationship failure(s): {types}. Relationships visible on screen (headings, groups, controls, lists) must also exist in the markup.',
      '{n} 件の構造・関係性の不備があります: {types}。画面上で分かる関係（見出し、グループ、コントロール、リスト）はマークアップでも表現されている必要があります。',
      { n: fails.length, types: summarize(fails) }), fails));
  }
  if (reviews.length) {
    rules.push(_rule(`${RULE_ID}-review`, 'incomplete', 'moderate', _t(ctx,
      '{n} structural pattern(s) need review: {types}.',
      '{n} 件の構造パターンの確認が必要です: {types}。',
      { n: reviews.length, types: summarize(reviews) }), reviews));
  }
  return { successCriteriaId: SC, rules };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
