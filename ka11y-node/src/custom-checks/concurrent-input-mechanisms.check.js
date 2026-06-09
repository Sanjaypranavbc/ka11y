'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '2.5.6';
const RULE_ID = 'custom-concurrent-input-mechanisms';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/concurrent-input-mechanisms';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Web content must not restrict use of input modalities available on a platform';

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

  const data = await page.evaluate(() => {
    const issues = [];

    // ── Check 1: touch-action: none on interactive elements ───────────────────
    // Prevents touch-based interaction; may break on touch-only devices.
    const INTERACTIVE = 'button,a[href],[role="button"],[role="link"],input,select,textarea';
    for (const el of document.querySelectorAll(INTERACTIVE)) {
      const cs = window.getComputedStyle(el);
      if (cs.touchAction === 'none') {
        issues.push({
          type: 'touch-action-none',
          target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
          snippet: el.outerHTML.slice(0, 150),
          detail: 'touch-action: none restricts touch input on this interactive element',
        });
      }
    }

    // ── Check 2: Scripts that detect and restrict pointer type ─────────────────
    // Look for inline scripts that reference pointer type restrictions
    const POINTER_RESTRICT_RE = /navigator\s*\.\s*(?:maxTouchPoints|msMaxTouchPoints)|window\s*\.\s*PointerEvent|pointerType\s*===?\s*["'](?:mouse|touch|pen)["']/;
    for (const script of document.querySelectorAll('script:not([src])')) {
      const src = script.textContent || '';
      if (POINTER_RESTRICT_RE.test(src) && /(?:return|break|throw|return\s+false|event\.preventDefault)/.test(src)) {
        issues.push({
          type: 'pointer-type-restriction',
          target: 'inline script',
          snippet: src.slice(0, 150),
          detail: 'Script may restrict functionality to specific pointer types',
        });
        break; // one finding per page is enough for this heuristic
      }
    }

    // ── Check 3: user-select: none on page-level content ─────────────────────
    // Preventing text selection blocks keyboard+mouse selection workflows.
    const CONTENT_SELECTOR = 'article,main,p,[role="article"],[role="main"],.content';
    for (const el of document.querySelectorAll(CONTENT_SELECTOR)) {
      const cs = window.getComputedStyle(el);
      if (cs.userSelect === 'none' || cs.webkitUserSelect === 'none') {
        issues.push({
          type: 'user-select-none',
          target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
          snippet: el.outerHTML.slice(0, 100),
          detail: 'user-select: none on content area restricts text-selection via pointer and keyboard',
        });
      }
    }

    return { issues };
  });

  if (!data.issues.length) {
    return _pass(ctx, _t(ctx,
      'No input modality restrictions detected (touch-action, pointer-type locks, or user-select: none on content).',
      '入力モダリティの制限は検出されませんでした（touch-action、ポインタータイプのロック、コンテンツへの user-select: none）。'));
  }

  const byType = {};
  for (const iss of data.issues) byType[iss.type] = (byType[iss.type] || 0) + 1;
  const summary = Object.entries(byType).map(([k, v]) => `${k}(${v})`).join(', ');

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'moderate',
      status: 'incomplete',
      reason: _t(ctx,
        '{n} input modality restriction(s) detected ({summary}). Manual review required.',
        '{n} 件の入力モダリティ制限が検出されました（{summary}）。手動確認が必要です。',
        { n: data.issues.length, summary }),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
