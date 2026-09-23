'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '3.1.4';
const RULE_ID = 'custom-abbreviations';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/abbreviations';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'A mechanism must be available for identifying the expanded form of abbreviations';

function _t(ctx, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, ctx, en);
}

function _pass(ctx, reason) {
  return {
    successCriteriaId: SC,
    rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'pass', reason, helpUrl: HELP_URL }],
  };
}
function _na(ctx, reason) {
  return {
    successCriteriaId: SC,
    rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'not_applicable', reason, helpUrl: HELP_URL }],
  };
}

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  const data = await page.evaluate(() => {
    const abbrs = Array.from(document.querySelectorAll('abbr'));

    // G102 / G97: acronyms written in prose. The first occurrence should be followed
    // (or preceded) by its expansion — "World Wide Web Consortium (W3C)" or
    // "W3C (World Wide Web Consortium)". Acronyms that appear ≥ 2 times with neither an
    // <abbr title> nor a prose expansion are reported for review.
    const prose = { expanded: [], unexpanded: [], scanned: 0 };
    try {
      const COMMON = new Set(['HTML', 'CSS', 'URL', 'PDF', 'FAQ', 'USA', 'UK', 'EU', 'ID', 'OK', 'TV', 'PC', 'AM', 'PM', 'CEO', 'CTO', 'CFO', 'NEW', 'API', 'USB', 'GPS', 'AI', 'IT', 'HR', 'PR', 'UI', 'UX', 'SEO', 'ATM', 'DIY', 'ASAP', 'FYI', 'RSVP', 'VIP', 'VAT', 'GDPR', 'ISO', 'JSON', 'XML', 'HTTP', 'HTTPS', 'WWW', 'COVID', 'NHS', 'BBC', 'CNN', 'NASA', 'NATO', 'UN', 'US', 'GB', 'JP', 'FR', 'DE', 'PIN', 'SMS', 'MMS', 'CC', 'BCC', 'CD', 'DVD', 'HD', 'RGB', 'LED', 'LCD', 'RAM', 'CPU', 'GPU', 'SSD', 'PNG', 'JPG', 'JPEG', 'GIF', 'SVG', 'MP3', 'MP4', 'ZIP', 'CSV', 'DOC', 'PPT', 'XLS', 'WCAG', 'ARIA', 'W3C', 'IE', 'IOS', 'MAC', 'GMT', 'UTC', 'EST', 'PST']);
      const bodyText = (document.body ? document.body.innerText || '' : '').replace(/\s+/g, ' ').slice(0, 60000);
      prose.scanned = bodyText.length;
      const abbrTexts = new Set(abbrs.map(a => (a.textContent || '').trim()));
      const counts = {};
      for (const m of bodyText.matchAll(/\b([A-Z][A-Z0-9]{1,5})\b/g)) { const t = m[1]; if (/\d/.test(t) && t.length < 3) continue; counts[t] = (counts[t] || 0) + 1; }
      const expandedSet = new Set();
      for (const m of bodyText.matchAll(/\b((?:[A-Z][a-zA-Z-]+\s+){1,5}[A-Z][a-zA-Z-]+)\s*\(([A-Z][A-Z0-9]{1,5})\)/g)) expandedSet.add(m[2]);
      for (const m of bodyText.matchAll(/\b([A-Z][A-Z0-9]{1,5})\s*\(([^)]{4,80})\)/g)) { if (/[a-z]/.test(m[2])) expandedSet.add(m[1]); }
      for (const [acr, n] of Object.entries(counts)) {
        if (COMMON.has(acr) || abbrTexts.has(acr)) continue;
        if (expandedSet.has(acr)) { prose.expanded.push(acr); continue; }
        if (n >= 2 && !/^[A-Z]{2}$/.test(acr)) prose.unexpanded.push({ acronym: acr, count: n });
      }
      prose.unexpanded.sort((a, b) => b.count - a.count);
      prose.unexpanded = prose.unexpanded.slice(0, 10);
    } catch (_) { /* ignore */ }

    if (!abbrs.length) return { abbrCount: 0, issues: [], prose };

    const issues = [];
    for (const abbr of abbrs) {
      const title = (abbr.getAttribute('title') || '').trim();
      if (!title) {
        issues.push({
          target: 'abbr',
          snippet: abbr.outerHTML.slice(0, 100),
          detail: `<abbr> "${abbr.textContent.trim()}" is missing a title attribute with its expanded form`,
        });
      }
    }
    return { abbrCount: abbrs.length, issues, prose };
  });

  const prose = (data && data.prose) || { expanded: [], unexpanded: [] };
  const proseRule = () => {
    if (!prose.unexpanded || !prose.unexpanded.length) return null;
    return {
      ruleId: `${RULE_ID}-prose`,
      description: FALLBACK_DESCRIPTION,
      impact: 'minor',
      status: 'incomplete',
      reason: _t(ctx,
        '{n} acronym(s) are used repeatedly without <abbr title> or an expansion in the text on first use ({sample}); {e} other acronym(s) are expanded in prose (G97/G102). Expand each on first use or use <abbr>.',
        '{n} 件の略語が <abbr title> も本文中の初出時の展開もなく繰り返し使われています（{sample}）。他の {e} 件は本文中で展開されています（G97/G102）。初出時に展開するか <abbr> を使ってください。',
        { n: prose.unexpanded.length, sample: prose.unexpanded.slice(0, 5).map(u => `${u.acronym}×${u.count}`).join(', '), e: (prose.expanded || []).length }),
      elements: prose.unexpanded.map(u => ({ target: 'text', snippet: u.acronym, detail: `"${u.acronym}" appears ${u.count} times with no expansion` })),
      helpUrl: HELP_URL,
    };
  };

  if (!data.abbrCount) {
    const pr = proseRule();
    if (pr) return { successCriteriaId: SC, rules: [pr] };
    if (prose.expanded && prose.expanded.length) {
      return _pass(ctx, _t(ctx,
        'No <abbr> elements, but {e} acronym(s) are expanded in the text on first use ({sample}) — G97/G102 satisfied in prose.',
        '<abbr> 要素はありませんが、{e} 件の略語が本文の初出時に展開されています（{sample}）。G97/G102 は本文中で満たされています。',
        { e: prose.expanded.length, sample: prose.expanded.slice(0, 5).join(', ') }));
    }
    return _na(ctx, _t(ctx,
      'No <abbr> elements and no repeated unexplained acronyms found — criterion not applicable.',
      'このページに <abbr> 要素はなく、説明のない略語の繰り返しもありません。略語の展開メカニズムは不要です。'));
  }

  if (!data.issues.length) {
    const pr = proseRule();
    const base = { ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'pass', helpUrl: HELP_URL, reason: _t(ctx,
      'All {n} <abbr> element(s) have a title attribute providing the expanded form{e}.',
      '{n} 件の <abbr> 要素すべてに展開形を示す title 属性があります{e}。',
      { n: data.abbrCount, e: prose.expanded && prose.expanded.length ? _t(ctx, `; ${prose.expanded.length} more acronym(s) are expanded in prose (G97)`, `。さらに ${prose.expanded.length} 件の略語が本文中で展開されています（G97）`) : '' }) };
    return { successCriteriaId: SC, rules: pr ? [base, pr] : [base] };
  }

  const rules = [{
    ruleId: RULE_ID,
    description: FALLBACK_DESCRIPTION,
    impact: 'minor',
    status: 'fail',
    reason: _t(ctx,
      '{i} of {n} <abbr> element(s) are missing a title attribute with the expanded form.',
      '{n} 件中 {i} 件の <abbr> 要素に展開形を示す title 属性がありません。',
      { i: data.issues.length, n: data.abbrCount }),
    elements: data.issues,
    helpUrl: HELP_URL,
  }];
  const pr = proseRule();
  if (pr) rules.push(pr);
  return { successCriteriaId: SC, rules };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
