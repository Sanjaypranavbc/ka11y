'use strict';

const {
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '2.2.3';
const RULE_ID = 'custom-no-timing';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/no-timing';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Timing is not an essential part of the event or activity presented by the content, except for non-interactive synchronized media and real-time events';

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);

  const data = await page.evaluate(() => {
    const issues = [];

    // 1. Check for meta refresh redirects
    const metaRefresh = document.querySelector('meta[http-equiv="refresh"]');
    if (metaRefresh) {
      const content = metaRefresh.getAttribute('content') || '';
      const match = content.match(/^\s*(\d+)\s*;?\s*url=/i);
      const delay = match ? parseInt(match[1], 10) : null;
      issues.push({
        type: 'meta-refresh',
        html: metaRefresh.outerHTML.slice(0, 200),
        element_id: metaRefresh.id || null,
        target: ['meta[http-equiv="refresh"]'],
        tag: 'META',
        delaySeconds: delay,
      });
    }

    // 2. Check for JavaScript-based timeouts (setTimeout, setInterval)
    // We can't see the JS code directly, but we can check for common patterns in attributes
    const elementsWithTimeouts = document.querySelectorAll('[data-timeout], [data-countdown], [data-session-timeout], [data-auto-logout]');
    elementsWithTimeouts.forEach(el => {
      issues.push({
        type: 'js-timeout-indicator',
        html: el.outerHTML.slice(0, 200),
        element_id: el.id || null,
        target: el.id ? [`#${CSS.escape(el.id)}`] : [el.tagName.toLowerCase()],
        tag: el.tagName.toUpperCase(),
        attributes: Array.from(el.attributes).map(a => `${a.name}="${a.value}"`).join(' '),
      });
    });

    // 3. Check for form inputs that suggest timing (session expiry, countdown timers)
    const timerElements = document.querySelectorAll('[aria-live="assertive"][role="timer"], [role="timer"], .countdown, .timer, .session-timeout, .session-warning');
    timerElements.forEach(el => {
      issues.push({
        type: 'visible-timer',
        html: el.outerHTML.slice(0, 200),
        element_id: el.id || null,
        target: el.id ? [`#${CSS.escape(el.id)}`] : [el.tagName.toLowerCase()],
        tag: el.tagName.toUpperCase(),
      });
    });

    // 4. Check for real-time content (auctions, live games, etc.)
    const realTimeIndicators = document.querySelectorAll('[data-live], [data-realtime], [data-auction], .live-auction, .real-time-bidding, .timer-auction');
    realTimeIndicators.forEach(el => {
      issues.push({
        type: 'realtime-content',
        html: el.outerHTML.slice(0, 200),
        element_id: el.id || null,
        target: el.id ? [`#${CSS.escape(el.id)}`] : [el.tagName.toLowerCase()],
        tag: el.tagName.toUpperCase(),
      });
    });

    // 5. Check for media with time-based restrictions
    const timedMedia = Array.from(document.querySelectorAll('audio, video')).filter(el => {
      const hasTimeLimit = el.hasAttribute('data-time-limit') || el.hasAttribute('data-max-duration');
      const hasExpiry = /expire|expiry|valid\s+for|available\s+until/i.test(el.getAttribute('aria-label') || '');
      return hasTimeLimit || hasExpiry;
    });
    timedMedia.forEach(el => {
      issues.push({
        type: 'timed-media',
        html: el.outerHTML.slice(0, 200),
        element_id: el.id || null,
        target: el.id ? [`${el.tagName.toLowerCase()}#${CSS.escape(el.id)}`] : [el.tagName.toLowerCase()],
        tag: el.tagName.toUpperCase(),
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
        reason: _t(sharedContext, 'No time limits or timing-dependent content detected.', '時間制限や時間依存のコンテンツは検出されませんでした。'),
        helpUrl: HELP_URL,
      }],
    };
  }

  // Classify issues: some may be essential timing (real-time events, live media)
  const essentialTiming = data.issues.filter(i => i.type === 'realtime-content' || i.type === 'timed-media');
  const nonEssentialTiming = data.issues.filter(i => i.type !== 'realtime-content' && i.type !== 'timed-media');

  if (essentialTiming.length > 0 && nonEssentialTiming.length === 0) {
    // Only essential timing found - this is allowed
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: FALLBACK_DESCRIPTION,
        impact: null,
        status: 'pass',
        reason: _t(
          sharedContext,
          'Only essential timing content detected (live events, synchronized media). Timing is permitted for real-time events.',
          '必須のタイミングコンテンツのみ検出されました（ライブイベント、同期メディア）。リアルタイムイベントではタイミングが許可されています。',
        ),
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
        '{count} timing-related issue(s) detected ({types}). Timing must not be essential unless content is real-time events or synchronized media. Manual review required to determine if time limits are essential.',
        '{count} 件のタイミング関連問題を検出しました ({types})。タイミングは、リアルタイムイベントまたは同期メディアでない限り必須であってはなりません。時間制限が必須かどうか手動確認が必要です。',
        { count: data.issues.length, types: allTypes },
      ),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };