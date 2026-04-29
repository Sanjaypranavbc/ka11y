'use strict';

const {
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

// This check lives under SC 1.1.1. It emits a supplementary finding for
// 1.4.5 when the background-image's src/URL suggests it carries text.
const SC = '1.1.1';
const RULE_ID = 'custom-background-image-content';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/non-text-content';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'CSS background images carrying meaningful content must have a text alternative';

const MAX_CANDIDATES = 400;

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);

  const data = await page.evaluate((max) => {
    const TEXT_HINT_RE = /(banner|headline|title|hero|cta|promo|callout|masthead|heading|text)/i;
    const DECORATIVE_HINT_RE = /(gradient|pattern|noise|texture|overlay|mask|fade|blur|dot|dots|divider|separator)/i;

    const out = { total: 0, candidates: [], textCandidates: [] };
    const all = document.querySelectorAll('*');

    for (const el of all) {
      if (out.candidates.length >= max) break;

      const cs = window.getComputedStyle(el);
      const bg = cs.backgroundImage;
      if (!bg || bg === 'none') continue;

      // Skip pure-gradient backgrounds — they are decorative by definition.
      if (bg.includes('gradient') && !bg.includes('url(')) continue;

      const urlMatch = bg.match(/url\((['"]?)(.*?)\1\)/);
      if (!urlMatch) continue;
      const url = urlMatch[2] || '';
      if (!url || url.startsWith('data:image/')) continue; // skip inline data URIs
      if (DECORATIVE_HINT_RE.test(url)) continue;

      // Visibility + area gate: tiny backgrounds are likely icons/bullets.
      const rect = el.getBoundingClientRect();
      if (rect.width < 24 || rect.height < 24) continue;
      if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity || '1') === 0) continue;

      // Skip when the element is a <button>/<a> with a text label — name already
      // covered by other rules.
      const role = el.getAttribute('role') || '';
      const tag = el.tagName.toLowerCase();
      const isInteractive = tag === 'button' || tag === 'a' || role === 'button' || role === 'link';
      const accName = (
        (el.getAttribute('aria-label') || '')
        + ' ' + (el.getAttribute('title') || '')
        + ' ' + (el.textContent || '')
      ).trim();
      const hasAccName = accName.length > 0;

      out.total += 1;

      // Skip decorative role.
      if (role === 'presentation' || role === 'none' || el.getAttribute('aria-hidden') === 'true') {
        continue;
      }

      const entry = {
        html: el.outerHTML.slice(0, 200),
        element_id: el.id || null,
        target: el.id ? [`${tag}#${CSS.escape(el.id)}`] : [tag],
        tag: el.tagName,
        url: url.slice(0, 180),
        hasAccName,
        isInteractive,
      };

      // 1.1.1 candidate: non-decorative bg image with no accessible name
      // on the host element.
      if (!hasAccName) {
        out.candidates.push(entry);
      }

      // 1.4.5 candidate: filename keywords suggest image-of-text.
      if (TEXT_HINT_RE.test(url)) {
        out.textCandidates.push(entry);
      }
    }

    return out;
  }, MAX_CANDIDATES);

  const rules = [];

  if (data.total === 0) {
    rules.push({
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: null,
      status: 'pass',
      reason: _t(sharedContext, 'No non-decorative CSS background images detected.', '装飾以外の CSS 背景画像は検出されませんでした。'),
      helpUrl: HELP_URL,
    });
  } else if (data.candidates.length === 0) {
    rules.push({
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: null,
      status: 'pass',
      reason: _t(
        sharedContext,
        '{total} CSS background image(s) reviewed — all containers expose an accessible name.',
        '{total} 件の CSS 背景画像を確認しました — すべてのコンテナにアクセシブルな名前があります。',
        { total: data.total },
      ),
      helpUrl: HELP_URL,
    });
  } else {
    rules.push({
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'moderate',
      status: 'incomplete',
      reason: _t(
        sharedContext,
        '{count} CSS background image(s) appear on non-decorative elements without an accessible name. Confirm they are purely decorative or add alt-equivalent text.',
        '装飾ではない要素に配置された {count} 件の CSS 背景画像にアクセシブルな名前が見つかりません。装飾であることを確認するか、代替テキストを追加してください。',
        { count: data.candidates.length },
      ),
      elements: data.candidates.slice(0, 30),
      helpUrl: HELP_URL,
    });
  }

  if (data.textCandidates.length > 0) {
    rules.push({
      ruleId: `${RULE_ID}-text-image`,
      description: 'CSS background images that appear to contain text must not be used when real text can achieve the same presentation',
      impact: 'moderate',
      status: 'incomplete',
      reason: _t(
        sharedContext,
        '{count} CSS background image(s) have src keywords suggesting they carry text content (banner/headline/hero). Replace with real CSS-styled text where possible (WCAG 1.4.5).',
        '{count} 件の CSS 背景画像は URL にテキストを含むことを示唆するキーワード（banner/headline/hero）があります。可能であれば CSS でスタイルを整えた実テキストに置き換えてください（WCAG 1.4.5）。',
        { count: data.textCandidates.length },
      ),
      elements: data.textCandidates.slice(0, 30),
      helpUrl: 'https://www.w3.org/WAI/WCAG22/Understanding/images-of-text',
    });
  }

  return {
    successCriteriaId: SC,
    rules,
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
