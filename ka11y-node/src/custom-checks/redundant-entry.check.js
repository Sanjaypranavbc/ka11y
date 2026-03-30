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

// ─── FIX #7: cap summarizeGroups output but also return full structured data ───
function summarizeGroups(groups) {
  return groups.slice(0, 3).map((group) => {
    const selectors = (group.sampleSelectors || []).slice(0, 2).join(', ');
    return `${group.key} (${group.requiredCount} required field(s)${selectors ? `: ${selectors}` : ''})`;
  }).join('; ');
}

// ─── FIX #8: collect inputs from all frames (called from run()) ───
async function collectFrameData(frame, tokens, confirmSrc, reuseSrc, keywordPairs) {
  try {
    return await frame.evaluate(evaluatePage, tokens, confirmSrc, reuseSrc, keywordPairs);
  } catch {
    // If a cross-origin frame blocks evaluation, skip it gracefully
    return null;
  }
}

// ─── Core page evaluator — extracted so it can be called per-frame ───
function evaluatePage(tokens, confirmSrc, reuseSrc, keywordPairs) {
  const personalTokenSet = new Set(tokens);
  const confirmRe = new RegExp(confirmSrc, 'i');
  const reuseRe = new RegExp(reuseSrc, 'i');
  const keywordMap = keywordPairs.map(([src, key]) => [new RegExp(src, 'i'), key]);

  // ─── FIX #4: Shadow DOM traversal ───
  function collectAllInputs(root) {
    const inputs = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
    let node = walker.currentNode;
    while (node) {
      const tag = node.tagName ? node.tagName.toLowerCase() : '';
      if (tag === 'input' || tag === 'select' || tag === 'textarea') {
        inputs.push(node);
      }
      // Pierce shadow roots
      if (node.shadowRoot) {
        inputs.push(...collectAllInputs(node.shadowRoot));
      }
      node = walker.nextNode();
    }
    return inputs;
  }

  // ─── FIX #6: stable form fingerprint instead of fragile DOM index ───
  function stableFormId(form, idx) {
    const names = Array.from(form.querySelectorAll('[name]'))
      .map((el) => el.getAttribute('name'))
      .filter(Boolean)
      .sort()
      .slice(0, 6)
      .join('|');
    if (names) return `form:fp:${names}`;
    const id = (form.id || '').trim();
    if (id) return `form:id:${id}`;
    const formName = (form.getAttribute('name') || '').trim();
    if (formName) return `form:name:${formName}`;
    return `form:idx:${idx}`;
  }

  const forms = Array.from(document.querySelectorAll('form'));
  const formStableIdMap = new Map(forms.map((form, idx) => [form, stableFormId(form, idx)]));

  // ─── FIX #3: scope reuse controls per-form, not globally ───
  function getFormReuseControls(form) {
    if (!form) return [];
    const candidates = Array.from(form.querySelectorAll(
      'input[type="checkbox"], input[type="radio"], button, a, label, option, summary, [role="button"], [role="link"]'
    ));
    return candidates.filter((el) => {
      const text = [
        el.textContent || '',
        el.getAttribute('aria-label') || '',
        el.getAttribute('value') || '',
      ].join(' ');
      return reuseRe.test(text);
    });
  }

  // Also retain a global reuse count for fields not inside any form
  const globalReuseControls = Array.from(document.querySelectorAll(
    'input[type="checkbox"], input[type="radio"], button, a, label, option, summary, [role="button"], [role="link"]'
  )).filter((el) => {
    const text = [
      el.textContent || '',
      el.getAttribute('aria-label') || '',
      el.getAttribute('value') || '',
    ].join(' ');
    return reuseRe.test(text);
  });
  const globalReuseControlCount = globalReuseControls.length;

  // Cache reuse controls per form to avoid repeated DOM queries
  const formReuseCache = new Map();
  for (const form of forms) {
    formReuseCache.set(form, getFormReuseControls(form));
  }

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

  // ─── FIX #7: cap context string length to avoid slow regex on long text ───
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

    // FIX #7: cap to 500 chars to prevent slow regex on huge label blobs
    return parts.join(' ').replace(/\s+/g, ' ').trim().toLowerCase().slice(0, 500);
  }

  // ─── FIX #2: robust field inference — semantic type first, then autocomplete, then keywords ───
  function inferKey(el, context) {
    // 1. Strongest signal: explicit autocomplete attribute
    const fromAutocomplete = normalizeAutocomplete(el);
    if (fromAutocomplete) return { key: fromAutocomplete, hasAutocomplete: true };

    // 2. Semantic HTML input types (type="email", type="tel") — reliable without autocomplete
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (type === 'email') return { key: 'email', hasAutocomplete: false };
    if (type === 'tel') return { key: 'tel', hasAutocomplete: false };

    // 3. Keyword heuristics on context text (name, id, placeholder, label)
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
  // FIX #4: use shadow-piercing collector instead of plain querySelectorAll
  const inputs = collectAllInputs(document);

  for (const el of inputs) {
    const tag = el.tagName ? el.tagName.toLowerCase() : '';
    if (!['input', 'select', 'textarea'].includes(tag)) continue;

    const type = (el.getAttribute('type') || '').toLowerCase();

    if (tag === 'input' && ['hidden', 'submit', 'button', 'reset', 'image', 'file', 'color', 'range'].includes(type)) {
      continue;
    }
    if (el.closest('[hidden], [aria-hidden="true"]')) continue;

    const context = contextText(el);
    const { key, hasAutocomplete } = inferKey(el, context);
    if (!key) continue;

    const form = el.closest('form');

    // FIX #6: use stable form fingerprint
    const formRef = form
      ? formStableIdMap.get(form) || `form:unknown`
      : 'form:none';

    // FIX #3: per-form reuse check instead of global
    const formSpecificReuseCount = form
      ? (formReuseCache.get(form) || []).length
      : 0;

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
      // FIX #3: scoped to the field's own form, not global
      formHasReuse: formSpecificReuseCount > 0,
      formSpecificReuseCount,
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

    // FIX #3: reuse mechanism is now true only if the field's own form has reuse controls,
    // or (for orphan fields) if there are global reuse controls
    const hasReuseMechanism = nonConfirm.some((f) =>
      f.formRef === 'form:none'
        ? globalReuseControlCount > 0   // orphan field: fall back to global
        : f.formHasReuse                // form-bound field: scoped check only
    );

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
      // FIX #9: retain full selector list (not just 3) for machine-readable output
      allSelectors: nonConfirm.map((f) => f.selector),
      sampleSelectors: nonConfirm.slice(0, 3).map((f) => f.selector),
    });
  }

  return {
    formCount: forms.length,
    candidateCount: candidates.length,
    globalReuseControlCount,
    repeatedGroups,
    highConfidenceGroups: repeatedGroups.filter((g) => g.highConfidence),
    reviewGroups: repeatedGroups.filter((g) => g.needsReview),
  };
}

