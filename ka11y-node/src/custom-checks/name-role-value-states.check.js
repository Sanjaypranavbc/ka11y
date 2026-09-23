'use strict';

/**
 * WCAG 4.1.2 Name, Role, Value — widget states and markup conformance beyond axe.
 *
 *   G108  custom toggles/disclosures must expose their state (aria-expanded / aria-pressed /
 *         aria-checked / aria-selected) and controls must reference what they control
 *   H88   HTML conformance visible in the DOM: obsolete elements, nested interactive
 *         elements, misnested list/table/select children, block content inside inline
 *         phrasing elements
 */

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '4.1.2';
const RULE_ID = 'custom-name-role-value-states';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/name-role-value';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'For all user interface components, the name, role, states and values must be programmatically determinable';

function _t(ctx, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, ctx, en);
}

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  const raw = await page.evaluate(() => {
    const out = { issues: [], controls: 0 };
    const sel = (el) => el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : '');
    const hidden = (el) => { const cs = window.getComputedStyle(el); return cs.display === 'none' || cs.visibility === 'hidden'; };
    const add = (type, technique, el, detail, severity) => out.issues.push({ type, technique, severity: severity || 'fail', target: sel(el), snippet: el.outerHTML.slice(0, 160), detail });
    const R = window.__ka11yRuntime;
    const TOGGLE_HINT = /toggle|accordion|collaps|expand|dropdown|drop-down|menu[-_]?(btn|button|toggle)|hamburger|burger|disclosure|show[-_]?more|read[-_]?more|open|close|tab[-_]?(btn|button)|filter[-_]?toggle/i;

    // ── G108: state exposure on custom widgets ──────────────────────────────
    try {
      for (const el of document.querySelectorAll('button, [role="button"], a[role="button"], [role="tab"], [role="switch"], [role="checkbox"], [role="menuitemcheckbox"], [role="menuitemradio"], [role="option"], [role="treeitem"]')) {
        if (hidden(el) || el.closest('[aria-hidden="true"]')) continue;
        out.controls++;
        const role = (el.getAttribute('role') || (el.tagName === 'BUTTON' ? 'button' : '')).toLowerCase();
        const controls = el.getAttribute('aria-controls');
        const target = controls ? document.getElementById(controls.split(/\s+/)[0]) : null;
        const hasState = el.hasAttribute('aria-expanded') || el.hasAttribute('aria-pressed') || el.hasAttribute('aria-checked') || el.hasAttribute('aria-selected') || el.hasAttribute('aria-haspopup');
        if (role === 'switch' || role === 'checkbox' || role === 'menuitemcheckbox' || role === 'menuitemradio') {
          if (!el.hasAttribute('aria-checked')) add('missing-aria-checked', 'G108', el, `role="${role}" has no aria-checked — its on/off state is not exposed (G108)`);
          continue;
        }
        if (role === 'tab' && !el.hasAttribute('aria-selected')) { add('missing-aria-selected', 'G108', el, 'role="tab" has no aria-selected — the active tab is not exposed (G108)'); continue; }
        if (role === 'option' && !el.hasAttribute('aria-selected') && !el.closest('[aria-multiselectable]')) { add('missing-aria-selected', 'G108', el, 'role="option" has no aria-selected (G108)', 'review'); continue; }
        if (role === 'treeitem' && !el.hasAttribute('aria-expanded') && el.querySelector('[role="group"]')) { add('missing-aria-expanded', 'G108', el, 'Expandable tree item has no aria-expanded (G108)'); continue; }
        if (role === 'button') {
          if (controls && target && !hasState) {
            const collapsible = hidden(target) || target.hidden || /collapse|panel|menu|dropdown|drawer|accordion/i.test(target.className + ' ' + target.id);
            if (collapsible) add('missing-aria-expanded', 'G108', el, `Button controls "#${controls.split(/\s+/)[0]}" (a collapsible region) but has no aria-expanded — screen reader users cannot tell whether it is open (G108)`);
          } else if (!hasState && TOGGLE_HINT.test((el.className || '') + ' ' + (el.id || '') + ' ' + (el.getAttribute('data-toggle') || '') + ' ' + (el.getAttribute('data-bs-toggle') || ''))) {
            const tog = (el.getAttribute('data-toggle') || el.getAttribute('data-bs-toggle') || '').toLowerCase();
            if (tog === 'modal' || tog === 'tooltip' || tog === 'popover') continue;
            add('toggle-without-state', 'G108', el, `Button looks like a toggle/disclosure ("${(el.className || el.id || '').toString().slice(0, 40)}") but exposes no aria-expanded/aria-pressed state (G108)`, 'review');
          }
        }
        if (out.issues.length > 80) break;
      }
      // aria-controls referencing nothing
      for (const el of document.querySelectorAll('[aria-controls]')) {
        const missing = (el.getAttribute('aria-controls') || '').split(/\s+/).filter(id => id && !document.getElementById(id));
        if (missing.length && !hidden(el)) add('aria-controls-dangling', 'G108', el, `aria-controls references missing id(s): ${missing.join(', ')} (G108)`, 'review');
        if (out.issues.length > 100) break;
      }
    } catch (_) { /* ignore */ }

    // ── H88: markup conformance visible after parsing ───────────────────────
    try {
      const OBSOLETE = ['font', 'center', 'marquee', 'blink', 'big', 'tt', 'strike', 'frame', 'frameset', 'acronym', 'applet', 'basefont', 'dir', 'isindex', 'nobr', 'plaintext', 'xmp', 'spacer', 'listing'];
      const obs = document.querySelectorAll(OBSOLETE.join(','));
      for (const el of Array.from(obs).slice(0, 20)) add('obsolete-element', 'H88', el, `<${el.tagName.toLowerCase()}> is obsolete in HTML — assistive technology support is undefined; use conforming markup + CSS (H88)`, 'review');
      // Nested interactive content
      for (const el of Array.from(document.querySelectorAll('a[href] a[href], a[href] button, button a[href], button button, button input, label label, button select, a[href] input:not([type="hidden"])')).slice(0, 20)) {
        add('nested-interactive', 'H88', el, `<${el.tagName.toLowerCase()}> is nested inside another interactive element (<${el.parentElement.closest('a, button, label').tagName.toLowerCase()}>) — invalid HTML; roles/names become ambiguous (H88)`);
      }
      // Misnested structural children
      const misnest = [
        ['li', 'ul, ol, menu, [role="list"], [role="menu"], [role="menubar"]', 'li must be a child of ul/ol/menu'],
        ['dt, dd', 'dl, div', 'dt/dd must be inside dl'],
        ['tr', 'table, thead, tbody, tfoot, [role="table"], [role="grid"], [role="treegrid"]', 'tr must be inside table/thead/tbody/tfoot'],
        ['td, th', 'tr', 'td/th must be inside tr'],
        ['option', 'select, datalist, optgroup', 'option must be inside select/datalist/optgroup'],
        ['legend', 'fieldset', 'legend must be the first child of fieldset'],
        ['figcaption', 'figure', 'figcaption must be inside figure'],
        ['summary', 'details', 'summary must be inside details'],
      ];
      for (const [child, parentSel, msg] of misnest) {
        for (const el of Array.from(document.querySelectorAll(child)).slice(0, 400)) {
          const p = el.parentElement;
          if (!p) continue;
          if (p.matches(parentSel)) continue;
          if (child === 'dt, dd' && p.tagName === 'DIV' && p.parentElement && p.parentElement.tagName === 'DL') continue;
          if (el.hasAttribute('role')) continue; // re-purposed intentionally
          add('misnested-element', 'H88', el, `<${el.tagName.toLowerCase()}> is a child of <${p.tagName.toLowerCase()}> — ${msg}; the implicit role/relationship is lost (H88)`);
          if (out.issues.length > 140) break;
        }
      }
      // Block-level content inside phrasing elements (parser keeps div inside span/b/i/em/strong/label)
      for (const el of Array.from(document.querySelectorAll('span > div, span > p, span > ul, span > ol, span > table, span > h1, span > h2, span > h3, b > div, i > div, em > div, strong > div, label > div, label > p, small > div, a > div, a > p, a > h1, a > h2, a > h3, a > ul')).slice(0, 20)) {
        const p = el.parentElement;
        if (p.tagName === 'A') continue; // HTML5 allows flow content in <a>
        add('block-in-phrasing', 'H88', el, `<${el.tagName.toLowerCase()}> is inside inline <${p.tagName.toLowerCase()}> — block content inside phrasing content is invalid and confuses reading order/semantics (H88)`, 'review');
      }
    } catch (_) { /* ignore */ }

    return out;
  });

  const data = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : { issues: [] };
  const issues = Array.isArray(data.issues) ? data.issues : [];
  if (!issues.length) {
    return { successCriteriaId: SC, rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'pass', reason: _t(ctx,
      '{n} custom control(s) expose their state (aria-expanded/pressed/checked/selected); no obsolete, nested-interactive or misnested elements found.',
      '{n} 件のカスタムコントロールは状態（aria-expanded/pressed/checked/selected）を公開しています。廃止要素、入れ子のインタラクティブ要素、誤った入れ子は見つかりませんでした。', { n: data.controls || 0 }), helpUrl: HELP_URL }] };
  }
  const fails = issues.filter(i => i.severity === 'fail');
  const reviews = issues.filter(i => i.severity !== 'fail');
  const summarize = (list) => [...new Set(list.map(i => `${i.technique}:${i.type}`))].join(', ');
  const rules = [];
  if (fails.length) rules.push({ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: 'serious', status: 'fail', reason: _t(ctx,
    '{n} name/role/value failure(s): {types}. States must be exposed with ARIA and markup must be well-formed so roles are unambiguous.',
    '{n} 件の name/role/value の不備: {types}。状態は ARIA で公開し、ロールが曖昧にならないようマークアップは正しく構成する必要があります。', { n: fails.length, types: summarize(fails) }), elements: fails, helpUrl: HELP_URL });
  if (reviews.length) rules.push({ ruleId: `${RULE_ID}-review`, description: FALLBACK_DESCRIPTION, impact: 'moderate', status: 'incomplete', reason: _t(ctx,
    '{n} item(s) need review: {types}.', '{n} 件の確認が必要です: {types}。', { n: reviews.length, types: summarize(reviews) }), elements: reviews, helpUrl: HELP_URL });
  return { successCriteriaId: SC, rules };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
