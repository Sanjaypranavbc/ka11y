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
  'honific-suffix',
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

const CONFIRM_RE = /\b(confirm|re-?enter|again|verify|verification|repeat|repeat\s+email|confirm\s+email|confirm\s+phone|retype)\b|確認|再入力|もう一度|再度|確認用/i;

const REUSE_CONTROL_RE = /\b(same\s+as|use\s+same|copy\s+from|copy\s+address|use\s+shipping|use\s+billing|billing\s+same|shipping\s+same|autofill|prefill|load\s+saved|from\s+profile|use\s+previous|same\s+details|same\s+information|copy\s+billing|copy\s+shipping|saved\s+address|saved\s+details|use\s+account|use\s+my\s+profile)\b|前と同じ|同じ住所|同上|コピー|自動入力|保存済み|プロフィール/i;

const PROCESS_HINT_RE = /\b(checkout|payment|billing|shipping|delivery|register|registration|signup|sign[\s-]?up|create\s+account|profile|account|application|apply|booking|reservation|purchase|order|quote|enquiry|inquiry|contact|subscribe|newsletter|support|feedback|survey)\b|申込|申し込み|登録|購入|注文|配送|請求|支払い|予約|問い合わせ/i;

const SECTION_NAME_RE = /\b(billing|shipping|delivery|contact|profile|account|newsletter|subscribe|support|quote|checkout|payment|registration|signup|application|order|booking)\b|請求|配送|連絡先|プロフィール|登録|注文|問い合わせ/i;

const EXPLICIT_DISTINCT_PURPOSE_RE = /\b(newsletter|subscribe|marketing|promotions?|quote|support|feedback|survey|job\s+application|careers?)\b|ニュースレター|購読|見積|サポート|フィードバック|応募/i;

const PERSONAL_KEYWORDS = [
  [/\b(e-?mail|email|mail\s+address)\b|メール/, 'email'],
  [/\b(phone|tel|telephone|mobile|contact\s*number|cell)\b|電話|携帯|連絡先/, 'tel'],
  [/\b(first\s*name|given\s*name|forename)\b|名(?!称)/, 'given-name'],
  [/\b(last\s*name|family\s*name|surname)\b|姓/, 'family-name'],
  [/\b(full\s*name|customer\s*name|your\s*name|name)\b|氏名|お名前|名前/, 'name'],
  [/\b(address\s*line\s*1|street\s*address|address1|address\s*1)\b|住所|番地/, 'address-line1'],
  [/\b(address\s*line\s*2|address2|address\s*2|apartment|suite|unit)\b|建物|部屋/, 'address-line2'],
  [/\b(city|town|locality)\b|市|区|町|村/, 'address-level2'],
  [/\b(state|province|prefecture|region)\b|都道府県/, 'address-level1'],
  [/\b(zip|postal|postcode|post\s*code)\b|郵便番号/, 'postal-code'],
  [/\b(country)\b|国/, 'country'],
  [/\b(company|organization|organisation|business)\b|会社|法人/, 'organization'],
];

function summarizeGroups(groups) {
  return groups.slice(0, 3).map((group) => {
    const selectors = (group.sampleSelectors || []).slice(0, 2).join(', ');
    return `${group.key} (${group.requiredCount} required field(s)${selectors ? `: ${selectors}` : ''})`;
  }).join('; ');
}

function tokenizeText(text) {
  return String(text || '')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s_-]+/gu, ' ')
    .split(/\s+/)
    .filter(Boolean);
}

function unique(arr) {
  return Array.from(new Set(arr));
}

function intersectCount(a, b) {
  const setB = new Set(b);
  let count = 0;
  for (const v of a) {
    if (setB.has(v)) count++;
  }
  return count;
}

function jaccardSimilarity(a, b) {
  const ua = unique(a);
  const ub = unique(b);
  if (!ua.length && !ub.length) return 1;
  const intersection = intersectCount(ua, ub);
  const union = new Set([...ua, ...ub]).size || 1;
  return intersection / union;
}

