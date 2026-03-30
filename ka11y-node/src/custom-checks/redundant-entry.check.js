'use strict';

const SC = '3.3.7';
const RULE_ID = 'custom-redundant-entry';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/redundant-entry';

const PERSONAL_AUTOCOMPLETE_TOKENS = [
  'name',
  'honorific-prefix',
  'given-name',
  'additional-name',
  'family-name',
  'honorific-suffix',
  'nickname',
  'username',
  'new-password',
  'current-password',
  'organization-title',
  'organization',
  'street-address',
  'address-line1',
  'address-line2',
  'address-line3',
  'address-level1',
  'address-level2',
  'address-level3',
  'address-level4',
  'country',
  'country-name',
  'postal-code',
  'cc-name',
  'email',
  'tel',
];

// Treat confirmation fields as lower-confidence signals to avoid obvious false positives.
const CONFIRM_RE = /\b(confirm|re-?enter|again|verify|verification|repeat)\b|確認|再入力|もう一度|再度|確認用/i;
const REUSE_CONTROL_RE = /\b(same\s+as|use\s+same|copy\s+from|copy\s+address|use\s+shipping|billing\s+same|autofill|prefill|load\s+saved|from\s+profile|use\s+previous|same\s+details)\b|前と同じ|同じ住所|同上|コピー|自動入力|保存済み|プロフィール/i;

const PERSONAL_KEYWORDS = [
  [/\b(e-?mail|email)\b|メール/, 'email'],
  [/\b(phone|tel|telephone|mobile|contact\s*number)\b|電話|携帯|連絡先/, 'tel'],
  [/\b(first\s*name|given\s*name|forename)\b|名(?!称)/, 'given-name'],
  [/\b(last\s*name|family\s*name|surname)\b|姓/, 'family-name'],
  [/\b(full\s*name|name)\b|氏名|お名前|名前/, 'name'],
  [/\b(address\s*line\s*1|street\s*address|address1)\b|住所|番地/, 'address-line1'],
  [/\b(address\s*line\s*2|address2|apartment|suite|unit)\b|建物|部屋/, 'address-line2'],
  [/\b(city|town)\b|市|区|町|村/, 'address-level2'],
  [/\b(state|province|prefecture|region)\b|都道府県/, 'address-level1'],
  [/\b(zip|postal|postcode)\b|郵便番号/, 'postal-code'],
  [/\b(country)\b|国/, 'country'],
  [/\b(company|organization|organisation)\b|会社|法人/, 'organization'],
];

function summarizeGroups(groups) {
  return groups.slice(0, 3).map((group) => {
    const selectors = (group.sampleSelectors || []).slice(0, 2).join(', ');
    return `${group.key} (${group.requiredCount} required field(s)${selectors ? `: ${selectors}` : ''})`;
  }).join('; ');
}

