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

    // 5. Runtime timers (installed hook): long setTimeout/setInterval that look like session limits
    const R = window.__ka11yRuntime;
    const SESSION_RE = /logout|log_out|log-out|signout|sign_out|sign-out|expire|expir|session|timeout|time_out|idle|inactiv|redirect|location\.(?:href|replace|assign)|reload/i;
    const runtimeTimers = (R && Array.isArray(R.timers)) ? R.timers.filter(t =>
      (t.delay >= 60000 && SESSION_RE.test(t.snippet || '')) || t.delay >= 300000) : [];

    // 6. Controls that let the user extend / disable the limit (G198, SCR1, G180, G133)
    const EXTEND_RE = /extend|stay\s+(?:signed|logged)\s+in|keep\s+me\s+(?:signed|logged)\s+in|more\s+time|need\s+more\s+time|continue\s+session|remain\s+logged|延長|ログイン状態を保持|ログインしたままにする|セッションを継続|時間を延長/i;
    const controlText = (el) => ((el.textContent || '') + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('title') || '')).trim();
    const hasExtendControl = Array.from(document.querySelectorAll('button, a[href], [role="button"], input[type="button"], input[type="submit"]'))
      .some(el => EXTEND_RE.test(controlText(el)) || EXTEND_RE.test(el.getAttribute('value') || ''));
    const hasTimeExtensionCheckbox = Array.from(document.querySelectorAll('input[type="checkbox"]')).some(cb => {
      const lbl = (cb.id && document.querySelector(`label[for="${CSS.escape(cb.id)}"]`)) || cb.closest('label');
      return EXTEND_RE.test(((lbl && lbl.textContent) || '') + ' ' + (cb.getAttribute('aria-label') || ''));
    });

    for (const t of runtimeTimers.slice(0, 5)) {
      issues.push({
        type: 'js-timer-limit',
        html: `${t.kind}(fn, ${t.delay})`,
        element_id: null,
        target: [`${t.kind}(${t.delay}ms)`],
        tag: 'SCRIPT',
        delayMs: t.delay,
        snippet: (t.snippet || '').slice(0, 160),
        hasExtendControl,
        hasTimeExtensionCheckbox,
      });
    }

    return {
      issues,
      hasLongTermPersistence,
      runtimeTimerCount: runtimeTimers.length,
      hasExtendControl,
      hasTimeExtensionCheckbox,
    };
  });

  if (!data || typeof data !== 'object' || !Array.isArray(data.issues)) {
    return { successCriteriaId: SC, rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'pass', reason: _t(sharedContext, 'No session timeout issues detected.', 'セッションのタイムアウトの問題は検出されませんでした。'), helpUrl: HELP_URL }] };
  }

  // ── G198 / SCR16 / SCR1: a visible countdown (mm:ss decreasing between two snapshots) is a
  // live time limit regardless of markup; a dialog mentioning the session/timeout is the
  // warning (SCR16); an extend control must exist (SCR1/G198).
  let countdown = null;
  let warnDialog = false;
  try {
    const snap = () => page.evaluate(() => {
      const out = {}; let i = 0;
      for (const el of document.querySelectorAll('span, div, p, b, strong, time, output, td, em')) {
        if (i++ > 5000) break;
        if (el.children.length) continue;
        const t = (el.textContent || '').trim();
        if (t.length > 9) continue;
        const m = t.match(/^(?:(\d{1,2}):)?(\d{1,2}):(\d{2})$/);
        if (!m) continue;
        el.__ka11yCd = el.__ka11yCd || ('c' + i);
        out[el.__ka11yCd] = parseInt(m[1] || '0', 10) * 3600 + parseInt(m[2], 10) * 60 + parseInt(m[3], 10);
      }
      return out;
    });
    const a = await snap();
    if (a && typeof a === 'object' && !Array.isArray(a) && Object.keys(a).length) {
      await new Promise(r => setTimeout(r, 1300));
      const b = await snap();
      for (const [k, v] of Object.entries(a)) {
        if (b && b[k] !== undefined && b[k] < v && v - b[k] <= 3) { countdown = { seconds: b[k] }; break; }
      }
    }
    if (countdown) {
      warnDialog = !!(await page.evaluate(() => Array.from(document.querySelectorAll('[role="dialog"], [role="alertdialog"], dialog[open], [class*="modal" i], [aria-live]')).some(d => /session|timeout|time\s*out|expire|inactiv|log(?:ged)?\s*out|セッション|タイムアウト|有効期限|自動ログアウト/i.test(d.textContent || ''))));
      if (!data.hasExtendControl && !data.hasTimeExtensionCheckbox) {
        data.issues.push({
          type: 'countdown-no-extend',
          html: `countdown at ${countdown.seconds}s`,
          element_id: null,
          target: ['countdown'],
          tag: 'TIMER',
          delayMs: countdown.seconds * 1000,
          detail: `A visible countdown (${countdown.seconds}s remaining) is running with no control to extend, adjust or turn off the limit (G198/SCR1)${warnDialog ? '; a session warning message is shown (SCR16)' : '; no warning dialog/message detected (SCR16)'}`,
        });
      }
    }
  } catch (_) { /* best effort */ }

  // Runtime timers with an extend/keep-alive control present satisfy G198/SCR1 — drop them from the issue list.
  if (data.hasExtendControl || data.hasTimeExtensionCheckbox) {
    data.issues = data.issues.filter(i => i.type !== 'js-timer-limit');
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
          'No session timeout issues detected. Users are warned of inactivity that could cause data loss.',
          'セッションのタイムアウトの問題は検出されませんでした。ユーザーは非活動によるデータ損失を警告されます。',
        ),
        helpUrl: HELP_URL,
      }],
    };
  }

  // Separate issues into different categories
  const timeoutWarnings = data.issues.filter(i => i.type !== 'auth-form-at-risk' && i.type !== 'session-expired' && i.type !== 'js-timer-limit' && i.type !== 'countdown-no-extend');
  const authAtRisk = data.issues.filter(i => i.type === 'auth-form-at-risk');
  const expired = data.issues.filter(i => i.type === 'session-expired');
  const jsTimers = data.issues.filter(i => i.type === 'js-timer-limit' || i.type === 'countdown-no-extend');

  if (jsTimers.length > 0 && timeoutWarnings.length === 0 && authAtRisk.length === 0 && expired.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: FALLBACK_DESCRIPTION,
        impact: 'moderate',
        status: 'needs_review',
        reason: _t(
          sharedContext,
          '{count} time limit(s) detected at runtime ({kinds}; shortest ≈ {minutes} min), and no control to extend, disable or lengthen the limit was found on the page. Warn users before the limit and offer a way to extend it (G198, SCR1, SCR16).',
          '実行時に {count} 件の時間制限が検出されました（{kinds}、最短 約 {minutes} 分）。制限を延長・無効化する操作がページに見つかりません。制限前に警告し、延長手段を提供してください（G198、SCR1、SCR16）。',
          { count: jsTimers.length, kinds: [...new Set(jsTimers.map(t => t.type === 'countdown-no-extend' ? 'visible countdown' : 'script timer'))].join(', '), minutes: Math.max(1, Math.round(Math.min(...jsTimers.map(t => t.delayMs || 60000)) / 60000)) },
        ),
        elements: jsTimers,
        helpUrl: HELP_URL,
      }],
    };
  }

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