async function run(page) {
  // ─── FIX #5: wait for dynamic/lazy-rendered fields before evaluating ───
  await page.waitForNetworkIdle({ timeout: 3000 }).catch(() => {});
  await page.waitForSelector('input, select, textarea', { timeout: 5000 }).catch(() => {});

  // Evaluate the main frame
  const mainData = await page.evaluate(
    evaluatePage,
    PERSONAL_AUTOCOMPLETE_TOKENS,
    CONFIRM_RE.source,
    REUSE_CONTROL_RE.source,
    PERSONAL_KEYWORDS.map(([re, key]) => [re.source, key])
  );

  // ─── FIX #8: also evaluate all child frames (iframes) ───
  const frames = page.frames().filter((f) => f !== page.mainFrame());
  const frameResults = await Promise.all(
    frames.map((frame) =>
      frame.evaluate(
        evaluatePage,
        PERSONAL_AUTOCOMPLETE_TOKENS,
        CONFIRM_RE.source,
        REUSE_CONTROL_RE.source,
        PERSONAL_KEYWORDS.map(([re, key]) => [re.source, key])
      ).catch(() => null) // skip cross-origin frames silently
    )
  );

  // Merge frame data into main data
  const data = mergeFrameData(mainData, frameResults.filter(Boolean));

  // ─── FIX #9: build full structured debug output alongside human summary ───
  function buildResult(status, impact, reason, extraDebug = {}) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Previously entered information should not be required again in the same process',
        impact,
        status,
        reason,
        helpUrl: HELP_URL,
      }],
      // Machine-readable full data for automated pipelines
      debug: {
        formCount: data.formCount,
        candidateCount: data.candidateCount,
        globalReuseControlCount: data.globalReuseControlCount,
        highConfidenceGroups: data.highConfidenceGroups,
        reviewGroups: data.reviewGroups,
        allRepeatedGroups: data.repeatedGroups,
        frameCount: frames.length,
        ...extraDebug,
      },
    };
  }

  if (data.formCount === 0) {
    return buildResult('pass', null, 'No forms detected on this page.');
  }

  if (data.repeatedGroups.length === 0) {
    return buildResult(
      'pass',
      null,
      `${data.candidateCount} personal-data field(s) checked — no repeated required personal-data fields were detected in a way that suggests redundant re-entry.`
    );
  }

  if (data.highConfidenceGroups.length > 0) {
    const sample = summarizeGroups(data.highConfidenceGroups);
    return buildResult(
      'fail',
      'moderate',
      `${data.highConfidenceGroups.length} high-confidence redundant-entry issue(s) detected: required personal data appears to be entered again with no detectable reuse/prefill mechanism. Examples: ${sample}.`
    );
  }

  if (data.reviewGroups.length > 0) {
    const sample = summarizeGroups(data.reviewGroups);
    return buildResult(
      'incomplete',
      'moderate',
      `${data.reviewGroups.length} repeated required personal-data group(s) detected that need manual verification for SC 3.3.7. Confirm whether previously entered values are auto-populated or selectable in the real process flow. Examples: ${sample}.`
    );
  }

  return buildResult(
    'pass',
    null,
    `${data.repeatedGroups.length} repeated personal-data group(s) detected, and reuse or prefill mechanisms were also detected.`
  );
}