function mergeTextParts(parts, max = 1200) {
  return parts
    .filter(Boolean)
    .join(' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, max);
}

function clampString(s, max = 500) {
  return String(s || '').replace(/\s+/g, ' ').trim().slice(0, max);
}

function _selectorToElement(selector) {
  const sel = clampString(selector, 200);
  if (!sel) return null;

  const tagMatch = sel.match(/^([a-z][\w-]*)/i);
  const tag = tagMatch ? tagMatch[1].toLowerCase() : null;

  const idMatch = sel.match(/#([a-zA-Z][\w:-]*)/);
  const id = idMatch ? idMatch[1] : null;

  const nameMatch = sel.match(/\[name=(?:"([^"]+)"|'([^']+)'|([^\]]+))\]/i);
  const name = nameMatch ? (nameMatch[1] || nameMatch[2] || nameMatch[3]) : null;

  const ariaLabelMatch = sel.match(/\[aria-label=(?:"([^"]+)"|'([^']+)'|([^\]]+))\]/i);
  const ariaLabel = ariaLabelMatch
    ? (ariaLabelMatch[1] || ariaLabelMatch[2] || ariaLabelMatch[3])
    : null;

  const attrs = [];
  if (id) attrs.push(`id="${id}"`);
  if (name) attrs.push(`name="${name}"`);
  if (ariaLabel) attrs.push(`aria-label="${ariaLabel}"`);

  const html = tag
    ? `<${tag}${attrs.length ? ` ${attrs.join(' ')}` : ''}>`
    : sel;

  return {
    selector: sel,
    tagName: tag ? tag.toUpperCase() : null,
    id,
    html: clampString(html, 200),
  };
}

function _elementsFromGroups(groups, max = 8) {
  const out = [];
  const seen = new Set();

  for (const group of (groups || [])) {
    const selectors = [
      ...((group && group.sampleSelectors) || []),
      ...((group && group.allSelectors) || []),
    ];
    for (const selector of selectors) {
      const element = _selectorToElement(selector);
      if (!element) continue;
      const dedupeKey = `${element.selector}|${element.tagName || ''}|${element.id || ''}`;
      if (seen.has(dedupeKey)) continue;
      seen.add(dedupeKey);
      out.push(element);
      if (out.length >= max) return out;
    }
  }

  return out;
}

function evaluatePage(tokens, confirmSrc, reuseSrc, keywordPairs) {
  const personalTokenSet = new Set(tokens);
  const confirmRe = new RegExp(confirmSrc, 'i');
  const reuseRe = new RegExp(reuseSrc, 'i');
  const keywordMap = keywordPairs.map(([src, key]) => [new RegExp(src, 'i'), key]);

  function isActuallyVisible(el) {
    try {
      if (!el || !el.isConnected) return false;
      if (el.closest('[hidden], [inert], template, [aria-hidden="true"]')) return false;

      const style = window.getComputedStyle(el);
      if (!style) return true;
      if (style.display === 'none' || style.visibility === 'hidden') return false;

      const rect = el.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) {
        const offscreen = style.position === 'absolute' || style.position === 'fixed';
        if (!offscreen) return false;
      }
      return true;
    } catch {
      return true;
    }
  }

  function collectAllInputs(root) {
    const inputs = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
    let node = walker.currentNode;
    while (node) {
      const tag = node.tagName ? node.tagName.toLowerCase() : '';
      if ((tag === 'input' || tag === 'select' || tag === 'textarea') && isActuallyVisible(node)) {
        inputs.push(node);
      }
      if (node.shadowRoot) {
        inputs.push(...collectAllInputs(node.shadowRoot));
      }
      node = walker.nextNode();
    }
    return inputs;
  }

  function stableFormId(form, idx) {
    const names = Array.from(form.querySelectorAll('[name]'))
      .map((el) => el.getAttribute('name'))
      .filter(Boolean)
      .sort()
      .slice(0, 8)
      .join('|');
    if (names) return `form:fp:${names}`;
    const id = (form.id || '').trim();
    if (id) return `form:id:${id}`;
    const formName = (form.getAttribute('name') || '').trim();
    if (formName) return `form:name:${formName}`;

    const action = (form.getAttribute('action') || '').trim();
    if (action) return `form:action:${action.slice(0, 80)}`;

    return `form:idx:${idx}`;
  }

  function safeCssEscape(value) {
    try {
      if (typeof CSS !== 'undefined' && CSS.escape) return CSS.escape(value);
    } catch {}
    return String(value).replace(/([ #;.?+*~\':"!^$[\]()=>|/@\\])/g, '\\$1');
  }

  function safeLabelFor(id) {
    if (!id) return null;
    try {
      return document.querySelector(`label[for="${safeCssEscape(id)}"]`);
    } catch {
      return null;
    }
  }

  function nearestText(el, depth = 3) {
    const parts = [];
    let current = el;
    let hops = 0;
    while (current && hops < depth) {
      if (current.parentElement) {
        const parent = current.parentElement;
        const txt = clampString(parent.textContent || '', 250);
        if (txt) parts.push(txt);
        current = parent;
        hops += 1;
      } else {
        break;
      }
    }
    return mergeTextParts(parts, 500);
  }

  function getFormScopeText(form) {
    if (!form) return '';
    const parts = [
      form.getAttribute('id') || '',
      form.getAttribute('name') || '',
      form.getAttribute('action') || '',
      form.getAttribute('aria-label') || '',
      form.getAttribute('aria-labelledby') || '',
      clampString(form.textContent || '', 600),
    ];
    return mergeTextParts(parts, 800).toLowerCase();
  }

  function getSectionScopeText(el) {
    const scope = el.closest('fieldset, section, article, aside, [role="group"], [role="form"], .form, .form-section, .section, .panel, .step, .checkout, .billing, .shipping, .contact, .subscribe');
    if (!scope) return '';
    return mergeTextParts([
      scope.getAttribute('id') || '',
      scope.getAttribute('class') || '',
      scope.getAttribute('aria-label') || '',
      clampString(scope.textContent || '', 600),
    ], 900).toLowerCase();
  }

  function getAutocompleteMeta(el) {
    const raw = (el.getAttribute('autocomplete') || '').trim().toLowerCase();
    if (!raw || raw === 'on' || raw === 'off') {
      return {
        token: null,
        hasAutocomplete: false,
        section: null,
        mode: null,
      };
    }

    const parts = raw.split(/\s+/).filter(Boolean);
    let section = null;
    let mode = null;
    let token = null;

    for (const part of parts) {
      if (part.startsWith('section-')) {
        section = part;
        continue;
      }
      if (['shipping', 'billing', 'home', 'work', 'mobile', 'fax', 'pager'].includes(part)) {
        mode = part;
        continue;
      }
      if (personalTokenSet.has(part)) {
        token = part;
      }
    }

    return {
      token,
      hasAutocomplete: true,
      section,
      mode,
    };
  }

  function contextText(el) {
    const explicit = safeLabelFor(el.id || '');
    const parts = [
      el.getAttribute('name') || '',
      el.getAttribute('id') || '',
      el.getAttribute('placeholder') || '',
      el.getAttribute('aria-label') || '',
      el.getAttribute('autocomplete') || '',
      el.getAttribute('title') || '',
      el.getAttribute('data-testid') || '',
      el.getAttribute('class') || '',
      el.getAttribute('inputmode') || '',
      explicit ? explicit.textContent || '' : '',
      el.labels && el.labels.length ? Array.from(el.labels).map((l) => l.textContent || '').join(' ') : '',
      nearestText(el, 3),
    ];
    return mergeTextParts(parts, 1200).toLowerCase();
  }

  function inferKey(el, context) {
    const autocompleteMeta = getAutocompleteMeta(el);
    if (autocompleteMeta.token) {
      return {
        key: autocompleteMeta.token,
        hasAutocomplete: true,
        autocompleteMeta,
      };
    }

    const tag = (el.tagName || '').toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();

    if (tag === 'input' && type === 'email') {
      return {
        key: 'email',
        hasAutocomplete: autocompleteMeta.hasAutocomplete,
        autocompleteMeta,
      };
    }
    if (tag === 'input' && type === 'tel') {
      return {
        key: 'tel',
        hasAutocomplete: autocompleteMeta.hasAutocomplete,
        autocompleteMeta,
      };
    }

    for (const [re, key] of keywordMap) {
      if (re.test(context)) {
        return {
          key,
          hasAutocomplete: autocompleteMeta.hasAutocomplete,
          autocompleteMeta,
        };
      }
    }

    return {
      key: null,
      hasAutocomplete: autocompleteMeta.hasAutocomplete,
      autocompleteMeta,
    };
  }

  function selectorHint(el) {
    const tag = (el.tagName || 'input').toLowerCase();
    if (el.id) return `${tag}#${el.id}`;
    const name = (el.getAttribute('name') || '').trim().replace(/"/g, '\'');
    if (name) return `${tag}[name="${name.slice(0, 64)}"]`;
    const aria = (el.getAttribute('aria-label') || '').trim().replace(/"/g, '\'');
    if (aria) return `${tag}[aria-label="${aria.slice(0, 64)}"]`;
    return tag;
  }

  function getFormReuseControls(form) {
    if (!form) return [];
    const candidates = Array.from(form.querySelectorAll(
      'input[type="checkbox"], input[type="radio"], button, a, label, option, summary, [role="button"], [role="link"]'
    ));
    return candidates.filter((el) => {
      const text = mergeTextParts([
        el.textContent || '',
        el.getAttribute('aria-label') || '',
        el.getAttribute('value') || '',
        el.getAttribute('title') || '',
      ], 300);
      return reuseRe.test(text);
    });
  }

  function getReuseStateNearField(el, form) {
    const localTexts = [];

    const section = el.closest('fieldset, section, article, aside, [role="group"], [role="form"], .form, .form-section, .section, .panel, .step');
    if (section) {
      localTexts.push(clampString(section.textContent || '', 700));
    }

    if (form) {
      localTexts.push(clampString(form.textContent || '', 1000));
    }

    const localReuse = localTexts.some((txt) => reuseRe.test(txt));
    const formReuseControls = form ? getFormReuseControls(form) : [];
    return {
      formHasReuse: formReuseControls.length > 0 || localReuse,
      formSpecificReuseCount: formReuseControls.length,
    };
  }

  function inferProcessType(form, sectionText, context) {
    const merged = mergeTextParts([
      form ? getFormScopeText(form) : '',
      sectionText || '',
      context || '',
    ], 1200).toLowerCase();

    const matches = [];
    if (/\b(newsletter|subscribe)\b|ニュースレター|購読/i.test(merged)) matches.push('subscribe');
    if (/\b(contact|enquiry|inquiry|quote|support|feedback)\b|問い合わせ|見積|サポート|フィードバック/i.test(merged)) matches.push('contact');
    if (/\b(checkout|payment|billing|shipping|delivery|order|purchase)\b|購入|注文|配送|請求|支払い/i.test(merged)) matches.push('checkout');
    if (/\b(register|registration|signup|sign[\s-]?up|account|profile)\b|登録|アカウント|プロフィール/i.test(merged)) matches.push('account');
    if (/\b(application|apply|careers?|job)\b|応募/i.test(merged)) matches.push('application');
    if (/\b(booking|reservation)\b|予約/i.test(merged)) matches.push('booking');

    return matches[0] || (PROCESS_HINT_RE.test(merged) ? 'generic-process' : 'unknown');
  }

  function inferPurposeSignature(key, context, form, sectionText, autocompleteMeta) {
    const merged = mergeTextParts([
      key,
      context,
      form ? getFormScopeText(form) : '',
      sectionText,
      autocompleteMeta.section || '',
      autocompleteMeta.mode || '',
    ], 1400).toLowerCase();

    const purposeParts = [key];

    if (/\b(newsletter|subscribe)\b|ニュースレター|購読/i.test(merged)) purposeParts.push('subscribe');
    else if (/\b(contact|enquiry|inquiry|support|feedback|quote)\b|問い合わせ|見積|サポート|フィードバック/i.test(merged)) purposeParts.push('contact');
    else if (/\b(checkout|payment|billing|shipping|delivery|order|purchase)\b|購入|注文|配送|請求|支払い/i.test(merged)) purposeParts.push('checkout');
    else if (/\b(register|registration|signup|sign[\s-]?up|account|profile)\b|登録|アカウント|プロフィール/i.test(merged)) purposeParts.push('account');
    else if (/\b(application|careers?|job)\b|応募/i.test(merged)) purposeParts.push('application');
    else if (/\b(booking|reservation)\b|予約/i.test(merged)) purposeParts.push('booking');
    else purposeParts.push('generic');

    if (/\bbilling\b|請求/i.test(merged) || autocompleteMeta.mode === 'billing') purposeParts.push('billing');
    if (/\bshipping|delivery\b|配送/i.test(merged) || autocompleteMeta.mode === 'shipping') purposeParts.push('shipping');

    if (autocompleteMeta.section) purposeParts.push(autocompleteMeta.section);

    return unique(purposeParts).join('|');
  }

  function inferDistinctPurpose(field) {
    const txt = mergeTextParts([
      field.context,
      field.sectionText,
      field.formText,
      field.processType,
      field.purposeSignature,
    ], 1400);

    return EXPLICIT_DISTINCT_PURPOSE_RE.test(txt);
  }

  const forms = Array.from(document.querySelectorAll('form'));
  const formStableIdMap = new Map(forms.map((form, idx) => [form, stableFormId(form, idx)]));

  const globalReuseControls = Array.from(document.querySelectorAll(
    'input[type="checkbox"], input[type="radio"], button, a, label, option, summary, [role="button"], [role="link"]'
  )).filter((el) => {
    const text = mergeTextParts([
      el.textContent || '',
      el.getAttribute('aria-label') || '',
      el.getAttribute('value') || '',
      el.getAttribute('title') || '',
    ], 300);
    return reuseRe.test(text);
  });
  const globalReuseControlCount = globalReuseControls.length;

  const inputs = collectAllInputs(document);
  const candidates = [];

  for (const el of inputs) {
    const tag = (el.tagName || '').toLowerCase();
    if (!['input', 'select', 'textarea'].includes(tag)) continue;

    const type = (el.getAttribute('type') || '').toLowerCase();

    if (tag === 'input' && ['hidden', 'submit', 'button', 'reset', 'image', 'file', 'color', 'range'].includes(type)) {
      continue;
    }

    if (type === 'password') continue;
    if (el.closest('[hidden], [aria-hidden="true"], [inert]')) continue;

    const context = contextText(el);
    const sectionText = getSectionScopeText(el);
    const { key, hasAutocomplete, autocompleteMeta } = inferKey(el, context);
    if (!key) continue;

    const form = el.closest('form');
    const formRef = form ? (formStableIdMap.get(form) || 'form:unknown') : 'form:none';
    const formText = form ? getFormScopeText(form) : '';

    const reuseState = getReuseStateNearField(el, form);
    const processType = inferProcessType(form, sectionText, context);
    const purposeSignature = inferPurposeSignature(key, context, form, sectionText, autocompleteMeta);

    const required = !!(
      el.required ||
      String(el.getAttribute('aria-required') || '').toLowerCase() === 'true'
    );

    const fieldValue = String(el.value || '').trim();
    const prefilled = fieldValue.length > 0;
    const readOnly = !!el.readOnly;
    const disabled = !!el.disabled;
    const isConfirmField = confirmRe.test(context);

    const field = {
      key,
      formRef,
      formText,
      required,
      prefilled,
      readOnly,
      disabled,
      hasAutocomplete,
      autocompleteToken: autocompleteMeta.token,
      autocompleteSection: autocompleteMeta.section,
      autocompleteMode: autocompleteMeta.mode,
      isConfirmField,
      formHasReuse: reuseState.formHasReuse,
      formSpecificReuseCount: reuseState.formSpecificReuseCount,
      selector: selectorHint(el),
      context,
      sectionText,
      processType,
      purposeSignature,
      distinctPurposeHint: false,
    };

    field.distinctPurposeHint = inferDistinctPurpose(field);
    candidates.push(field);
  }

  const grouped = new Map();
  for (const field of candidates) {
    if (!grouped.has(field.key)) grouped.set(field.key, []);
    grouped.get(field.key).push(field);
  }

  function areLikelySamePurpose(fields) {
    if (fields.length < 2) return false;

    const signatures = fields.map((f) => f.purposeSignature).filter(Boolean);
    const signatureCounts = new Map();
    for (const sig of signatures) {
      signatureCounts.set(sig, (signatureCounts.get(sig) || 0) + 1);
    }

    const maxSignatureCount = Math.max(0, ...Array.from(signatureCounts.values()));
    if (maxSignatureCount >= 2) return true;

    const tokenLists = fields.map((f) => tokenizeText(
      mergeTextParts([f.context, f.sectionText, f.formText, f.processType, f.purposeSignature], 1200)
    ));

    let best = 0;
    for (let i = 0; i < tokenLists.length; i++) {
      for (let j = i + 1; j < tokenLists.length; j++) {
        best = Math.max(best, jaccardSimilarity(tokenLists[i], tokenLists[j]));
      }
    }

    return best >= 0.4;
  }

function areClearlyDifferentPurpose(fields) {
    if (fields.length < 2) return false;

    const combinedText = fields.map(f =>
      (f.context + ' ' + f.sectionText + ' ' + f.formText).toLowerCase()
    );

    const hasSubscribe = combinedText.some(t =>
      /newsletter|subscribe|get the fresh news|subscription/i.test(t)
    );

    const hasContact = combinedText.some(t =>
      /contact|enquiry|support|get in touch/i.test(t)
    );

    // 🔥 STRONG override
    if (hasSubscribe && hasContact) return true;

    return false;
}

  function getStrongestPairwiseEvidence(fields) {
    let samePurposePairs = 0;
    let distinctPurposePairs = 0;
    let pairCount = 0;

    for (let i = 0; i < fields.length; i++) {
      for (let j = i + 1; j < fields.length; j++) {
        pairCount++;
        const a = fields[i];
        const b = fields[j];

        const aTokens = tokenizeText(mergeTextParts([a.context, a.sectionText, a.formText, a.processType, a.purposeSignature], 1000));
        const bTokens = tokenizeText(mergeTextParts([b.context, b.sectionText, b.formText, b.processType, b.purposeSignature], 1000));
        const similarity = jaccardSimilarity(aTokens, bTokens);

        const sameSignature = a.purposeSignature && b.purposeSignature && a.purposeSignature === b.purposeSignature;
        const sameProcess = a.processType && b.processType && a.processType === b.processType;
        const differentProcess = a.processType && b.processType && a.processType !== b.processType;

        if (sameSignature || (sameProcess && similarity >= 0.35) || similarity >= 0.5) {
          samePurposePairs++;
        } else if (differentProcess && similarity < 0.25) {
          distinctPurposePairs++;
        }
      }
    }

    return { pairCount, samePurposePairs, distinctPurposePairs };
  }

  const repeatedGroups = [];

  for (const [key, fields] of grouped.entries()) {
    const nonConfirm = fields.filter((f) => !f.isConfirmField);
    if (nonConfirm.length < 2) continue;

    const actionable = nonConfirm.filter((f) => !f.readOnly && !f.disabled);
    const requiredCount = actionable.filter((f) => f.required).length;
    if (requiredCount < 2) continue;

    const uniqueForms = new Set(actionable.map((f) => f.formRef)).size;
    const hasPrefilledRepeat = actionable.slice(1).some((f) => f.prefilled || f.readOnly || f.disabled);

    const hasAutocompleteSupport = actionable.every((f) => {
      if (!f.hasAutocomplete) return false;
      if (f.autocompleteToken !== key) return false;
      return true;
    });

    const hasReuseMechanism = actionable.some((f) =>
      f.formRef === 'form:none'
        ? globalReuseControlCount > 0
        : f.formHasReuse
    );

    const samePurpose = areLikelySamePurpose(actionable);
    const clearlyDifferentPurpose = areClearlyDifferentPurpose(actionable);
    const pairwiseEvidence = getStrongestPairwiseEvidence(actionable);

    const sameProcessLike = unique(actionable.map((f) => f.processType).filter(Boolean)).length <= 1
      || pairwiseEvidence.samePurposePairs > pairwiseEvidence.distinctPurposePairs;

    const highConfidence = (
      actionable.length >= 2 &&
      requiredCount >= 2 &&
      samePurpose &&
      sameProcessLike &&
      !clearlyDifferentPurpose &&
      !hasPrefilledRepeat &&
      !hasReuseMechanism &&
      !hasAutocompleteSupport
    );

    const clearlyMitigated =
      hasPrefilledRepeat ||
      hasReuseMechanism ||
      (hasAutocompleteSupport && samePurpose && !clearlyDifferentPurpose);

    const needsReview =
      !highConfidence &&
      !clearlyMitigated &&
      samePurpose &&
      !clearlyDifferentPurpose;

    repeatedGroups.push({
      key,
      fieldCount: actionable.length,
      requiredCount,
      uniqueForms,
      hasPrefilledRepeat,
      hasAutocompleteSupport,
      hasReuseMechanism,
      highConfidence,
      needsReview,
      samePurpose,
      clearlyDifferentPurpose,
      samePurposePairs: pairwiseEvidence.samePurposePairs,
      distinctPurposePairs: pairwiseEvidence.distinctPurposePairs,
      purposeSignatures: unique(actionable.map((f) => f.purposeSignature).filter(Boolean)).slice(0, 10),
      processTypes: unique(actionable.map((f) => f.processType).filter(Boolean)).slice(0, 10),
      allSelectors: actionable.map((f) => f.selector),
      sampleSelectors: actionable.slice(0, 3).map((f) => f.selector),
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

function mergeFrameData(main, frameDataList) {
  const merged = {
    formCount: main.formCount || 0,
    candidateCount: main.candidateCount || 0,
    globalReuseControlCount: main.globalReuseControlCount || 0,
    repeatedGroups: Array.isArray(main.repeatedGroups) ? [...main.repeatedGroups] : [],
    highConfidenceGroups: Array.isArray(main.highConfidenceGroups) ? [...main.highConfidenceGroups] : [],
    reviewGroups: Array.isArray(main.reviewGroups) ? [...main.reviewGroups] : [],
  };

  for (const frame of frameDataList) {
    merged.formCount += frame.formCount || 0;
    merged.candidateCount += frame.candidateCount || 0;
    merged.globalReuseControlCount += frame.globalReuseControlCount || 0;

    for (const fg of frame.repeatedGroups || []) {
      const existing = merged.repeatedGroups.find((g) =>
        g.key === fg.key &&
        JSON.stringify(g.purposeSignatures || []) === JSON.stringify(fg.purposeSignatures || [])
      );

      if (existing) {
        existing.fieldCount += fg.fieldCount || 0;
        existing.requiredCount += fg.requiredCount || 0;
        existing.uniqueForms += fg.uniqueForms || 0;
        existing.hasPrefilledRepeat = existing.hasPrefilledRepeat || fg.hasPrefilledRepeat;
        existing.hasAutocompleteSupport = existing.hasAutocompleteSupport && fg.hasAutocompleteSupport;
        existing.hasReuseMechanism = existing.hasReuseMechanism || fg.hasReuseMechanism;
        existing.samePurpose = existing.samePurpose || fg.samePurpose;
        existing.clearlyDifferentPurpose = existing.clearlyDifferentPurpose || fg.clearlyDifferentPurpose;
        existing.samePurposePairs = (existing.samePurposePairs || 0) + (fg.samePurposePairs || 0);
        existing.distinctPurposePairs = (existing.distinctPurposePairs || 0) + (fg.distinctPurposePairs || 0);
        existing.processTypes = unique([...(existing.processTypes || []), ...(fg.processTypes || [])]);
        existing.purposeSignatures = unique([...(existing.purposeSignatures || []), ...(fg.purposeSignatures || [])]);
        existing.allSelectors = [...(existing.allSelectors || []), ...(fg.allSelectors || [])];
        existing.sampleSelectors = existing.allSelectors.slice(0, 3);

        const sameProcessLike = (existing.processTypes || []).length <= 1
          || (existing.samePurposePairs || 0) > (existing.distinctPurposePairs || 0);

        existing.highConfidence =
          existing.requiredCount >= 2 &&
          existing.samePurpose &&
          sameProcessLike &&
          !existing.clearlyDifferentPurpose &&
          !existing.hasPrefilledRepeat &&
          !existing.hasReuseMechanism &&
          !existing.hasAutocompleteSupport;

        const clearlyMitigated =
          existing.hasPrefilledRepeat ||
          existing.hasReuseMechanism ||
          (existing.hasAutocompleteSupport && existing.samePurpose && !existing.clearlyDifferentPurpose);

        existing.needsReview =
          !existing.highConfidence &&
          !clearlyMitigated &&
          existing.samePurpose &&
          !existing.clearlyDifferentPurpose;
      } else {
        merged.repeatedGroups.push({ ...fg });
      }
    }
  }

  merged.highConfidenceGroups = merged.repeatedGroups.filter((g) => g.highConfidence);
  merged.reviewGroups = merged.repeatedGroups.filter((g) => g.needsReview);

  return merged;
}

async function run(page) {
  await page.waitForLoadState?.('domcontentloaded').catch(() => {});
  await page.waitForNetworkIdle?.({ timeout: 3000 }).catch(() => {});
  await page.waitForSelector('input, select, textarea', { timeout: 5000 }).catch(() => {});

  const mainData = await page.evaluate(
    evaluatePage,
    PERSONAL_AUTOCOMPLETE_TOKENS,
    CONFIRM_RE.source,
    REUSE_CONTROL_RE.source,
    PERSONAL_KEYWORDS.map(([re, key]) => [re.source, key])
  );

  const frames = page.frames().filter((f) => f !== page.mainFrame());
  const frameResults = await Promise.all(
    frames.map((frame) =>
      frame.evaluate(
        evaluatePage,
        PERSONAL_AUTOCOMPLETE_TOKENS,
        CONFIRM_RE.source,
        REUSE_CONTROL_RE.source,
        PERSONAL_KEYWORDS.map(([re, key]) => [re.source, key])
      ).catch(() => null)
    )
  );

  const data = mergeFrameData(mainData, frameResults.filter(Boolean));

  function buildResult(status, impact, reason, extraDebug = {}, elements = []) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Previously entered information should not be required again in the same process',
        impact,
        status,
        reason,
        helpUrl: HELP_URL,
        ...(elements.length > 0 ? { elements } : {}),
      }],
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
    const elements = _elementsFromGroups(data.highConfidenceGroups);
    return buildResult(
      'fail',
      'moderate',
      `${data.highConfidenceGroups.length} high-confidence redundant-entry issue(s) detected: required personal data appears to be entered again with no detectable reuse/prefill mechanism. Examples: ${sample}.`,
      {},
      elements
    );
  }

  if (data.reviewGroups.length > 0) {
    const sample = summarizeGroups(data.reviewGroups);
    const elements = _elementsFromGroups(data.reviewGroups);
    return buildResult(
      'incomplete',
      'moderate',
      `${data.reviewGroups.length} repeated required personal-data group(s) detected that need manual verification for SC 3.3.7. Confirm whether previously entered values are auto-populated or selectable in the real process flow. Examples: ${sample}.`,
      {},
      elements
    );
  }

  return buildResult(
    'pass',
    null,
    `${data.repeatedGroups.length} repeated personal-data group(s) detected, and reuse or prefill mechanisms were also detected.`
  );
}

module.exports = { run, SC, RULE_ID, HELP_URL };
