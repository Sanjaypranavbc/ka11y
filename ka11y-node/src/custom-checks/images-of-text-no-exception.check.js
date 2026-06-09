'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '1.4.9';
const RULE_ID = 'custom-images-of-text-no-exception';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/images-of-text-no-exception';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Images of text must not be used — essential text must be real text, with no exception for logos';

function _t(ctx, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, ctx, en);
}

function _pass(ctx, reason) {
  return {
    successCriteriaId: SC,
    rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'pass', reason, helpUrl: HELP_URL }],
  };
}

// Heuristically detect images that likely contain text
// (SC 1.4.9 has no logo exception unlike 1.4.5)
async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  const data = await page.evaluate(() => {
    const issues = [];
    const TEXT_IN_ALT_RE = /\b(?:text|heading|title|label|caption|button|nav|menu|banner|logo|wordmark|tagline|slogan)\b/i;
    const TEXT_IN_SRC_RE = /[_-](?:text|heading|title|label|btn|button|banner|logo|wordmark|sign|badge|stamp)[._-]/i;
    // Patterns in alt/src that strongly suggest an image contains rendered text
    const ALT_WORDS_RE = /^[A-Za-z\d\s\-_.,:!?'"&/()]{5,80}$/; // alt that looks like a sentence/phrase

    const imgs = Array.from(document.querySelectorAll('img[alt]'));
    for (const img of imgs) {
      const alt = (img.getAttribute('alt') || '').trim();
      if (!alt) continue; // decorative or missing alt handled elsewhere

      const src = img.getAttribute('src') || img.getAttribute('data-src') || '';
      const srcBasename = src.split('/').pop().split('?')[0] || '';

      const looksLikeText =
        TEXT_IN_ALT_RE.test(alt) ||
        TEXT_IN_SRC_RE.test(srcBasename) ||
        (ALT_WORDS_RE.test(alt) && alt.split(/\s+/).length >= 2);

      if (looksLikeText) {
        issues.push({
          target: img.id ? `img#${CSS.escape(img.id)}` : 'img',
          snippet: img.outerHTML.slice(0, 200),
          detail: `alt="${alt.slice(0, 80)}"`,
        });
      }
    }

    // Also check CSS background images on elements that have text-related class/id names
    const BG_TEXT_SELECTOR = '[class*="logo"],[class*="wordmark"],[class*="banner"],[class*="text-img"],[id*="logo"],[id*="banner"]';
    for (const el of document.querySelectorAll(BG_TEXT_SELECTOR)) {
      const cs = window.getComputedStyle(el);
      if (cs.backgroundImage && cs.backgroundImage !== 'none') {
        const text = (el.textContent || '').trim();
        const ariaLabel = el.getAttribute('aria-label') || el.getAttribute('title') || '';
        if (!text && !ariaLabel) {
          issues.push({
            type: 'css-background-text',
            target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
            snippet: el.outerHTML.slice(0, 200),
            detail: 'CSS background image with no text alternative (possible image of text)',
          });
        }
      }
    }

    return { imgCount: document.querySelectorAll('img').length, issues };
  });

  if (!data.imgCount) {
    return _pass(ctx, _t(ctx, 'No <img> elements found on this page.', 'このページに <img> 要素はありません。'));
  }
  if (!data.issues.length) {
    return _pass(ctx, _t(ctx,
      'No images that appear to contain text without a real-text equivalent were detected.',
      'テキストを含む可能性のある画像で、実テキストの代替がないものは検出されませんでした。'));
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'moderate',
      status: 'incomplete',
      reason: _t(ctx,
        '{n} image(s) may be images of text (including logos). Verify these use real text instead. Manual review required.',
        '{n} 件の画像がテキストを含む画像（ロゴを含む）の可能性があります。実テキストへの置き換えを確認してください。',
        { n: data.issues.length }),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