// ─── Merge results from multiple frames into one unified data object ───
function mergeFrameData(main, frameDataList) {
  const merged = { ...main };

  for (const frame of frameDataList) {
    merged.formCount += frame.formCount;
    merged.candidateCount += frame.candidateCount;
    merged.globalReuseControlCount += frame.globalReuseControlCount;

    // Merge repeatedGroups by key — combine field counts across frames
    for (const fg of frame.repeatedGroups) {
      const existing = merged.repeatedGroups.find((g) => g.key === fg.key);
      if (existing) {
        existing.fieldCount += fg.fieldCount;
        existing.requiredCount += fg.requiredCount;
        existing.uniqueForms += fg.uniqueForms;
        existing.hasPrefilledRepeat = existing.hasPrefilledRepeat || fg.hasPrefilledRepeat;
        existing.hasAutocompleteSupport = existing.hasAutocompleteSupport && fg.hasAutocompleteSupport;
        existing.hasReuseMechanism = existing.hasReuseMechanism || fg.hasReuseMechanism;
        existing.allSelectors = [...(existing.allSelectors || []), ...(fg.allSelectors || [])];
        existing.sampleSelectors = existing.allSelectors.slice(0, 3);
        // Re-evaluate confidence after merge
        existing.highConfidence = existing.uniqueForms > 1
          && !existing.hasPrefilledRepeat
          && !existing.hasAutocompleteSupport
          && !existing.hasReuseMechanism;
        existing.needsReview = !existing.highConfidence && !existing.hasPrefilledRepeat && !existing.hasReuseMechanism;
      } else {
        merged.repeatedGroups.push({ ...fg });
      }
    }
  }

  // Re-derive filtered lists after merge
  merged.highConfidenceGroups = merged.repeatedGroups.filter((g) => g.highConfidence);
  merged.reviewGroups = merged.repeatedGroups.filter((g) => g.needsReview);

  return merged;
}

module.exports = { run, SC, RULE_ID, HELP_URL };