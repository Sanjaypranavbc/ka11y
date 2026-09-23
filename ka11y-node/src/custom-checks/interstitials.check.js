'use strict';

const {
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '2.2.4';
const RULE_ID = 'custom-interstitials';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/interruptions';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Interruptions can be postponed or suppressed by the user, except for interruptions involving an emergency';

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);

  const data = await page.evaluate(() => {
    const issues = [];
    // G75 / SCR14: can the user postpone, dismiss or suppress the interruption?
    const DISMISS_RE = /close|dismiss|later|remind\s+me|not\s+now|no\s+thanks|skip|maybe\s+later|got\s+it|ok(?:ay)?|accept|reject|decline|continue|閉じる|後で|あとで|今はしない|スキップ|同意|拒否|了解|×|✕/i;
    const SUPPRESS_RE = /don'?t\s+show|do\s+not\s+show|never\s+show|stop\s+showing|hide\s+these|今後表示しない|表示しない/i;
    const controlLabel = (el) => [el.textContent || '', el.getAttribute('aria-label') || '', el.getAttribute('title') || '',
      ...Array.from(el.querySelectorAll('svg title, img[alt]')).map(x => x.getAttribute('alt') || x.textContent || '')].join(' ');
    const dismissInfo = (el) => {
      const controls = Array.from(el.querySelectorAll('button, [role="button"], a[href], input[type="button"], input[type="submit"], summary'));
      const hasDismissControl = controls.some(c => DISMISS_RE.test(controlLabel(c)) || c.hasAttribute('data-dismiss') || c.hasAttribute('data-bs-dismiss') || /close|dismiss/i.test(c.className || ''))
        || el.hasAttribute('data-escape-close') || (el.tagName.toLowerCase() === 'dialog');
      const hasSuppressOption = Array.from(el.querySelectorAll('input[type="checkbox"], label, button')).some(c => SUPPRESS_RE.test(controlLabel(c)));
      return { hasDismissControl, hasSuppressOption };
    };

    // 1. Check for modal dialogs/popups that auto-open
    const autoOpenModals = document.querySelectorAll('[role="dialog"]:not([aria-modal="false"]):not([open="false"]):not([data-manual-open])');
    autoOpenModals.forEach(el => {
      issues.push({
        ...dismissInfo(el),
        type: 'auto-open-modal',
        html: el.outerHTML.slice(0, 200),
        element_id: el.id || null,
        target: el.id ? [`#${CSS.escape(el.id)}`] : ['dialog'],
        tag: 'DIALOG',
        description: el.textContent?.slice(0, 100) || 'Modal dialog',
      });
    });

    // 2. Check for cookie consent banners that auto-appear
    const cookieBanners = document.querySelectorAll('[role="dialog"][aria-label*="cookie"], [role="alertdialog"][aria-label*="cookie"], .cookie-banner, #cookie-consent, #onetrust-banner-sdk');
    cookieBanners.forEach(el => {
      issues.push({
        ...dismissInfo(el),
        type: 'cookie-banner',
        html: el.outerHTML.slice(0, 200),
        element_id: el.id || null,
        target: el.id ? [`#${CSS.escape(el.id)}`] : ['div'],
        tag: 'DIV',
        description: 'Cookie consent banner',
      });
    });

    // 3. Check for interstitial ads between pages
    const interstitials = document.querySelectorAll('.interstitial, .ad-overlay, .page-overlay, #interstitial, .between-pages');
    interstitials.forEach(el => {
      issues.push({
        ...dismissInfo(el),
        type: 'interstitial-ad',
        html: el.outerHTML.slice(0, 200),
        element_id: el.id || null,
        target: el.id ? [`#${CSS.escape(el.id)}`] : ['div'],
        tag: 'DIV',
        description: 'Interstitial ad',
      });
    });

    // 4. Check for notification/toast messages
    const notifications = document.querySelectorAll('.notification, .toast, [role="status"][aria-live="polite"], .alert-toast, .snackbar');
    notifications.forEach(el => {
      issues.push({
        type: 'notification-toast',
        html: el.outerHTML.slice(0, 200),
        element_id: el.id || null,
        target: el.id ? [`#${CSS.escape(el.id)}`] : ['div'],
        tag: 'DIV',
        description: 'Notification/toast message',
      });
    });

    // 5. Check for loading spinners/overlays that block interaction
    const loadingOverlays = document.querySelectorAll('.loading-overlay, .spinner-overlay, #loading, [data-loading], .modal-backdrop[aria-hidden="false"]');
    loadingOverlays.forEach(el => {
      issues.push({
        type: 'loading-overlay',
        html: el.outerHTML.slice(0, 200),
        element_id: el.id || null,
        target: el.id ? [`#${CSS.escape(el.id)}`] : ['div'],
        tag: 'DIV',
        description: 'Loading overlay',
      });
    });

    // 6. Check for focus-trapping modals without escape key hint
    const focusTrapped = document.querySelectorAll('[role="dialog"]:not([data-escape-close]):not([aria-modal="false"])');
    focusTrapped.forEach(el => {
      const hasEscapeHandler = el.hasAttribute('data-escape-close');
      issues.push({
        ...dismissInfo(el),
        type: 'focus-trapped-modal',
        html: el.outerHTML.slice(0, 200),
        element_id: el.id || null,
        target: el.id ? [`#${CSS.escape(el.id)}`] : ['dialog'],
        tag: 'DIALOG',
        hasEscapeKey: hasEscapeHandler,
      });
    });

    return { issues };
  });

  if (data.issues.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: FALLBACK_DESCRIPTION,
        impact: null,
        status: 'pass',
        reason: _t(sharedContext, 'No disruptive interruptions detected.', 'ユーザーが抑制または遅延させられない中断は検出されませんでした。'),
        helpUrl: HELP_URL,
      }],
    };
  }

  // G75 / SCR14: interruptions that expose a dismiss/postpone control (or a "don't show again"
  // option) can be postponed or suppressed by the user → they satisfy the criterion.
  const interruptions = data.issues.filter(i => i.type !== 'loading-overlay' && i.type !== 'notification-toast');
  const lackingDismiss = interruptions.filter(i => !(i.hasDismissControl || i.hasSuppressOption));
  if (interruptions.length > 0 && lackingDismiss.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: FALLBACK_DESCRIPTION,
        impact: null,
        status: 'pass',
        reason: _t(
          sharedContext,
          '{count} interruption(s) detected and every one offers a dismiss, postpone or "don\'t show again" control (G75/SCR14).',
          '{count} 件の中断が検出されましたが、すべてに閉じる・後で・今後表示しないの操作があります（G75/SCR14）。',
          { count: interruptions.length },
        ),
        helpUrl: HELP_URL,
      }],
    };
  }
  if (lackingDismiss.length > 0) {
    // Only report the ones the user cannot dismiss.
    data.issues = data.issues.filter(i => lackingDismiss.includes(i) || i.type === 'loading-overlay' || i.type === 'notification-toast');
  }

  // Categorize the issues
  const dismissible = data.issues.filter(i => i.type !== 'cookie-banner' && i.type !== 'loading-overlay' && i.type !== 'notification-toast');
  const cookieLike = data.issues.filter(i => i.type === 'cookie-banner');

  if (dismissible.length > 0 && cookieLike.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: FALLBACK_DESCRIPTION,
        impact: 'moderate',
        status: 'needs_review',
        reason: _t(
          sharedContext,
          '{count} disruptive interruption(s) detected. Interruptions must be dismissible, postponable, or suppressible by the user except for emergencies. Manual review required.',
          '{count} 件の中断が検出されました。中断は、緊急事態を除き、ユーザーによって抑制、遅延、または dismiss できる必要があります。手動確認が必要です。',
          { count: dismissible.length },
        ),
        elements: dismissible,
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
      impact: 'moderate',
      status: 'needs_review',
      reason: _t(
        sharedContext,
        '{count} interruption(s) detected ({types}). Must be dismissible/postponable by user except for emergencies.',
        '{count} 件の中断を検出しました ({types})。緊急事態を除き、ユーザーによって遅延または抑制できる必要があります。',
        { count: data.issues.length, types: allTypes },
      ),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };