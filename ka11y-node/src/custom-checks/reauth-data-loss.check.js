'use strict';

const {
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '2.2.5';
const RULE_ID = 'custom-reauth-data-loss';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/re-authenticating';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'When an authenticated session expires, users can continue the activity without loss of data after re-authenticating';

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);

  const data = await page.evaluate(() => {
    const issues = [];

    // 1. Find forms that look like login/re-authentication forms
    const forms = Array.from(document.querySelectorAll('form'));
    const loginForms = forms.filter(form => {
      const hasPassword = form.querySelector('input[type="password"]');
      const hasUsername = form.querySelector('input[type="email"], input[type="text"][name*="user"], input[name*="email"], input[autocomplete="username"], input[autocomplete="email"]');
      const formText = (form.textContent || '').toLowerCase();
      const hasLoginText = /sign\s*in|log\s*in|login|re-?authenticate|re-?auth|reauth|session\s*expired|resume|continue|verify|確認|ログイン|サインイン|続ける|再開/i.test(formText);
      return hasPassword && (hasUsername || hasLoginText);
    });

    // 2. Check if login forms preserve user data via hidden fields, localStorage, or sessionStorage
    for (const form of loginForms) {
      const formData = {
        html: form.outerHTML.slice(0, 250),
        element_id: form.id || null,
        target: form.id ? [`form#${CSS.escape(form.id)}`] : ['form'],
        tag: 'FORM',
        issues: [],
      };

      // Check for hidden form fields that might preserve data
      const hiddenFields = form.querySelectorAll('input[type="hidden"]');
      const hiddenNames = Array.from(hiddenFields).map(h => h.getAttribute('name') || '').join(', ');

      // Check for data preservation patterns
      const hasReturnUrl = form.querySelector('input[name*="return"], input[name*="redirect"], input[name*="next"], input[name*="continue"], input[name*="url"]');
      const hasStateField = form.querySelector('input[name*="state"], input[name*="csrf"], input[name*="token"], input[name*="session"]');
      const hasDataPreservation = form.querySelector('input[name*="data"], input[name*="form"], input[name*="preserve"], input[name*="resume"]');

      // Check for localStorage/sessionStorage usage hints in the form
      const hasStorageHints = form.hasAttribute('data-persist') || form.hasAttribute('data-preserve-form');

      // Check for AJAX/fetch submissions (might preserve state better)
      const hasAjaxHandler = form.hasAttribute('data-ajax') || form.hasAttribute('data-fetch');

      if (!hasReturnUrl && !hasStateField && !hasDataPreservation && !hasStorageHints) {
        formData.issues.push('No detected mechanism to preserve user data or return URL after re-authentication');
      }

      if (formData.issues.length > 0) {
        issues.push(formData);
      }
    }

    // 3. Check for session expiry indicators that suggest poor UX
    const sessionExpiryElements = document.querySelectorAll('[data-session-expiry], .session-expiry, .session-timeout-warning, .reauth-prompt');
    sessionExpiryElements.forEach(el => {
      issues.push({
        type: 'session-expiry-warning',
        html: el.outerHTML.slice(0, 200),
        element_id: el.id || null,
        target: el.id ? [`#${CSS.escape(el.id)}`] : [el.tagName.toLowerCase()],
        tag: el.tagName.toUpperCase(),
        description: 'Session expiry indicator',
      });
    });

    // 4. Check for password reset forms (if data is lost, this is the workaround)
    const passwordResetForms = Array.from(forms).filter(form => {
      const formText = (form.textContent || '').toLowerCase();
      return /password\s*reset|reset\s*password|forgot\s*password|パスワードリセット|パスワードを再設定/i.test(formText);
    });

    // 5. Check for "session expired" messages
    const sessionExpiredMessages = document.querySelectorAll('.session-expired, .session-expired-message, [data-session-expired]');
    sessionExpiredMessages.forEach(el => {
      issues.push({
        type: 'session-expired-message',
        html: el.outerHTML.slice(0, 200),
        element_id: el.id || null,
        target: el.id ? [`#${CSS.escape(el.id)}`] : [el.tagName.toLowerCase()],
        tag: el.tagName.toUpperCase(),
        description: 'Session expired message',
      });
    });

    return {
      loginFormCount: loginForms.length,
      hasPasswordReset: passwordResetForms.length > 0,
      issues,
    };
  });

  if (data.loginFormCount === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: FALLBACK_DESCRIPTION,
        impact: null,
        status: 'not_applicable',
        reason: _t(sharedContext, 'No login/re-authentication forms detected on this page.', 'このページにログイン/再認証フォームは検出されませんでした。'),
        helpUrl: HELP_URL,
      }],
    };
  }

  if (data.issues.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: FALLBACK_DESCRIPTION,
        impact: null,
        status: 'pass',
        reason: _t(
          sharedContext,
          '{count} login/re-authentication form(s) checked — all appear to have data preservation mechanisms (return URLs, state fields, or persistence).',
          '{count} 件のログイン/再認証フォームを確認しました — すべてにデータ保存の仕組み（リダイレクトURL、状態フィールド、永続化）があります。',
          { count: data.loginFormCount },
        ),
        helpUrl: HELP_URL,
      }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'serious',
      status: 'needs_review',
      reason: _t(
        sharedContext,
        '{count} re-authentication issue(s) detected. Users must be able to continue their activity without data loss after re-authenticating. Manual review required to verify data preservation.',
        '{count} 件の再認証問題を検出しました。ユーザーは再認証後、データを失うことなく活動を継続できる必要があります。データ保存を手動で確認する必要があります。',
        { count: data.issues.length },
      ),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };