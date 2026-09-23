'use strict';

/**
 * WCAG 3.1.1 Language of Page — HTTP-level signal (SVR5).
 *
 * axe checks the html lang attribute. This check reads the Content-Language
 * response header recorded by the service on `page.__ka11yNav` and compares it
 * with the html lang, and detects a document whose text script contradicts the
 * declared language.
 */

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '3.1.1';
const RULE_ID = 'custom-language-of-page';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/language-of-page';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'The default human language of each page must be programmatically determinable';

function _t(ctx, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, ctx, en);
}

function _primary(tag) {
  return String(tag || '').trim().toLowerCase().split(/[-_]/)[0];
}

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);
  const nav = page && page.__ka11yNav && typeof page.__ka11yNav === 'object' ? page.__ka11yNav : null;
  const headers = nav && nav.headers ? nav.headers : {};
  const headerLang = String(headers['content-language'] || headers['Content-Language'] || '').split(',')[0].trim();

  const raw = await page.evaluate(() => {
    const lang = document.documentElement.getAttribute('lang') || '';
    const xml = document.documentElement.getAttribute('xml:lang') || '';
    const meta = document.querySelector('meta[http-equiv="content-language" i]');
    const body = (document.body ? document.body.innerText || '' : '').slice(0, 6000);
    const cjk = (body.match(/[぀-ヿ㐀-鿿]/g) || []).length;
    const kana = (body.match(/[぀-ヿ]/g) || []).length;
    const hangul = (body.match(/[가-힯]/g) || []).length;
    const cyr = (body.match(/[Ѐ-ӿ]/g) || []).length;
    const arabic = (body.match(/[؀-ۿ]/g) || []).length;
    const latin = (body.match(/[A-Za-zÀ-ɏ]/g) || []).length;
    return { lang, xml, metaLang: meta ? (meta.getAttribute('content') || '') : '', total: body.length, cjk, kana, hangul, cyr, arabic, latin };
  });
  const d = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
  const htmlLang = _primary(d.lang);
  const issues = [];

  // ── SVR5: Content-Language header vs html lang ───────────────────────────
  if (headerLang && htmlLang && _primary(headerLang) !== htmlLang) {
    issues.push({ type: 'content-language-mismatch', technique: 'SVR5', target: 'html', snippet: `Content-Language: ${headerLang} / <html lang="${d.lang}">`, detail: `HTTP Content-Language header says "${headerLang}" but html lang is "${d.lang}" — the two signals disagree; user agents prefer the lang attribute but the header should match (SVR5)` });
  }
  if (d.metaLang && htmlLang && _primary(d.metaLang) !== htmlLang) {
    issues.push({ type: 'meta-language-mismatch', technique: 'SVR5', target: 'meta[http-equiv="content-language"]', snippet: `<meta http-equiv="content-language" content="${d.metaLang}">`, detail: `meta content-language "${d.metaLang}" contradicts html lang "${d.lang}"` });
  }
  if (d.xml && htmlLang && _primary(d.xml) !== htmlLang) {
    issues.push({ type: 'xml-lang-mismatch', technique: 'H57', target: 'html', snippet: `<html lang="${d.lang}" xml:lang="${d.xml}">`, detail: 'lang and xml:lang differ — they must have the same value (H57)' });
  }

  // ── Script sanity: declared language vs dominant script ──────────────────
  if (htmlLang && d.total > 400) {
    const dominant = d.kana > 40 && d.kana > d.latin * 0.2 ? 'ja' : d.hangul > 40 && d.hangul > d.latin * 0.2 ? 'ko' : d.cyr > d.latin && d.cyr > 40 ? 'ru' : d.arabic > d.latin && d.arabic > 40 ? 'ar' : (d.cjk > 40 && d.kana === 0 && d.cjk > d.latin * 0.3) ? 'zh' : null;
    const declaredScript = ['ja'].includes(htmlLang) ? 'ja' : ['ko'].includes(htmlLang) ? 'ko' : ['ru', 'uk', 'bg', 'sr', 'mk', 'be', 'kk'].includes(htmlLang) ? 'ru' : ['ar', 'fa', 'ur'].includes(htmlLang) ? 'ar' : ['zh'].includes(htmlLang) ? 'zh' : 'latin';
    if (dominant && dominant !== declaredScript) {
      issues.push({ type: 'lang-script-mismatch', technique: 'H57', target: 'html', snippet: `<html lang="${d.lang}">`, detail: `Page text is predominantly ${dominant === 'ja' ? 'Japanese' : dominant === 'ko' ? 'Korean' : dominant === 'ru' ? 'Cyrillic' : dominant === 'ar' ? 'Arabic' : 'Chinese'} but html lang is "${d.lang}" — screen readers will use the wrong voice (H57)` });
    }
  }

  if (!issues.length) {
    const src = headerLang ? _t(ctx, `; Content-Language header "${headerLang}" agrees`, `。Content-Language ヘッダー「${headerLang}」と一致`) : (nav ? _t(ctx, '; no Content-Language header (lang attribute is sufficient)', '。Content-Language ヘッダーなし（lang 属性で十分）') : '');
    return { successCriteriaId: SC, rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: htmlLang ? 'pass' : 'not_applicable',
      reason: htmlLang ? _t(ctx, 'html lang="{l}" matches the page text script{src}.', 'html lang="{l}" はページ本文の文字体系と一致しています{src}。', { l: d.lang, src }) : _t(ctx, 'No html lang attribute — reported by the html-has-lang rule.', 'html lang 属性がありません。html-has-lang ルールで報告されます。'), helpUrl: HELP_URL }] };
  }
  const hard = issues.some(i => i.type === 'lang-script-mismatch' || i.type === 'xml-lang-mismatch');
  return { successCriteriaId: SC, rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: hard ? 'serious' : 'minor', status: hard ? 'fail' : 'incomplete',
    reason: _t(ctx, 'Language declaration problem: {d}', '言語宣言の問題: {d}', { d: issues[0].detail }), elements: issues, helpUrl: HELP_URL }] };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
