'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '3.3.9';
const RULE_ID = 'custom-accessible-auth-enhanced';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/accessible-authentication-enhanced';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Authentication must not require cognitive function tests — including copy-paste and password manager blocking';

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
    const issues = [];

    const pwdInputs = Array.from(document.querySelectorAll('input[type="password"]'));
    if (!pwdInputs.length) return { pwdCount: 0, issues: [] };

    for (const inp of pwdInputs) {
      const selector = `input[type="password"]${inp.id ? '#' + CSS.escape(inp.id) : inp.name ? `[name="${inp.name}"]` : ''}`;

      // ── Check 1: autocomplete="off" / autocomplete="new-password" (blocks managers) ──
      const autoComplete = (inp.getAttribute('autocomplete') || '').toLowerCase();
      // 'off' and 'current-password' when combined with paste-block is the real risk.
      // 'new-password' is acceptable; 'off' or completely missing can cause issues.
      if (autoComplete === 'off') {
        issues.push({
          type: 'autocomplete-off',
          target: selector,
          snippet: inp.outerHTML.slice(0, 150),
          detail: 'autocomplete="off" on password field may prevent password manager autofill',
        });
      }

      // ── Check 2: Paste prevention via inline event attributes ─────────────────
      if (inp.getAttribute('onpaste') === 'return false' || inp.getAttribute('onpaste') === 'return false;') {
        issues.push({
          type: 'paste-blocked',
          target: selector,
          snippet: inp.outerHTML.slice(0, 150),
          detail: 'onpaste="return false" blocks pasting into password field',
        });
      }

      // ── Check 3: Script-attached paste prevention ─────────────────────────────
      // Look for inline scripts that attach paste blockers to password inputs
      for (const script of document.querySelectorAll('script:not([src])')) {
        const src = script.textContent || '';
        if (/password|passwd|pwd/.test(src) && /\.addEventListener\s*\(\s*['"]paste['"]/.test(src) && /preventDefault/.test(src)) {
          issues.push({
            type: 'script-paste-blocked',
            target: 'inline script (password field)',
            snippet: src.slice(0, 150),
            detail: 'Script adds a paste event listener with preventDefault on a password field',
          });
          break;
        }
      }

      // ── Check 4: Cognitive test pattern — copy prevention on confirm field ──
      if (/confirm|repeat|retype/.test((inp.getAttribute('name') || inp.getAttribute('id') || inp.getAttribute('placeholder') || '').toLowerCase())) {
        const pasteAttr = inp.getAttribute('onpaste') || '';
        const copyAttr = inp.getAttribute('oncopy') || '';
        if (/false/.test(pasteAttr) || /false/.test(copyAttr)) {
          issues.push({
            type: 'confirm-paste-blocked',
            target: selector,
            snippet: inp.outerHTML.slice(0, 150),
            detail: 'Paste is blocked on a "confirm password" field, forcing manual retyping (cognitive function test)',
          });
        }
      }
    }

    return { pwdCount: pwdInputs.length, issues };
  });

  if (!data.pwdCount) {
    return _na(ctx, _t(ctx, 'No password fields found on this page — criterion not applicable.', 'このページにパスワードフィールドはありません。'));
  }

  if (!data.issues.length) {
    return _pass(ctx, _t(ctx,
      '{n} password field(s) checked — no paste-blocking, autocomplete="off", or password manager barriers detected.',
      '{n} 件のパスワードフィールドを確認しました。貼り付けブロック、autocomplete="off"、パスワードマネージャーの障壁は検出されませんでした。',
      { n: data.pwdCount }));
  }

  const byType = {};
  for (const iss of data.issues) byType[iss.type] = (byType[iss.type] || 0) + 1;
  const summary = Object.entries(byType).map(([k, v]) => `${k}(${v})`).join(', ');

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'serious',
      status: 'fail',
      reason: _t(ctx,
        '{n} authentication barrier(s) detected on password field(s) ({summary}).',
        'パスワードフィールドで {n} 件の認証障壁が検出されました（{summary}）。',
        { n: data.issues.length, summary }),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
