'use strict';

const {
  buildKeywordPattern,
  getKeywordList,
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '3.3.8';
const RULE_ID = 'custom-accessible-auth';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/accessible-authentication-minimum';

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);
  
  const loginFormPattern = buildKeywordPattern(
    getKeywordList('accessible_auth', 'login_form_keywords', sharedContext)
  );

  const captchaAltPattern = buildKeywordPattern(
    getKeywordList('accessible_auth', 'captcha_alt_keywords', sharedContext)
  );

  const cognitiveTestPattern = buildKeywordPattern(
    getKeywordList('accessible_auth', 'cognitive_test_keywords', sharedContext)
  );

  const data = await page.evaluate((loginFormReStr, captchaAltReStr, cognitiveTestReStr) => {
    const loginFormRe = new RegExp(`\\b(${loginFormReStr})\\b|${loginFormReStr}`, 'i');
    const captchaAltRe = new RegExp(captchaAltReStr, 'i');
    const cognitiveTestRe = new RegExp(cognitiveTestReStr, 'i');

    const forms = Array.from(document.querySelectorAll('form'));
    const authForms = forms.filter(form => {
      const hasPassword = !!form.querySelector('input[type="password"]');
      const text = (form.textContent || '').toLowerCase();
      const isLoginLike = loginFormRe.test(text);
      return hasPassword || isLoginLike;
    });

    if (authForms.length === 0) return { hasAuthForm: false, authFormCount: 0, issues: [] };

    const issues = [];

    for (const form of authForms) {
      // 1. Detect CAPTCHA presence
      const hasCaptchaImg = !!(
        form.querySelector('img[src*="captcha" i], img[alt*="captcha" i]') ||
        form.querySelector('[class*="captcha" i], [id*="captcha" i]')
      );
      // N10 fix: require multiple independent signals before flagging reCAPTCHA/hCaptcha.
      // [data-sitekey] alone is too broad — it's used by many non-CAPTCHA widgets.
      // Require either a recognisable CAPTCHA class/iframe OR data-sitekey combined with class context.
      const hasReCaptcha = !!(
        document.querySelector('iframe[src*="recaptcha" i]') ||
        document.querySelector('[class*="g-recaptcha" i]') ||
        document.querySelector('[data-sitekey][class*="captcha" i], [data-sitekey][class*="recaptcha" i]') ||
        // hCaptcha
        document.querySelector('[class*="h-captcha" i], [data-hcaptcha-widget-id]') ||
        document.querySelector('[data-sitekey][class*="hcaptcha" i]')
      );
      // Cloudflare Turnstile
      const hasTurnstile = !!document.querySelector('.cf-turnstile, [data-cf-turnstile]');
      const hasAnyCaptcha = hasCaptchaImg || hasReCaptcha || hasTurnstile;

      // Bug fix: Expanded audio alternative detection
      const hasCaptchaAlt = !!(
        // Standard audio CAPTCHA button/link
        document.querySelector('[class*="captcha-audio" i], [id*="audio-captcha" i]') ||
        document.querySelector('button[aria-label*="audio" i], a[aria-label*="audio" i], button[aria-label*="音声" i], a[aria-label*="音声" i]') ||
        // reCAPTCHA's built-in audio button (class is obfuscated but aria-label is stable)
        document.querySelector('[title*="audio" i][title*="captcha" i], [title*="音声" i]') ||
        // Links offering alternative text/audio
        Array.from(document.querySelectorAll('a, button')).some(el => {
          const text = (el.textContent || '').trim().toLowerCase();
          const label = (el.getAttribute('aria-label') || '').toLowerCase();
          return captchaAltRe.test(text + label);
        })
      );

      // 2. Check if password field blocks copy-paste.
      // B20: addEventListener-based paste blocking (the most common production pattern in
      // React/Vue/Angular apps) is invisible to getAttribute('onpaste'). Fix: dispatch a
      // synthetic cancelable paste event and check whether it was defaultPrevented.
      // This detects both inline onpaste attributes AND addEventListener('paste', ...) handlers.
      const passwordField = form.querySelector('input[type="password"]');
      let blocksCopyPaste = false;
      if (passwordField) {
        const onPaste = passwordField.getAttribute('onpaste') || '';
        const onCopy  = passwordField.getAttribute('oncopy') || '';
        const inlineBlocks = /return\s+false|preventDefault|false/i.test(onPaste + onCopy);
        // Dispatch a synthetic paste event and see if it's cancelled
        const testEvent = new ClipboardEvent('paste', { bubbles: true, cancelable: true });
        passwordField.dispatchEvent(testEvent);
        blocksCopyPaste = inlineBlocks || testEvent.defaultPrevented;
      }

      // 3. Cognitive function tests (expanded patterns)
      const formText = (form.textContent || '').toLowerCase();
      const hasCognitiveTest = cognitiveTestRe.test(formText);

      // Passkey/WebAuthn alternative detection
      const hasPasskeyOption = Array.from(document.querySelectorAll('button, a')).some(el =>
        /passkey|webauthn|biometric|fingerprint|face\s*id/i.test(el.textContent + (el.getAttribute('aria-label') || ''))
      );

      let formHasIssue = false;

      if (hasAnyCaptcha && !hasCaptchaAlt && !hasPasskeyOption) {
        issues.push({
          type: 'captcha-no-alternative',
          provider: hasTurnstile ? 'Cloudflare Turnstile' : hasReCaptcha ? 'reCAPTCHA/hCaptcha' : 'image CAPTCHA',
          html: form.outerHTML.slice(0, 150),
          element_id: form.id || null,
          target: form.id ? [`form#${CSS.escape(form.id)}`] : ['form'],
          tag: 'FORM',
        });
        formHasIssue = true;
      }
      // If a passkey/WebAuthn option is available it provides an accessible authentication
      // alternative — skip paste-blocking and cognitive-test issues for this form.
      if (!hasPasskeyOption) {
        if (blocksCopyPaste) {
          issues.push({
            type: 'paste-blocked',
            html: form.outerHTML.slice(0, 150),
            element_id: form.id || null,
            target: form.id ? [`form#${CSS.escape(form.id)}`] : ['form'],
            tag: 'FORM',
          });
          formHasIssue = true;
        }
        if (hasCognitiveTest && !formHasIssue) {
          issues.push({
            type: 'cognitive-test',
            html: form.outerHTML.slice(0, 150),
            element_id: form.id || null,
            target: form.id ? [`form#${CSS.escape(form.id)}`] : ['form'],
            tag: 'FORM',
          });
        }
      }
    }

    return { hasAuthForm: true, authFormCount: authForms.length, issues };
  }, loginFormPattern, captchaAltPattern, cognitiveTestPattern);

  if (!data.hasAuthForm) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Authentication must not rely solely on cognitive function tests',
        impact: null,
        status: 'pass',
        reason: _t(sharedContext, 'No authentication forms detected on this page.', 'このページでは認証フォームは検出されませんでした。'),
        helpUrl: HELP_URL,
      }],
    };
  }

  if (data.issues.length > 0) {
    const issueTexts = data.issues.map((issue) => {
      switch (issue.type) {
        case 'captcha-no-alternative':
          return _t(sharedContext, 'CAPTCHA detected ({provider}) without a detectable audio or accessible alternative.', 'CAPTCHA（{provider}）が検出されましたが、判別可能な音声またはアクセシブルな代替手段が見つかりません。', { provider: issue.provider || 'CAPTCHA' });
        case 'paste-blocked':
          return _t(sharedContext, 'Password field blocks pasting, preventing the use of password managers.', 'パスワード欄で貼り付けが禁止されており、パスワードマネージャーを利用できません。');
        case 'cognitive-test':
          return _t(sharedContext, 'Authentication appears to require solving a cognitive puzzle (math, riddle, or visual challenge) without a detectable accessible alternative.', '認証時に計算・なぞなぞ・視覚的チャレンジなどの認知課題が必要なように見えますが、判別可能なアクセシブルな代替手段が見つかりません。');
        default:
          return _t(sharedContext, 'Authentication issue detected.', '認証に関する問題が検出されました。');
      }
    }).join(' ');
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Authentication must not rely solely on cognitive function tests',
        impact: 'serious',
        status: 'fail',
        reason: _t(sharedContext, '{count} authentication form(s) found with issues: {issues}', '問題のある認証フォームが {count} 件見つかりました: {issues}', { count: data.authFormCount, issues: issueTexts }),
        elements: data.issues,
        helpUrl: HELP_URL,
      }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Authentication must not rely solely on cognitive function tests',
      impact: null,
      status: 'pass',
      reason: _t(sharedContext, '{count} authentication form(s) found — no CAPTCHA-without-alternative, paste-blocking, or cognitive-test issues detected.', '認証フォームが {count} 件見つかりましたが、代替手段のない CAPTCHA、貼り付け禁止、認知課題の問題は検出されませんでした。', { count: data.authFormCount }),
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
