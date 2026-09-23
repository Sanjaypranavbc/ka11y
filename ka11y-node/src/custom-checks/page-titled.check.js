'use strict';

/**
 * WCAG 2.4.2 Page Titled — descriptiveness of the <title> (axe only checks presence).
 *
 *   G88   generic/placeholder titles; title unrelated to the page's main heading
 *   G127  title should identify the site/collection (site name) as well as the page
 */

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '2.4.2';
const RULE_ID = 'custom-page-titled';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/page-titled';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Web pages must have titles that describe topic or purpose';

const GENERIC_TITLE_RE = /^(?:home|home\s*page|homepage|untitled|untitled\s*(?:document|page)|index|index\.html?|default|new\s*page|page|document|welcome|title|site|website|web\s*site|loading\.{0,3}|test|placeholder|ホーム|トップ|トップページ|無題|タイトル|ページ|新しいページ|ようこそ)$/i;

function _t(ctx, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, ctx, en);
}

function _tokens(text) {
  const t = String(text || '').toLowerCase();
  const latin = (t.match(/[a-z0-9À-ɏ]{3,}/g) || []);
  const cjk = [];
  const cjkRuns = t.match(/[぀-ヿ㐀-鿿]{2,}/g) || [];
  for (const run of cjkRuns) for (let i = 0; i + 2 <= run.length; i++) cjk.push(run.slice(i, i + 2));
  const STOP = new Set(['the', 'and', 'for', 'with', 'from', 'your', 'you', 'our', 'are', 'this', 'that', 'page', 'home', 'www', 'com', 'org', 'net', 'html', 'htm']);
  return new Set([...latin, ...cjk].filter(x => !STOP.has(x)));
}

function _overlap(a, b) {
  let n = 0;
  for (const x of a) if (b.has(x)) n++;
  return n;
}

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  const raw = await page.evaluate(() => {
    const title = (document.title || '').trim();
    const h1s = Array.from(document.querySelectorAll('h1')).map(h => (h.textContent || '').replace(/\s+/g, ' ').trim()).filter(Boolean);
    const h2 = document.querySelector('main h2, h2');
    const meta = (name) => { const m = document.querySelector(`meta[property="${name}"], meta[name="${name}"]`); return m ? (m.getAttribute('content') || '').trim() : ''; };
    return {
      title,
      h1s,
      firstH2: h2 ? (h2.textContent || '').replace(/\s+/g, ' ').trim() : '',
      siteName: meta('og:site_name') || meta('application-name') || meta('apple-mobile-web-app-title') || '',
      host: location.hostname || '',
      logoAlt: (() => { const l = document.querySelector('header img[alt], [role="banner"] img[alt], a[href="/"] img[alt]'); return l ? (l.getAttribute('alt') || '').trim() : ''; })(),
      lang: document.documentElement.lang || '',
    };
  });

  const data = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
  const title = String(data.title || '').trim();
  const issues = [];
  const notes = [];

  if (!title) {
    // axe `document-title` reports the missing title; nothing to add here.
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'not_applicable', reason: _t(ctx, 'No <title> present — reported by the document-title rule.', '<title> がありません。document-title ルールで報告されます。'), helpUrl: HELP_URL }],
    };
  }

  const host = String(data.host || '').replace(/^www\./, '');
  const hostLabel = host.split('.')[0] || '';
  const titleLower = title.toLowerCase();

  // ── G88: generic / placeholder / domain-only titles ───────────────────────
  if (GENERIC_TITLE_RE.test(title)) {
    issues.push({ type: 'generic-title', technique: 'G88', target: 'title', snippet: `<title>${title.slice(0, 80)}</title>`, detail: `Title "${title}" is a placeholder or generic word and does not describe the page (G88)` });
  } else if (host && (titleLower === host || titleLower === hostLabel || titleLower === `www.${host}`)) {
    issues.push({ type: 'domain-only-title', technique: 'G88', target: 'title', snippet: `<title>${title.slice(0, 80)}</title>`, detail: `Title is just the domain name "${title}" — it identifies the site but not this page (G88)` });
  } else if (/^https?:\/\//i.test(title)) {
    issues.push({ type: 'url-title', technique: 'G88', target: 'title', snippet: `<title>${title.slice(0, 80)}</title>`, detail: 'Title is a URL rather than a description of the page (G88)' });
  }

  // ── G88: title vs main heading relation ───────────────────────────────────
  const h1s = Array.isArray(data.h1s) ? data.h1s : [];
  const heading = h1s[0] || String(data.firstH2 || '');
  let headingRelated = null;
  if (heading && !issues.length) {
    const tt = _tokens(title), ht = _tokens(heading);
    if (ht.size >= 1) {
      const ov = _overlap(tt, ht);
      headingRelated = ov > 0 || titleLower.includes(heading.toLowerCase().slice(0, 12)) || heading.toLowerCase().includes(titleLower.split(/\s[-|–—:·»]\s/)[0].slice(0, 12));
      if (!headingRelated) {
        issues.push({ type: 'title-unrelated-to-heading', technique: 'G88', target: 'title', snippet: `<title>${title.slice(0, 80)}</title> / <h1>${heading.slice(0, 80)}</h1>`, detail: `Title "${title.slice(0, 60)}" shares no words with the page's main heading "${heading.slice(0, 60)}" — the title should name the page's topic (G88)`, review: true });
      }
    }
  }

  // ── G127: site name in title ──────────────────────────────────────────────
  const siteName = String(data.siteName || data.logoAlt || '').trim();
  const hasSeparator = /\s[-|–—:·»›/]\s/.test(title) || /[|｜]/.test(title);
  const siteInTitle = (siteName && titleLower.includes(siteName.toLowerCase().slice(0, 24))) || (hostLabel.length >= 3 && titleLower.includes(hostLabel));
  if (siteInTitle) notes.push(_t(ctx, 'site name present', 'サイト名あり'));
  else if (siteName) issues.push({ type: 'site-name-missing', technique: 'G127', target: 'title', snippet: `<title>${title.slice(0, 80)}</title>`, detail: `Title does not include the site name "${siteName.slice(0, 40)}" — identify the site as well as the page, e.g. "Page – ${siteName.slice(0, 30)}" (G127)`, review: true });
  else if (!hasSeparator) issues.push({ type: 'site-name-unknown', technique: 'G127', target: 'title', snippet: `<title>${title.slice(0, 80)}</title>`, detail: 'Title has a single segment and no site name could be detected (no og:site_name); consider "Page – Site" so users know which site they are on (G127)', review: true });

  if (!issues.length) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'pass', reason: _t(ctx,
        'Title "{title}" is specific (not generic or domain-only){rel}{notes}.',
        'タイトル「{title}」は具体的です（汎用語やドメイン名のみではありません）{rel}{notes}。',
        { title: title.slice(0, 80), rel: headingRelated ? _t(ctx, ' and relates to the main heading', '。主見出しと関連しています') : '', notes: notes.length ? ` (${notes.join(', ')})` : '' }), helpUrl: HELP_URL }],
    };
  }

  const hardFail = issues.some(i => !i.review);
  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: hardFail ? 'serious' : 'minor',
      status: hardFail ? 'fail' : 'incomplete',
      reason: hardFail
        ? _t(ctx, 'Page title "{title}" does not describe the page: {detail}', 'ページタイトル「{title}」はページを説明していません: {detail}', { title: title.slice(0, 60), detail: issues[0].detail })
        : _t(ctx, 'Page title "{title}" may not fully identify the page or site: {detail}', 'ページタイトル「{title}」はページまたはサイトを十分に識別していない可能性があります: {detail}', { title: title.slice(0, 60), detail: issues[0].detail }),
      elements: issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
