'use strict';

const {
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '2.2.6';
const RULE_ID = 'custom-session-timeouts';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/timeouts';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Users are warned of the duration of any user inactivity that could cause data loss, unless the data is preserved for more than 20 hours';

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);

  const data = await page.evaluate(() => {
    const issues = [];

    // 1. Check for session timeout indicators without proper warning
    const timeoutIndicators = document.querySelectorAll(
      '[data-session-timeout], .session-timeout, .auto-logout, .expire-session, .session-expire, [data-timeout], .timeout-warning'
    );

    timeoutIndicators.forEach(el => {
      const hasNoWarning = !el.hasAttribute('data-warning-time') &&
                           !el.hasAttribute('data-timeout-warning') &&
                           !el.querySelector('.timeout-warning, .session-warning, .countdown') &&
                           !el.textContent?.toLowerCase().includes('warning') &&
                           !el.textContent?.toLowerCase().includes('expir') &&
                           !el.textContent?.toLowerCase().includes('remaining');

      if (hasNoWarning) {
        issues.push({
          html: el.outerHTML.slice(0, 200),
          element_id: el.id || null,
          target: el.id ? [`#${CSS.escape(el.id)}`] : [el.tagName.toLowerCase()],
          tag: el.tagName.toUpperCase(),
          hasWarningText: false,
        });
      }
    });

    // 2. Check for cookie/session storage that persists data > 20 hours
    // Look for indicators of long-term data preservation
    const persistenceIndicators = document.querySelectorAll('[data-persist-duration], [data-save-duration], .long-persistence, .extended-save');
    const hasLongTermPersistence = persistenceIndicators.length > 0;

    // 3. Check for auth forms that would cause data loss
    const forms = document.querySelectorAll('form');
    const formsAtRisk = Array.from(forms).filter(form => {
      const formText = (form.textContent || '').toLowerCase();
      const isAuthForm = /log\s*in|sign\s*in|log\s*out|logout|password|authenticate/i.test(formText);
      const hasInput = form.querySelector('input, textarea, select');
      return isAuthForm && hasInput;
    });

    formsAtRisk.forEach(form => {
      const hasHiddenState = !!form.querySelector('input[type="hidden"][name*="state"], input[type="hidden"][name*="session"], input[type="hidden"][name*="token"]');
      const hasAutoSave = form.hasAttribute('data-auto-save') || form.hasAttribute('data-persist');
      if (!hasHiddenState && !hasAutoSave) {
        issues.push({
          type: 'auth-form-at-risk',
          html: form.outerHTML.slice(0, 200),
          element_id: form.id || null,
          target: form.id ? [`form#${CSS.escape(form.id)}`] : ['form'],
          tag: 'FORM',
          hasStatePreservation: hasHiddenState,
          hasAutoSave: hasAutoSave,
        });
      }
    });

    // 4. Check for session-expired messages (indicates timeout happening)
    const expiredMessages = document.querySelectorAll('.session-expired, .session-expired-message, .timeout-expired, .log-out, [data-session-expired]');
    expiredMessages.forEach(el => {
      issues.push({
        type: 'session-expired',
        html: el.outerHTML.slice(0, 200),
        element_id: el.id || null,
        target: el.id ? [`#${CSS.escape(el.id)}`] : [el.tagName.toLowerCase()],
        tag: el.tagName.toUpperCase(),
      });
    });

    return {
      issues,
      hasLongTermPersistence,
    };
  });

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
          'No session timeout issues detected. Users are warned of inactivity that could cause data loss.',
          'セッションのタイムアウトの問題は検出されませんでした。ユーザーは非活動によるデータ損失を警告されます。',
        ),
        helpUrl: HELP_URL,
      }],
    };
  }

  // Separate issues into different categories
  const timeoutWarnings = data.issues.filter(i => i.type !== 'auth-form-at-risk' && i.type !== 'session-expired');
  const authAtRisk = data.issues.filter(i => i.type === 'auth-form-at-risk');
  const expired = data.issues.filter(i => i.type === 'session-expired');

  if (timeoutWarnings.length > 0 && authAtRisk.length === 0 && expired.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: FALLBACK_DESCRIPTION,
        impact: 'moderate',
        status: 'needs_review',
        reason: _t(
          sharedContext,
          '{count} timeout warning issue(s) detected. Users must be warned of inactivity that could cause data loss at least 20 seconds before timeout.',
          '{count} 件のタイムアウト警告の問題を検 outしました。ユーザーは、データ損失を引き起こす前に少なくとも20秒の警告を受ける必要があります。',
          { count: timeoutWarnings.length },
        ),
        elements: timeoutWarnings,
        helpUrl: HELP_URL,
      }],
    };
  }

  const allTypes = [...new Set(data.issues.map(i => i.type))].join(', ');
  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'serious',
      status: 'needs_review',
      reason: _t(
        sharedContext,
        '{count} session timeout issue(s) detected ({types}). Users must be warned of inactivity that could cause data loss. Data must be preserved for at least 20 hours.',
        '{count} 件のセッションタイムアウトの問題を検出しました ({types})。ユーザーは、データ損失を引き起こす非活動について警告を受ける必要があります。データは少なくとも20時間保存される必要があります。',
        { count: data.issues.length, types: allTypes },
      ),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };