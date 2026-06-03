'use strict';

const {
  buildKeywordPattern,
  getKeywordList,
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '4.1.3';
const RULE_ID = 'custom-status-messages';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/status-messages';

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);

  const searchResultPattern = buildKeywordPattern(
    getKeywordList('status_messages', 'search_result_keywords', sharedContext)
  ) || 'result|結果';

  const counterBadgePattern = buildKeywordPattern(
    getKeywordList('status_messages', 'counter_badge_keywords', sharedContext)
  ) || 'count|counter|notification|unread|新着|件|通知|未読';

  const cartPattern = buildKeywordPattern(
    getKeywordList('status_messages', 'cart_keywords', sharedContext)
  ) || 'cart|basket|カート|買い物かご';

  const notificationClassPattern = buildKeywordPattern(
    getKeywordList('status_messages', 'notification_class_keywords', sharedContext)
  ) || 'notification|toast|snackbar|flash|alert|banner|sonner|hot-toast|toastify';

  const data = await page.evaluate((searchResultReStr, counterBadgeReStr, cartReStr, notificationClassReStr) => {
    const searchResultRe = new RegExp(searchResultReStr, 'i');
    const counterBadgeRe = new RegExp(`\\b(${counterBadgeReStr})\\b|${counterBadgeReStr}`, 'i');
    const cartRe = new RegExp(cartReStr, 'i');
    const notificationClassRe = new RegExp(notificationClassReStr, 'i');

    const liveRegions = Array.from(document.querySelectorAll(
      '[aria-live], [role="status"], [role="alert"], [role="log"], [role="timer"], [role="marquee"]'
    ));

    const forms     = document.querySelectorAll('form');
    const formCount = forms.length;

    const hasAlerts = liveRegions.some(el =>
      el.getAttribute('role') === 'alert' ||
      el.getAttribute('aria-live') === 'assertive'
    );
    const hasPolite = liveRegions.some(el =>
      el.getAttribute('role') === 'status' ||
      el.getAttribute('aria-live') === 'polite'
    );

    // Bug fix: detect other dynamic-content contexts beyond forms
    // that would need status messages (search results, cart, notifications)
    const searchResultEls = Array.from(document.querySelectorAll('[role="region"], [aria-live], [id], [class]')).filter(el => {
      const label = el.getAttribute('aria-label') || '';
      const idStr = el.id || '';
      const classStr = typeof el.className === 'string' ? el.className : '';
      return searchResultRe.test(label) || searchResultRe.test(idStr) || searchResultRe.test(classStr);
    });
    const hasSearchResults = searchResultEls.length > 0;

    // B14: '[class*="badge" i]' was too broad
    const badgeEls = Array.from(document.querySelectorAll('[class*="badge" i]'));
    const counterBadgeEls = badgeEls.filter(el => {
      const text = (el.textContent || '').trim();
      const label = (el.getAttribute('aria-label') || '').toLowerCase();
      return /^\d+\+?$/.test(text) || counterBadgeRe.test(label);
    });
    const hasCounterBadge = counterBadgeEls.length > 0;

    const cartOrCounterEls = Array.from(document.querySelectorAll('[aria-label], [class]')).filter(el => {
      const label = el.getAttribute('aria-label') || '';
      const classStr = typeof el.className === 'string' ? el.className : '';
      return cartRe.test(label) || cartRe.test(classStr);
    });
    const combinedCartEls = [...new Set([...cartOrCounterEls, ...counterBadgeEls])];
    const hasCartOrCounter = combinedCartEls.length > 0;

    // FP fix: detect visual notification patterns only when they are NOT already
    // contained within an existing live region.
    const notificationCandidates = Array.from(document.querySelectorAll('[class]')).filter(el => {
      const classStr = typeof el.className === 'string' ? el.className : '';
      return classStr.trim().length > 0 &&
             notificationClassRe.test(classStr) &&
             !(/alert|banner/i.test(classStr) && el.hasAttribute('role'));
    });

    const toastLibCandidates = Array.from(document.querySelectorAll([
      '.Toastify__toast-container',
      '.Toastify',
      '[data-sonner-toaster]',
      '[data-sonner-toast]',
      '.sonner-toast',
      '.react-hot-toast',
      '[data-rht-toaster]',
      '[class*="toastify" i]',
      '[class*="hot-toast" i]',
      '[class*="sonner" i]',
    ].join(', ')));
    const combinedNotificationCandidates = [...new Set([...notificationCandidates, ...toastLibCandidates])];

    const notificationAreaEls = combinedNotificationCandidates.filter(el => {
      // Walk up ancestors to check if this element is already inside a live region
      let node = el;
      while (node && node !== document.body) {
        const role = node.getAttribute('role');
        const ariaLive = node.getAttribute('aria-live');
        if (role === 'status' || role === 'alert' || role === 'log' ||
            ariaLive === 'polite' || ariaLive === 'assertive') {
          return false; // already inside a live region — not a problem
        }
        node = node.parentElement;
      }
      return true; // notification element has no live region ancestor
    });
    const hasNotificationArea = notificationAreaEls.length > 0;
    const toastWithoutAria = notificationAreaEls.filter(el => {
      const classStr = typeof el.className === 'string' ? el.className : '';
      const dataAttrs = `${el.getAttribute('data-sonner-toast') || ''} ${el.getAttribute('data-sonner-toaster') || ''}`;
      const looksLikeToast = /toastify|toast|hot-toast|sonner/i.test(classStr) || dataAttrs.trim().length > 0;
      if (!looksLikeToast) return false;
      const ownRole = (el.getAttribute('role') || '').toLowerCase();
      const ownLive = (el.getAttribute('aria-live') || '').toLowerCase();
      return !['status', 'alert', 'log'].includes(ownRole) && ownLive === '';
    }).map(el => ({
      html: el.outerHTML.slice(0, 150),
      element_id: el.id || null,
      target: el.id ? [`#${CSS.escape(el.id)}`] : [el.tagName.toLowerCase()],
      tag: el.tagName.toUpperCase(),
    }));

    const needsLiveRegions = formCount > 0 || hasSearchResults || hasCartOrCounter || hasNotificationArea;

    const contextElements = [];
    for (const el of [...forms, ...searchResultEls, ...combinedCartEls, ...notificationAreaEls]) {
      contextElements.push({
        html: el.outerHTML.slice(0, 150),
        element_id: el.id || null,
        target: el.id ? [`#${CSS.escape(el.id)}`] : [el.tagName.toLowerCase()],
        tag: el.tagName.toUpperCase(),
      });
    }

    // Probe: check whether any live region already has text content at page-load time.
    // An empty live region (no content) has never been used yet — flag it as a signal
    // that the live regions may be structural placeholders not wired to actual updates.
    // Note: live regions that are correctly empty at load and populated on interaction
    // will appear as "no content", so this is informational, not a definitive fail.
    const anyLiveRegionHasContent = liveRegions.some(
      el => (el.textContent || '').trim().length > 0
    );

    // aria-atomic check: [role="alert"] or [aria-live="assertive"] missing aria-atomic="true"
    const alertsWithoutAtomic = Array.from(document.querySelectorAll(
      '[role="alert"], [aria-live="assertive"]'
    )).filter(el => el.getAttribute('aria-atomic') !== 'true').map(el => ({
      html: el.outerHTML.slice(0, 150),
      element_id: el.id || null,
      target: el.id ? [`#${CSS.escape(el.id)}`] : [el.tagName.toLowerCase()],
      tag: el.tagName.toUpperCase(),
    }));

    // Inline validation without live region ancestor
    const invalidWithoutLiveRegion = Array.from(document.querySelectorAll('[aria-invalid]')).filter(el => {
      let node = el.parentElement;
      while (node && node !== document.body) {
        const role = node.getAttribute('role');
        const ariaLive = node.getAttribute('aria-live');
        if (ariaLive || role === 'status' || role === 'alert' || role === 'log') return false;
        node = node.parentElement;
      }
      return true;
    }).map(el => ({
      html: el.outerHTML.slice(0, 150),
      element_id: el.id || null,
      target: el.id ? [`#${CSS.escape(el.id)}`] : [el.tagName.toLowerCase()],
      tag: el.tagName.toUpperCase(),
    }));

    return {
      liveRegionCount: liveRegions.length,
      formCount,
      hasAlerts,
      hasPolite,
      hasSearchResults,
      hasCartOrCounter,
      hasNotificationArea,
      needsLiveRegions,
      anyLiveRegionHasContent,
      alertsWithoutAtomic,
      invalidWithoutLiveRegion,
      toastWithoutAria,
      contextElements,
    };
  }, searchResultPattern, counterBadgePattern, cartPattern, notificationClassPattern);

  const { liveRegionCount, formCount, hasAlerts, hasPolite, hasSearchResults, hasCartOrCounter, hasNotificationArea, needsLiveRegions, anyLiveRegionHasContent, alertsWithoutAtomic = [], invalidWithoutLiveRegion = [], toastWithoutAria = [], contextElements = [] } = data;
  const dynamicContexts = [
    formCount > 0 && _t(sharedContext, '{count} form(s)', 'フォーム {count} 件', { count: formCount }),
    hasSearchResults && _t(sharedContext, 'search results', '検索結果'),
    hasCartOrCounter && _t(sharedContext, 'cart/counter', 'カート/カウンター'),
    hasNotificationArea && _t(sharedContext, 'notification area', '通知領域'),
  ].filter(Boolean);

  // Build extra INCOMPLETE rules for aria-atomic and inline validation issues
  const extraRules = [];
  if (alertsWithoutAtomic.length > 0) {
    extraRules.push({
      ruleId: `${RULE_ID}-atomic`,
      description: 'Status messages must be programmatically determinable',
      impact: null,
      status: 'incomplete',
      reason: _t(sharedContext, '{count} [role="alert"] or [aria-live="assertive"] element(s) are missing aria-atomic="true". Without aria-atomic, only changed portions may be announced rather than the full message.', '[role="alert"] または [aria-live="assertive"] 要素 {count} 件に aria-atomic="true" がありません。aria-atomic がないと、完全なメッセージではなく変更部分だけが読み上げられる可能性があります。', { count: alertsWithoutAtomic.length }),
      elements: alertsWithoutAtomic,
      helpUrl: HELP_URL,
    });
  }
  if (invalidWithoutLiveRegion.length > 0) {
    extraRules.push({
      ruleId: `${RULE_ID}-inline-validation`,
      description: 'Status messages must be programmatically determinable',
      impact: null,
      status: 'incomplete',
      reason: _t(sharedContext, '{count} [aria-invalid] element(s) have no live region ancestor (aria-live, role="status/alert/log"). Inline validation errors may not be announced to screen reader users.', '[aria-invalid] 要素 {count} 件にライブリージョンの祖先（aria-live、role="status/alert/log"）がありません。インラインの入力検証エラーがスクリーンリーダー利用者に通知されない可能性があります。', { count: invalidWithoutLiveRegion.length }),
      elements: invalidWithoutLiveRegion,
      helpUrl: HELP_URL,
    });
  }
  if (toastWithoutAria.length > 0) {
    extraRules.push({
      ruleId: `${RULE_ID}-toast`,
      description: 'Status messages must be programmatically determinable',
      impact: null,
      status: 'incomplete',
      reason: _t(sharedContext, '{count} toast/notification container(s) appear without role="status"/"alert"/"log" or aria-live. These status updates may not be announced to screen readers (F114 risk).', 'role="status"/"alert"/"log" または aria-live を持たないトースト/通知コンテナが {count} 件見つかりました。これらの状態更新はスクリーンリーダーに通知されない可能性があります（F114 のリスク）。', { count: toastWithoutAria.length }),
      elements: toastWithoutAria,
      helpUrl: HELP_URL,
    });
  }


  // Page has dynamic contexts but no live regions at all → clear fail
  if (needsLiveRegions && liveRegionCount === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Status messages must be programmatically determinable',
        impact: 'serious',
        status: 'fail',
        reason: _t(sharedContext, 'Dynamic content contexts detected ({contexts}) but no ARIA live regions found. Validation errors and status updates will not be announced to screen readers.', '動的コンテンツの文脈（{contexts}）が検出されましたが、ARIA ライブリージョンが見つかりません。入力エラーや状態更新がスクリーンリーダーに通知されません。', { contexts: dynamicContexts.join(', ') }),
        elements: contextElements,
        helpUrl: HELP_URL,
      }, ...extraRules],
    };
  }

  // Dynamic contexts exist AND live regions exist → needs_review (can't verify coverage statically).
  // Add an informational note about whether any live region had text content at page load —
  // all-empty live regions may be structural placeholders that are never written to.
  if (needsLiveRegions && liveRegionCount > 0) {
    const contentNote = anyLiveRegionHasContent
      ? _t(sharedContext, 'At least one live region contains text at page load.', '少なくとも 1 つのライブリージョンには、ページ読み込み時点でテキストが含まれています。')
      : _t(sharedContext, 'All live regions are empty at page load — confirm they are populated on status updates at runtime.', 'ページ読み込み時点では、すべてのライブリージョンが空です。実行時の状態更新で内容が設定されることを確認してください。');
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: 'Status messages must be programmatically determinable', impact: null, status: 'incomplete', reason: _t(sharedContext, '{count} ARIA live region(s) found (assertive: {has_alerts}, polite: {has_polite}) alongside dynamic contexts ({contexts}). {content_note} Verify live regions are correctly wired to each status update.', 'ARIA ライブリージョンが {count} 件見つかりました（assertive: {has_alerts}, polite: {has_polite}）。動的コンテンツの文脈（{contexts}）も検出されています。{content_note} 各ステータス更新に対して、ライブリージョンが正しく接続されていることを確認してください。', { count: liveRegionCount, has_alerts: hasAlerts, has_polite: hasPolite, contexts: dynamicContexts.join(', '), content_note: contentNote }), elements: contextElements, helpUrl: HELP_URL }, ...extraRules],
    };
  }

  // Live regions present, no unprotected dynamic contexts → pass
  if (liveRegionCount > 0) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: 'Status messages must be programmatically determinable', impact: null, status: 'pass', reason: _t(sharedContext, '{count} ARIA live region(s) found (assertive: {has_alerts}, polite: {has_polite}).', 'ARIA ライブリージョンが {count} 件見つかりました（assertive: {has_alerts}, polite: {has_polite}）。', { count: liveRegionCount, has_alerts: hasAlerts, has_polite: hasPolite }), helpUrl: HELP_URL }, ...extraRules],
    };
  }

  // No dynamic contexts and no live regions — not enough info, mark incomplete
  return {
    successCriteriaId: SC,
    rules: [{ ruleId: RULE_ID, description: 'Status messages must be programmatically determinable', impact: 'moderate', status: 'incomplete', reason: _t(sharedContext, 'No ARIA live regions detected. If this page displays status updates (alerts, notifications, form feedback), verify they use role="status", role="alert", or aria-live.', 'ARIA ライブリージョンは検出されませんでした。このページでステータス更新（アラート、通知、フォームのフィードバックなど）を表示する場合は、role="status"、role="alert"、または aria-live を使用していることを確認してください。'), helpUrl: HELP_URL }, ...extraRules],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
