'use strict';

/**
 * WCAG 3.2.2 On Input — static complement to the interactive on-input check.
 *
 *   H32  every form that takes typed input needs an explicit submit control
 *   G13  controls that change context on change (auto-submitting selects, navigating
 *        radios/checkboxes) must be preceded by a description of what will happen
 */

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '3.2.2';
const RULE_ID = 'custom-form-submit-controls';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/on-input';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Changing a setting must not automatically change context unless the user is advised beforehand';

function _t(ctx, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, ctx, en);
}

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  const raw = await page.evaluate(() => {
    const out = { issues: [], forms: 0, autoControls: 0 };
    const sel = (el) => el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : (el.name ? `[name="${el.name}"]` : ''));
    const hidden = (el) => { const cs = window.getComputedStyle(el); return cs.display === 'none' || cs.visibility === 'hidden'; };
    const text = (el) => (el ? (el.textContent || '') : '').replace(/\s+/g, ' ').trim();
    const R = window.__ka11yRuntime;
    const CHANGE_SRC = /submit\(|location\.|\.href|window\.open|navigate|router\.push|history\.push/i;
    const ADVISE_RE = /automatically|will\s+(?:take|go|load|change|update|reload|submit|navigate)|takes you|selecting|choosing|on\s+change|when you (?:select|choose)|自動的に|選択すると|移動します|切り替わります|更新されます|送信されます/i;

    // ── H32: forms without a submit control ─────────────────────────────────
    for (const form of document.querySelectorAll('form')) {
      if (hidden(form)) continue;
      out.forms++;
      const typed = form.querySelectorAll('input[type="text"], input[type="search"], input[type="email"], input[type="tel"], input[type="url"], input[type="number"], input[type="password"], input:not([type]), textarea').length;
      if (!typed) continue;
      const submit = form.querySelector('button:not([type="button"]):not([type="reset"]), input[type="submit"], input[type="image"], [role="button"]');
      const external = form.id ? document.querySelector(`button[form="${CSS.escape(form.id)}"], input[type="submit"][form="${CSS.escape(form.id)}"]`) : null;
      if (submit || external) continue;
      const role = form.getAttribute('role') || '';
      out.issues.push({ type: 'form-no-submit', technique: 'H32', severity: role === 'search' || typed === 1 ? 'review' : 'fail', target: sel(form), snippet: form.outerHTML.slice(0, 160),
        detail: `Form with ${typed} text field(s) has no submit button — users must guess that Enter submits; add <button type="submit"> (H32)` });
    }

    // ── G13: change-of-context controls need an advance description ─────────
    const candidates = Array.from(document.querySelectorAll('select, input[type="radio"], input[type="checkbox"]')).filter(el => !hidden(el));
    for (const el of candidates) {
      const inline = (el.getAttribute('onchange') || el.getAttribute('onclick') || el.getAttribute('oninput') || '');
      let auto = CHANGE_SRC.test(inline);
      if (!auto && R && typeof R.hasListener === 'function' && R.hasListener(el, /^(change|input)$/)) {
        // A change listener on a control in a form with no submit button is the classic auto-submit pattern.
        const form = el.form;
        const hasSubmit = form && form.querySelector('button:not([type="button"]), input[type="submit"], input[type="image"]');
        if (form && !hasSubmit) auto = true;
      }
      if (!auto && el.tagName === 'SELECT' && (el.className + ' ' + el.id).match(/jump|goto|redirect|navigate|lang(uage)?[-_]?(switch|select)|region[-_]?select/i)) auto = true;
      if (!auto) continue;
      out.autoControls++;
      // Description: label text, aria-describedby, preceding sibling text, form instructions
      const bits = [];
      if (el.labels) for (const l of el.labels) bits.push(text(l));
      for (const id of (el.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean)) { const n = document.getElementById(id); if (n) bits.push(text(n)); }
      let prev = el.previousElementSibling || (el.parentElement && el.parentElement.previousElementSibling);
      for (let i = 0; i < 2 && prev; i++) { bits.push(text(prev)); prev = prev.previousElementSibling; }
      const form = el.form;
      if (form) { const first = form.querySelector('input, select, textarea'); if (first) { const w = document.createTreeWalker(form, NodeFilter.SHOW_TEXT); let n; while ((n = w.nextNode())) { if (first.compareDocumentPosition(n) & Node.DOCUMENT_POSITION_PRECEDING) bits.push(n.textContent); else break; } } }
      const desc = bits.join(' ');
      if (!ADVISE_RE.test(desc)) {
        out.issues.push({ type: 'auto-change-not-described', technique: 'G13', severity: 'fail', target: sel(el), snippet: el.outerHTML.slice(0, 160),
          detail: `<${el.tagName.toLowerCase()}> changes context on change (${inline ? 'inline handler' : 'change listener without submit button'}) but nothing before it tells the user that selecting a value will navigate/submit (G13)` });
      }
    }
    return out;
  });

  const data = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : { issues: [] };
  const issues = Array.isArray(data.issues) ? data.issues : [];
  if (!data.forms && !data.autoControls) {
    return { successCriteriaId: SC, rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'not_applicable', reason: _t(ctx, 'No forms or change-triggered controls on the page.', 'ページにフォームや変更で動作するコントロールはありません。'), helpUrl: HELP_URL }] };
  }
  if (!issues.length) {
    return { successCriteriaId: SC, rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'pass', reason: _t(ctx,
      '{f} form(s) have explicit submit controls{a}.', '{f} 件のフォームに明示的な送信コントロールがあります{a}。',
      { f: data.forms, a: data.autoControls ? _t(ctx, ` and all ${data.autoControls} auto-changing control(s) are described in advance`, `。自動で動作する ${data.autoControls} 件のコントロールはすべて事前に説明されています`) : '' }), helpUrl: HELP_URL }] };
  }
  const fails = issues.filter(i => i.severity === 'fail');
  const status = fails.length ? 'fail' : 'incomplete';
  return {
    successCriteriaId: SC,
    rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: fails.length ? 'serious' : 'moderate', status,
      reason: _t(ctx, '{n} issue(s): {types}. Provide a submit button for typed input and describe any control that changes context before the user operates it.',
        '{n} 件の問題: {types}。入力フォームには送信ボタンを用意し、コンテキストを変更するコントロールは操作前に説明してください。',
        { n: issues.length, types: [...new Set(issues.map(i => `${i.technique}:${i.type}`))].join(', ') }),
      elements: issues, helpUrl: HELP_URL }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