async function run(page) {
  const data = await page.evaluate((tokens, confirmSrc, reuseSrc, keywordPairs) => {
    const personalTokenSet = new Set(tokens);
    const confirmRe = new RegExp(confirmSrc, 'i');
    const reuseRe = new RegExp(reuseSrc, 'i');
    const keywordMap = keywordPairs.map(([src, key]) => [new RegExp(src, 'i'), key]);

    const forms = Array.from(document.querySelectorAll('form'));
    const formIndexMap = new Map(forms.map((form, idx) => [form, idx]));

    const formReuseMap = new Map();
    for (const form of forms) {
      const text = [
        form.getAttribute('aria-label') || '',
        form.getAttribute('name') || '',
        form.textContent || '',
      ].join(' ').slice(0, 6000);
      formReuseMap.set(form, reuseRe.test(text));
    }

    const reuseControls = Array.from(document.querySelectorAll(
      'input[type="checkbox"], input[type="radio"], button, a, label, option, summary, [role="button"], [role="link"]'
    ));
    const reuseControlCount = reuseControls.filter((el) => {
      const text = [
        el.textContent || '',
        el.getAttribute('aria-label') || '',
        el.getAttribute('value') || '',
      ].join(' ');
      return reuseRe.test(text);
    }).length;

    function normalizeAutocomplete(el) {
      const raw = (el.getAttribute('autocomplete') || '').trim().toLowerCase();
      if (!raw || raw === 'on' || raw === 'off') return null;

      const parts = raw.split(/\s+/).filter(Boolean).filter((token) =>
        !token.startsWith('section-')
        && !['shipping', 'billing', 'home', 'work', 'mobile', 'fax', 'pager'].includes(token)
      );

      for (const token of parts) {
        if (personalTokenSet.has(token)) return token;
      }
      return null;
    }

    function safeLabelFor(id) {
      if (!id) return null;
      try {
        const escaped = typeof CSS !== 'undefined' && CSS.escape
          ? CSS.escape(id)
          : id.replace(/([ #;.?+*~\':"!^$[\]()=>|\/@])/g, '\\$1');
        return document.querySelector(`label[for="${escaped}"]`);
      } catch {
        return null;
      }
    }

    function contextText(el) {
      const parts = [
        el.getAttribute('name') || '',
        el.getAttribute('id') || '',
        el.getAttribute('placeholder') || '',
        el.getAttribute('aria-label') || '',
        el.getAttribute('autocomplete') || '',
      ];

      if (el.labels && el.labels.length) {
        parts.push(Array.from(el.labels).map((l) => l.textContent || '').join(' '));
      }

      const explicit = safeLabelFor(el.id || '');
      if (explicit) parts.push(explicit.textContent || '');

      return parts.join(' ').replace(/\s+/g, ' ').trim().toLowerCase();
    }

    function inferKey(el, context) {
      const fromAutocomplete = normalizeAutocomplete(el);
      if (fromAutocomplete) return { key: fromAutocomplete, hasAutocomplete: true };

      for (const [re, key] of keywordMap) {
        if (re.test(context)) return { key, hasAutocomplete: false };
      }

      return { key: null, hasAutocomplete: false };
    }

    function selectorHint(el) {
      const tag = el.tagName.toLowerCase();
      if (el.id) return `${tag}#${el.id}`;
      const name = (el.getAttribute('name') || '').trim().replace(/"/g, '\'');
      if (name) return `${tag}[name="${name.slice(0, 48)}"]`;
      return tag;
    }

    const candidates = [];
    const inputs = Array.from(document.querySelectorAll('input, select, textarea'));
    for (const el of inputs) {
      const tag = el.tagName.toLowerCase();
      const type = (el.getAttribute('type') || '').toLowerCase();

      if (tag === 'input' && ['hidden', 'submit', 'button', 'reset', 'image', 'file', 'color', 'range'].includes(type)) {
        continue;
      }
      if (el.closest('[hidden], [aria-hidden="true"]')) continue;

      const context = contextText(el);
      const { key, hasAutocomplete } = inferKey(el, context);
      if (!key) continue;

      const form = el.closest('form');
      const formRef = form
        ? `form:${form.id || form.getAttribute('name') || formIndexMap.get(form)}`
        : 'form:none';

      candidates.push({
        key,
        formRef,
        required: !!(
          el.required
          || String(el.getAttribute('aria-required') || '').toLowerCase() === 'true'
        ),
        prefilled: String(el.value || '').trim().length > 0,
        readOnly: !!el.readOnly,
        disabled: !!el.disabled,
        hasAutocomplete,
        isConfirmField: confirmRe.test(context),
        formHasReuse: !!(form && formReuseMap.get(form)),
        selector: selectorHint(el),
      });
    }

    const grouped = new Map();
    for (const field of candidates) {
      if (!grouped.has(field.key)) grouped.set(field.key, []);
      grouped.get(field.key).push(field);
    }

    const repeatedGroups = [];

    for (const [key, fields] of grouped.entries()) {
      const nonConfirm = fields.filter((f) => !f.isConfirmField);
      if (nonConfirm.length < 2) continue;

      const requiredCount = nonConfirm.filter((f) => f.required && !f.readOnly && !f.disabled).length;
      if (requiredCount < 2) continue;

      const uniqueForms = new Set(nonConfirm.map((f) => f.formRef)).size;
      const hasPrefilledRepeat = nonConfirm.slice(1).some((f) => f.prefilled || f.readOnly || f.disabled);
      const hasAutocompleteSupport = nonConfirm.every((f) => f.hasAutocomplete);
      const hasReuseMechanism = reuseControlCount > 0 || nonConfirm.some((f) => f.formHasReuse);

      const highConfidence = uniqueForms > 1
        && !hasPrefilledRepeat
        && !hasAutocompleteSupport
        && !hasReuseMechanism;

      const clearlyMitigated = hasPrefilledRepeat || hasReuseMechanism;
      const needsReview = !highConfidence && !clearlyMitigated;

      repeatedGroups.push({
        key,
        fieldCount: nonConfirm.length,
        requiredCount,
        uniqueForms,
        hasPrefilledRepeat,
        hasAutocompleteSupport,
        hasReuseMechanism,
        highConfidence,
        needsReview,
        sampleSelectors: nonConfirm.slice(0, 3).map((f) => f.selector),
      });
    }

    return {
      formCount: forms.length,
      candidateCount: candidates.length,
      reuseControlCount,
      repeatedGroups,
      highConfidenceGroups: repeatedGroups.filter((g) => g.highConfidence),
      reviewGroups: repeatedGroups.filter((g) => g.needsReview),
    };
  }, PERSONAL_AUTOCOMPLETE_TOKENS, CONFIRM_RE.source, REUSE_CONTROL_RE.source, PERSONAL_KEYWORDS.map(([re, key]) => [re.source, key]));

  if (data.formCount === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Previously entered information should not be required again in the same process',
        impact: null,
        status: 'pass',
        reason: 'No forms detected on this page.',
        helpUrl: HELP_URL,
      }],
    };
  }

  if (data.repeatedGroups.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Previously entered information should not be required again in the same process',
        impact: null,
        status: 'pass',
        reason: `${data.candidateCount} personal-data field(s) checked — no repeated required personal-data fields were detected in a way that suggests redundant re-entry.`,
        helpUrl: HELP_URL,
      }],
    };
  }

  if (data.highConfidenceGroups.length > 0) {
    const sample = summarizeGroups(data.highConfidenceGroups);
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Previously entered information should not be required again in the same process',
        impact: 'moderate',
        status: 'fail',
        reason: `${data.highConfidenceGroups.length} high-confidence redundant-entry issue(s) detected: required personal data appears to be entered again with no detectable reuse/prefill mechanism. Examples: ${sample}.`,
        helpUrl: HELP_URL,
      }],
    };
  }

  if (data.reviewGroups.length > 0) {
    const sample = summarizeGroups(data.reviewGroups);
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Previously entered information should not be required again in the same process',
        impact: 'moderate',
        status: 'incomplete',
        reason: `${data.reviewGroups.length} repeated required personal-data group(s) detected that need manual verification for SC 3.3.7. Confirm whether previously entered values are auto-populated or selectable in the real process flow. Examples: ${sample}.`,
        helpUrl: HELP_URL,
      }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Previously entered information should not be required again in the same process',
      impact: null,
      status: 'pass',
      reason: `${data.repeatedGroups.length} repeated personal-data group(s) detected, and reuse or prefill mechanisms were also detected.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
