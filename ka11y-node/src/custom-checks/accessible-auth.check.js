'use strict';

const SC = '3.3.8';
const RULE_ID = 'custom-accessible-auth';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/accessible-authentication-minimum';

async function run(page) {
  const data = await page.evaluate(() => {
    const forms = Array.from(document.querySelectorAll('form'));
    const authForms = forms.filter(form => {
      const hasPassword = !!form.querySelector('input[type="password"]');
      const text = (form.textContent || '').toLowerCase();
      const isLoginLike = /\b(log\s*in|sign\s*in|login|signin|authenticate|username|email\s+address|create\s+account|register|forgot\s+password)\b/.test(text);
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
      const hasReCaptcha = !!(
        document.querySelector('iframe[src*="recaptcha" i], [class*="g-recaptcha" i], [data-sitekey]') ||
        // hCaptcha
        document.querySelector('[class*="h-captcha" i], [data-hcaptcha-widget-id]')
      );
      const hasAnyCaptcha = hasCaptchaImg || hasReCaptcha;

      // Bug fix: Expanded audio alternative detection
      const hasCaptchaAlt = !!(
        // Standard audio CAPTCHA button/link
        document.querySelector('[class*="captcha-audio" i], [id*="audio-captcha" i]') ||
        document.querySelector('button[aria-label*="audio" i], a[aria-label*="audio" i]') ||
        // reCAPTCHA's built-in audio button (class is obfuscated but aria-label is stable)
        document.querySelector('[title*="audio" i][title*="captcha" i]') ||
        // Links offering alternative text/audio
        Array.from(document.querySelectorAll('a, button')).some(el => {
          const text = (el.textContent || '').trim().toLowerCase();
          const label = (el.getAttribute('aria-label') || '').toLowerCase();
          return /audio|can.?t\s+read|different\s+image|refresh\s+captcha|alternative|try\s+another/i.test(text + label);
        })
      );

      // 2. Check if password field blocks copy-paste (inline attribute only — addEventListener not detectable)
      const passwordField = form.querySelector('input[type="password"]');
      let blocksCopyPaste = false;
      if (passwordField) {
        const onPaste = passwordField.getAttribute('onpaste') || '';
        const onCopy  = passwordField.getAttribute('oncopy') || '';
        // Bug fix: check for any variation of blocking patterns
        blocksCopyPaste = /return\s+false|preventDefault|false/i.test(onPaste + onCopy);
      }

      // 3. Cognitive function tests (expanded patterns)
      const formText = (form.textContent || '').toLowerCase();
      const hasCognitiveTest = /what\s+is\s+\d+\s*[\+\-\*×÷]\s*\d+|solve\s+the\s+(puzzle|equation|problem)|enter\s+the\s+(word|text|code|letters?|numbers?)\s+(you\s+see|shown|above|below|in\s+the\s+(image|picture))|answer\s+the\s+(question|challenge)|what\s+(color|colour|shape)\s+is/i.test(formText);

      if (hasAnyCaptcha && !hasCaptchaAlt) {
        issues.push({
          type: 'captcha-no-alternative',
          detail: `CAPTCHA detected (${hasReCaptcha ? 'reCAPTCHA/hCaptcha' : 'image CAPTCHA'}) without a detectable audio or accessible alternative.`,
        });
      }
      if (blocksCopyPaste) {
        issues.push({
          type: 'paste-blocked',
          detail: 'Password field has inline onpaste/oncopy handler that blocks pasting, preventing use of password managers.',
        });
      }
      if (hasCognitiveTest) {
        issues.push({
          type: 'cognitive-test',
          detail: 'Authentication appears to require solving a cognitive puzzle (math, riddle, or visual challenge) without a detectable accessible alternative.',
        });
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
        reason: 'No authentication forms detected on this page.',
        helpUrl: HELP_URL,
      }],
    };
  }

  if (data.issues.length > 0) {
    const issueTexts = data.issues.map(i => i.detail).join(' ');
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Authentication must not rely solely on cognitive function tests',
        impact: 'serious',
        status: 'fail',
        reason: `${data.authFormCount} authentication form(s) found with issues: ${issueTexts}`,
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
      reason: `${data.authFormCount} authentication form(s) found — no CAPTCHA-without-alternative, paste-blocking, or cognitive-test issues detected.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run };