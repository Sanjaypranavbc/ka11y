'use strict';

/**
 * WCAG 3.3.2 Labels or Instructions — beyond axe's label presence rules.
 *
 *   G162  label placement relative to its control (above/left for text, right for check/radio)
 *   ARIA2 required fields need a visible required cue, not only aria-required
 *   ARIA1 aria-describedby instructions are credited; dangling references are flagged
 *   G131  label text should match the kind of input (email/tel/password/url/date)
 *   G167  an adjacent submit button can act as the label of an otherwise unlabelled field (advisory)
 *   G89   constrained inputs (pattern/date/tel/email/url/maxlength) need a visible format hint
 *   G184  forms with several required fields should carry instructions before the first field
 */

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '3.3.2';
const RULE_ID = 'custom-form-labels-instructions';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/labels-or-instructions';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Labels or instructions must be provided when content requires user input';

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
    const out = { issues: [], counts: { inputs: 0, forms: 0, describedBy: 0, requiredWithCue: 0 } };
    const sel = (el) => el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : (el.name ? `[name="${el.name}"]` : ''));
    const hidden = (el) => { const cs = window.getComputedStyle(el); const r = el.getBoundingClientRect(); return cs.display === 'none' || cs.visibility === 'hidden' || (r.width === 0 && r.height === 0); };
    const text = (el) => (el ? (el.textContent || '') : '').replace(/\s+/g, ' ').trim();
    const add = (type, technique, el, detail, severity) => out.issues.push({ type, technique, severity: severity || 'review', target: sel(el), snippet: el.outerHTML.slice(0, 160), detail });
    const REQ_WORD = /required|mandatory|必須|\*|※必須|obligatoire|erforderlich|obligatorio/i;
    const FORMAT_WORD = /format|e\.g\.|for example|example|such as|yyyy|dd\/mm|mm\/dd|\d{2,4}[-\/]\d{2}|digits|characters|@|xxx|例|形式|半角|全角|ハイフン|桁/i;

    const labelsFor = (input) => {
      const labels = [];
      if (input.labels) for (const l of input.labels) labels.push(l);
      const wrap = input.closest('label');
      if (wrap && !labels.includes(wrap)) labels.push(wrap);
      return labels;
    };
    const describedText = (input) => {
      const ids = (input.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean);
      let txt = '', dangling = [];
      for (const id of ids) { const n = document.getElementById(id); if (!n) dangling.push(id); else txt += ' ' + text(n); }
      return { txt: txt.trim(), dangling, ids };
    };
    const nameOf = (input) => {
      const bits = [input.getAttribute('aria-label') || '', ...labelsFor(input).map(text)];
      for (const id of (input.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean)) { const n = document.getElementById(id); if (n) bits.push(text(n)); }
      return bits.join(' ').trim();
    };
    const adjacentText = (input) => {
      // text in the same container row: previous/next siblings and parent's own text nodes
      const parent = input.parentElement;
      if (!parent) return '';
      const bits = [];
      for (const n of parent.childNodes) {
        if (n === input) continue;
        if (n.nodeType === 3) bits.push(n.textContent);
        else if (n.nodeType === 1 && !/^(INPUT|SELECT|TEXTAREA|BUTTON)$/.test(n.tagName)) bits.push(n.textContent);
      }
      const prev = parent.previousElementSibling;
      if (prev && !prev.querySelector('input, select, textarea')) bits.push(prev.textContent);
      return bits.join(' ').replace(/\s+/g, ' ').trim().slice(0, 400);
    };

    const inputs = Array.from(document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="reset"]):not([type="image"]), select, textarea'))
      .filter(i => !hidden(i) && !i.closest('[aria-hidden="true"]'));
    out.counts.inputs = inputs.length;

    for (const input of inputs) {
      const type = (input.getAttribute('type') || input.tagName).toLowerCase();
      const labels = labelsFor(input);
      const label = labels.find(l => !hidden(l)) || null;
      const name = nameOf(input);
      const desc = describedText(input);
      if (desc.ids.length) out.counts.describedBy++;

      // ── ARIA1: dangling aria-describedby ────────────────────────────────
      if (desc.dangling.length) add('describedby-dangling', 'ARIA1', input, `aria-describedby references missing id(s): ${desc.dangling.join(', ')} — instructions are not associated (ARIA1)`, 'fail');

      // ── G162: label position ────────────────────────────────────────────
      try {
        if (label && label !== input.closest('label')) {
          const lr = label.getBoundingClientRect(), ir = input.getBoundingClientRect();
          if (lr.width && ir.width) {
            const isCheck = type === 'checkbox' || type === 'radio';
            const above = lr.bottom <= ir.top + 4;
            const left = lr.right <= ir.left + 6 && lr.top < ir.bottom && lr.bottom > ir.top;
            const right = lr.left >= ir.right - 6 && lr.top < ir.bottom && lr.bottom > ir.top;
            const below = lr.top >= ir.bottom - 4;
            if (isCheck && (left || above) && !right) add('label-position-unconventional', 'G162', input, `Label for this ${type} sits ${left ? 'to the left of' : 'above'} the control — checkbox/radio labels are conventionally placed to the right (G162)`);
            else if (!isCheck && (below || right)) add('label-position-unconventional', 'G162', input, `Label for this field sits ${below ? 'below' : 'to the right of'} the control — text field labels are conventionally above or to the left (G162)`);
          }
        }
      } catch (_) { /* ignore */ }

      // ── ARIA2: required cue ─────────────────────────────────────────────
      const required = input.required || input.getAttribute('aria-required') === 'true';
      if (required) {
        const cueText = [name, desc.txt, adjacentText(input), input.getAttribute('placeholder') || ''].join(' ');
        const hasCue = REQ_WORD.test(cueText) || !!(label && label.querySelector('[class*="required" i], [class*="asterisk" i], abbr[title*="required" i], .req'));
        if (hasCue) out.counts.requiredWithCue++;
        else add('required-no-visible-cue', 'ARIA2', input, 'Field is required (required/aria-required) but nothing visible tells sighted users so — add "(required)" or an explained asterisk to the label (ARIA2/G83)');
      }

      // ── G131: label/type mismatch ───────────────────────────────────────
      if (name) {
        const n = name.toLowerCase();
        const mismatch = (type === 'email' && !/mail|メール|e-?mail|correo|courriel/.test(n))
          || (type === 'tel' && !/phone|tel|mobile|fax|電話|携帯|番号/.test(n))
          || (type === 'password' && !/pass|pin|パスワード|暗証/.test(n))
          || (type === 'url' && !/url|website|link|site|address|ホームページ|サイト|リンク/.test(n));
        if (mismatch) add('label-type-mismatch', 'G131', input, `Label "${name.slice(0, 40)}" does not indicate that a ${type} value is expected — make the label say what to enter (G131)`);
      }

      // ── G167 / unlabeled search with adjacent button ────────────────────
      if (!name && !input.getAttribute('title')) {
        const next = input.nextElementSibling;
        const btn = next && (next.matches('button, input[type="submit"], input[type="button"], [role="button"]') ? next : next.querySelector && next.querySelector('button, input[type="submit"]'));
        const btnText = btn ? (text(btn) || btn.getAttribute('value') || btn.getAttribute('aria-label') || '') : '';
        if (btnText) add('adjacent-button-as-label', 'G167', input, `Unlabelled field is followed by the "${btnText.slice(0, 30)}" button which visually labels it — add aria-label/placeholder-independent label so the name is programmatic too (G167)`);
      }

      // ── G89: format hints for constrained inputs ────────────────────────
      const constrained = input.hasAttribute('pattern') || ['date', 'datetime-local', 'time', 'month', 'week', 'tel'].includes(type)
        || (type === 'text' && (input.hasAttribute('maxlength') && parseInt(input.getAttribute('maxlength'), 10) <= 12 && /code|zip|postal|郵便|番号|id/i.test(name + ' ' + (input.name || ''))));
      if (constrained && !/^(date|datetime-local|time|month|week)$/.test(type) || (input.hasAttribute('pattern'))) {
        const hintTexts = [name, desc.txt, adjacentText(input)].join(' ');
        const placeholder = input.getAttribute('placeholder') || '';
        if (FORMAT_WORD.test(hintTexts)) { /* visible hint present */ }
        else if (FORMAT_WORD.test(placeholder) || placeholder) add('format-hint-placeholder-only', 'G89', input, `Expected format for this field is shown only as placeholder "${placeholder.slice(0, 30)}", which disappears while typing — repeat it in the label or aria-describedby text (G89)`);
        else add('format-hint-missing', 'G89', input, `Field has an input format constraint (${input.hasAttribute('pattern') ? 'pattern' : type}) but no visible format instruction (G89)`);
      }
      if (out.issues.length > 120) break;
    }

    // ── G184: form-level instructions ───────────────────────────────────────
    try {
      for (const form of document.querySelectorAll('form')) {
        if (hidden(form)) continue;
        out.counts.forms++;
        const req = form.querySelectorAll('[required], [aria-required="true"]').length;
        if (req < 3) continue;
        const first = form.querySelector('input:not([type="hidden"]), select, textarea');
        if (!first) continue;
        // Text before the first field, inside the form or immediately preceding it
        let before = '';
        const walker = document.createTreeWalker(form, NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walker.nextNode())) {
          if (first.compareDocumentPosition(node) & Node.DOCUMENT_POSITION_PRECEDING) before += ' ' + node.textContent; else break;
        }
        const prev = form.previousElementSibling;
        if (prev) before += ' ' + text(prev);
        before = before.replace(/\s+/g, ' ').trim();
        if (!REQ_WORD.test(before)) add('form-no-instructions', 'G184', form, `Form has ${req} required fields but no instructions before the first field explaining required fields or formats (G184)`);
      }
    } catch (_) { /* ignore */ }

    return out;
  });

  const data = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : { issues: [], counts: {} };
  const issues = Array.isArray(data.issues) ? data.issues : [];
  const c = data.counts || {};

  if (!c.inputs) {
    return { successCriteriaId: SC, rules: [_rule(RULE_ID, 'not_applicable', null, _t(ctx, 'No form fields on the page.', 'ページにフォームフィールドはありません。'))] };
  }
  if (!issues.length) {
    return {
      successCriteriaId: SC,
      rules: [_rule(RULE_ID, 'pass', null, _t(ctx,
        '{n} field(s) checked: labels are conventionally placed, required fields carry a visible cue ({req}), labels match input types, format hints are visible and aria-describedby references resolve ({desc}).',
        '{n} 件のフィールドを確認: ラベル位置は慣例どおり、必須フィールドには視覚的な表示があり（{req} 件）、ラベルは入力種別と一致し、形式のヒントは可視で、aria-describedby の参照は解決します（{desc} 件）。',
        { n: c.inputs, req: c.requiredWithCue || 0, desc: c.describedBy || 0 }))],
    };
  }
  const fails = issues.filter(i => i.severity === 'fail');
  const reviews = issues.filter(i => i.severity !== 'fail');
  const summarize = (list) => [...new Set(list.map(i => `${i.technique}:${i.type}`))].join(', ');
  const rules = [];
  if (fails.length) rules.push(_rule(RULE_ID, 'fail', 'serious', _t(ctx, '{n} label/instruction failure(s): {types}.', '{n} 件のラベル/説明の不備: {types}。', { n: fails.length, types: summarize(fails) }), fails));
  if (reviews.length) rules.push(_rule(`${RULE_ID}-review`, 'incomplete', 'moderate', _t(ctx,
    '{n} field(s) need review for labels or instructions: {types}. Required cues, format hints and label placement should be visible and associated with the field.',
    '{n} 件のフィールドでラベル/説明の確認が必要です: {types}。必須の表示、形式のヒント、ラベル位置は可視でフィールドに関連付けられている必要があります。',
    { n: reviews.length, types: summarize(reviews) }), reviews));
  return { successCriteriaId: SC, rules };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
