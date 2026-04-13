'use strict';

const {
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
  const data = await page.evaluate(() => {
    const forms = Array.from(document.querySelectorAll('form'));
    const authForms = forms.filter(form => {
      const hasPassword = !!form.querySelector('input[type="password"]');
      const text = (form.textContent || '').toLowerCase();
      const isLoginLike =
        /\b(log\s*in|sign\s*in|login|signin|authenticate|username|email\s+address|create\s+account|register|forgot\s+password)\b|ログイン|サインイン|認証|ユーザー名|メールアドレス|アカウント作成|新規登録|会員登録|パスワード|パスワードを忘れ|パスワード再設定/.test(text);
      return hasPassword || isLoginLike;
    });

    if (authForms.length === 0) return { hasAuthForm: false };

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
          return /audio|音声|can.?t\s+read|読み取れない|different\s+image|別の画像|refresh\s+captcha|画像を更新|alternative|別の方法|try\s+another|別の認証/i.test(text + label);
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
      const hasCognitiveTest =
        /what\s+is\s+\d+\s*[\+\-\*×÷]\s*\d+|solve\s+the\s+(puzzle|equation|problem)|enter\s+the\s+(word|text|code|letters?|numbers?)\s+(you\s+see|shown|above|below|in\s+the\s+(image|picture))|answer\s+the\s+(question|challenge)|what\s+(color|colour|shape)\s+is|\d+\s*[\+\-\*×÷]\s*\d+|計算|問題を解|パズル|クイズ|画像に表示|表示された文字|見える文字|質問に答|何色|どの色|どの形/i.test(formText);

      // Passkey/WebAuthn alternative detection
      const hasPasskeyOption = Array.from(document.querySelectorAll('button, a')).some(el =>
        /passkey|webauthn|biometric|fingerprint|face\s*id/i.test(el.textContent + (el.getAttribute('aria-label') || ''))
      );

      if (hasAnyCaptcha && !hasCaptchaAlt && !hasPasskeyOption) {
        issues.push({
          type: 'captcha-no-alternative',
          provider: hasTurnstile ? 'Cloudflare Turnstile' : hasReCaptcha ? 'reCAPTCHA/hCaptcha' : 'image CAPTCHA',
        });
      }
      // If a passkey/WebAuthn option is available it provides an accessible authentication
      // alternative — skip paste-blocking and cognitive-test issues for this form.
      if (!hasPasskeyOption) {
        if (blocksCopyPaste) {
          issues.push({
            type: 'paste-blocked',
          });
        }
        if (hasCognitiveTest) {
          issues.push({
            type: 'cognitive-test',
          });
        }
      }
    }

    return { hasAuthForm: true, authFormCount: authForms.length, issues };
  });

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
