'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '2.4.6';
const RULE_ID = 'custom-headings-and-labels';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/headings-and-labels';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Headings and labels must describe topic or purpose — empty or non-descriptive labels fail this criterion';

const GENERIC_HEADING_RE = /^(untitled|heading|section|content|page|title|click here|read more|more|here|link)$/i;
const GENERIC_LABEL_RE = /^(field|input|text|value|label|enter|type here|select|option|choose|untitled|\*)$/i;
const MAX_VIOLATIONS = 40;

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
    const generic = new RegExp(opts.genericPattern, 'i');
    const genericLabel = new RegExp(opts.genericLabelPattern, 'i');
    const violations = [];

    // ── 1. Headings: empty text or purely generic ───────────────────────
    for (const el of document.querySelectorAll('h1,h2,h3,h4,h5,h6,[role="heading"]')) {
      const cs = window.getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') continue;

      const text = (el.textContent || '').trim();
      const ariaLabel = (el.getAttribute('aria-label') || '').trim();
      const effective = ariaLabel || text;

      let reason = null;
      if (!effective) {
        reason = 'Heading has no visible text or aria-label — it does not describe the section.';
      } else if (generic.test(effective)) {
        reason = `Heading text "${effective}" is too generic — it does not describe the topic of the section.`;
      }

      // G130: a heading should describe its section — compare heading words with the
      // first ~300 characters of content that follows it (advisory when nothing overlaps).
      if (!reason && effective.length >= 4 && effective.length <= 120) {
        try {
          const toks = (s) => { const t = s.toLowerCase(); const latin = (t.match(/[a-z0-9\u00c0-\u024f]{3,}/g) || []).filter(x => !/^(the|and|for|with|from|your|you|our|are|this|that|about|into)$/.test(x)); const cjk = []; for (const run of (t.match(/[\u3040-\u30ff\u3400-\u9fff]{2,}/g) || [])) for (let i = 0; i + 2 <= run.length; i++) cjk.push(run.slice(i, i + 2)); return new Set([...latin, ...cjk]); };
          let body = '', n = el.nextElementSibling, hops = 0;
          while (n && hops++ < 4 && body.length < 300) { if (/^H[1-6]$/.test(n.tagName)) break; body += ' ' + (n.textContent || ''); n = n.nextElementSibling; }
          if (!body.trim() && el.parentElement && /^(HEADER|HGROUP|DIV|SECTION)$/.test(el.parentElement.tagName)) { let m = el.parentElement.nextElementSibling; while (m && hops++ < 6 && body.length < 300) { body += ' ' + (m.textContent || ''); m = m.nextElementSibling; } }
          body = body.replace(/\s+/g, ' ').trim().slice(0, 400);
          if (body.length >= 120) {
            const h = toks(effective), b = toks(body);
            let overlap = 0; for (const t of h) if (b.has(t)) overlap++;
            if (h.size >= 2 && overlap === 0) {
              violations.push({ type: 'heading-unrelated', target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''), snippet: el.outerHTML.slice(0, 120), detail: `Heading "${effective.slice(0, 50)}" shares no words with the content that follows it — verify it describes the section (G130).` });
            }
          }
        } catch (_) { /* ignore */ }
      }

      if (reason) {
        violations.push({
          type: 'heading',
          target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
          snippet: el.outerHTML.slice(0, 120),
          detail: reason,
        });
        if (violations.length >= opts.max) return { violations, headingCount: 0, labelCount: 0, done: true };
      }
    }

    // ── 2. <label> elements: empty / no matching control ─────────────────
    const allLabels = Array.from(document.querySelectorAll('label'));
    for (const label of allLabels) {
      const cs = window.getComputedStyle(label);
      if (cs.display === 'none' || cs.visibility === 'hidden') continue;

      const text = (label.textContent || '').trim();
      const ariaLabel = (label.getAttribute('aria-label') || '').trim();
      const effective = ariaLabel || text;

      if (!effective) {
        violations.push({
          type: 'label',
          target: 'label' + (label.htmlFor ? `[for="${label.htmlFor}"]` : ''),
          snippet: label.outerHTML.slice(0, 120),
          detail: 'Label element has no visible text — the associated control will have no accessible name.',
        });
        if (violations.length >= opts.max) return { violations, headingCount: 0, labelCount: allLabels.length, done: true };
      } else if (genericLabel.test(effective)) {
        violations.push({
          type: 'label',
          target: 'label' + (label.htmlFor ? `[for="${label.htmlFor}"]` : ''),
          snippet: label.outerHTML.slice(0, 120),
          detail: `Label text "${effective}" is too generic — it does not describe the purpose of the control (G131).`,
        });
        if (violations.length >= opts.max) return { violations, headingCount: 0, labelCount: allLabels.length, done: true };
      }
    }

    // ── 3. Inputs missing accessible name ────────────────────────────────
    const INPUT_SEL = 'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="reset"]):not([type="image"]), select, textarea';
    for (const el of document.querySelectorAll(INPUT_SEL)) {
      const cs = window.getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') continue;
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) continue;

      const id = el.id;
      const ariaLabel = (el.getAttribute('aria-label') || '').trim();
      const ariaLabelledBy = el.getAttribute('aria-labelledby');
      const labelEl = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : null;
      const labelText = labelEl ? (labelEl.textContent || '').trim() : '';
      const title = (el.getAttribute('title') || '').trim();
      const placeholder = (el.getAttribute('placeholder') || '').trim();

      const hasName = ariaLabel || ariaLabelledBy || labelText || title || placeholder;
      if (!hasName) {
        violations.push({
          type: 'input-no-label',
          target: el.tagName.toLowerCase() + (id ? `#${CSS.escape(id)}` : '') + (el.type ? `[type="${el.type}"]` : ''),
          snippet: el.outerHTML.slice(0, 120),
          detail: 'Form control has no associated label, aria-label, or title — screen readers cannot announce its purpose.',
        });
        if (violations.length >= opts.max) break;
      }
    }

    const headingCount = document.querySelectorAll('h1,h2,h3,h4,h5,h6,[role="heading"]').length;
    const labelCount   = allLabels.length;
    return { violations, headingCount, labelCount };
  }, { genericPattern: GENERIC_HEADING_RE.source, genericLabelPattern: GENERIC_LABEL_RE.source, max: MAX_VIOLATIONS });

  const totalElements = data.headingCount + data.labelCount;

  if (totalElements === 0) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'not_applicable', reason: 'No headings or form labels found on this page.', helpUrl: HELP_URL }],
    };
  }

  if (!data.violations.length) {
    return _pass(ctx, _t(ctx,
      '{h} heading(s) and {l} label(s) checked — all have descriptive text.',
      '{h} 件の見出しと {l} 件のラベルを確認しました。すべて説明的なテキストを持っています。',
      { h: data.headingCount, l: data.labelCount }));
  }

  const unrelated = data.violations.filter(v => v.type === 'heading-unrelated');
  const hard = data.violations.filter(v => v.type !== 'heading-unrelated');
  if (!hard.length) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: `${RULE_ID}-relevance`, description: FALLBACK_DESCRIPTION, impact: 'minor', status: 'incomplete',
        reason: _t(ctx, '{n} heading(s) share no words with the content that follows them — verify each heading describes its section (G130).', '{n} 件の見出しが直後のコンテンツと共通する語を持ちません。各見出しがセクションを説明しているか確認してください（G130）。', { n: unrelated.length }),
        elements: unrelated, helpUrl: HELP_URL }],
    };
  }
  data.violations = hard;
  const emptyCount   = data.violations.filter(v => v.detail.includes('no visible text')).length;
  const genericCount = data.violations.filter(v => v.detail.includes('generic')).length;
  const missingCount = data.violations.filter(v => v.type === 'input-no-label').length;

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'moderate',
      status: 'fail',
      reason: _t(ctx,
        '{n} issue(s) found: {e} empty, {g} generic, {m} unlabelled inputs.',
        '{n} 件の問題が見つかりました: {e} 件が空、{g} 件が汎用的、{m} 件のラベルなし入力。',
        { n: data.violations.length, e: emptyCount, g: genericCount, m: missingCount }),
      elements: data.violations,
      helpUrl: HELP_URL,
    }].concat(unrelated.length ? [{ ruleId: `${RULE_ID}-relevance`, description: FALLBACK_DESCRIPTION, impact: 'minor', status: 'incomplete',
      reason: _t(ctx, '{n} heading(s) share no words with the content that follows them — verify each heading describes its section (G130).', '{n} 件の見出しが直後のコンテンツと共通する語を持ちません。各見出しがセクションを説明しているか確認してください（G130）。', { n: unrelated.length }),
      elements: unrelated, helpUrl: HELP_URL }] : []),
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
