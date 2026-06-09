'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '1.4.12';
const RULE_ID = 'custom-text-spacing';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/text-spacing';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Content must not lose information when line height, letter spacing, word spacing, or paragraph spacing is overridden';

const SETTLE_MS = 300;

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

  try {
    // Inject WCAG 1.4.12 spacing overrides (bookmarklet technique)
    await page.evaluate(() => {
      const style = document.createElement('style');
      style.id = '__ka11y_text_spacing__';
      style.textContent = `
        * { line-height: 1.5 !important; letter-spacing: 0.12em !important; word-spacing: 0.16em !important; }
        p  { margin-bottom: 2em !important; }
      `;
      document.head.appendChild(style);
      return new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    });

    await new Promise(r => setTimeout(r, SETTLE_MS));

    const data = await page.evaluate(() => {
      const issues = [];
      const CANDIDATES = 'p,h1,h2,h3,h4,h5,h6,li,td,th,div,span,section,article,aside,main,header,footer,nav';
      for (const el of document.querySelectorAll(CANDIDATES)) {
        const cs = window.getComputedStyle(el);
        const ovX = cs.overflowX;
        const ovY = cs.overflowY;
        const clipsX = ovX === 'hidden' || ovX === 'clip';
        const clipsY = ovY === 'hidden' || ovY === 'clip';
        if (!clipsX && !clipsY) continue;
        if (!(el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1)) continue;
        const text = (el.textContent || '').trim();
        if (!text) continue;
        issues.push({
          target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
          snippet: el.outerHTML.slice(0, 120),
          detail: `overflow:${clipsX ? ovX : ''} ${clipsY ? ovY : ''} clips content — scrollHeight ${el.scrollHeight}px vs clientHeight ${el.clientHeight}px`,
        });
        if (issues.length >= 20) break;
      }
      return { issues };
    });

    if (!data.issues.length) {
      return _pass(ctx, _t(ctx,
        'No content clipping detected when WCAG 1.4.12 text-spacing overrides are applied.',
        'WCAG 1.4.12 のテキスト間隔上書き適用時にコンテンツのクリッピングは検出されませんでした。'));
    }

    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: FALLBACK_DESCRIPTION,
        impact: 'serious',
        status: 'fail',
        reason: _t(ctx,
          '{n} element(s) clip content when WCAG 1.4.12 spacing overrides are applied (overflow:hidden/clip with scroll overflow). Users who override spacing via user stylesheets will lose content.',
          '{n} 件の要素で WCAG 1.4.12 スペーシング上書き適用時にコンテンツがクリップされます。',
          { n: data.issues.length }),
        elements: data.issues,
        helpUrl: HELP_URL,
      }],
    };
  } finally {
    await page.evaluate(() => {
      const el = document.getElementById('__ka11y_text_spacing__');
      if (el) el.remove();
    }).catch(() => {});
  }
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
