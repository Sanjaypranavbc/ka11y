'use strict';

const {
  getSharedRuleContext,
  renderLocalizedText,
  settle,
} = require('./sharedAssets');

const SC = '2.1.2';
const RULE_ID = 'custom-keyboard-trap';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/no-keyboard-trap';
const MAX_TABS = 200;
// Buffer size for cycle detection: tracks last 4 focused keys.
// This detects both single-element stuck traps (A,A,A) and two-element cycling
// traps (A,B,A,B) — the most common real-world pattern (dialog with 2 focusable elements).
const CYCLE_WINDOW = 4;

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

function _formatTrapDetail(detail, context) {
  if (!detail || typeof detail !== 'object') return '';

  if (detail.type === 'arrow-key-trap') {
    return _t(
      context,
      'arrow-key trap in [role="{role}"]',
      '[role="{role}"] 内で矢印キー操作のトラップの可能性',
      { role: detail.role },
    );
  }

  if (detail.type === 'iframe-tab-trap') {
    return _t(
      context,
      'Tab trap in iframe ({frameUrl})',
      'iframe 内で Tab トラップの可能性 ({frameUrl})',
      { frameUrl: detail.frameUrl },
    );
  }

  if (detail.type === 'script-key-suppression') {
    return _t(
      context,
      'keyboard handler suppresses {keys} with preventDefault() ({snippet})',
      'キーボードハンドラーが preventDefault() で {keys} を抑止しています（{snippet}）',
      { keys: detail.keys || 'Tab/Escape', snippet: detail.snippet || '' },
    );
  }

  if (detail.type === 'nonmodal-no-close') {
    return _t(
      context,
      'non-modal popup remains visible after Escape ({selector})',
      '非モーダルポップアップが Escape 後も表示されたままです（{selector}）',
      { selector: detail.selector || detail.html || '' },
    );
  }

  return '';
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);
  // Focus the page body to start from a known position
  await page.evaluate(() => { try { document.body.focus(); } catch (_) {} });

  // Bug fix: track the LAST N focus targets to detect consecutive repetition
  // rather than cumulative count which caused false positives on identical elements
  const recentKeys = [];
  let trapHtml = null;

  for (let i = 0; i < MAX_TABS; i++) {
    await page.keyboard.press('Tab');
    // Wait for focus event handlers and React/Vue re-renders to settle
    await settle(page, 60);

    const activeInfo = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body || el === document.documentElement) return null;
      // Bug fix: prefer stable identifiers (id, name, aria-label) over DOM position.
      // Fall back to position+tag only when no stable attribute is available.
      const allEls = Array.from(document.querySelectorAll('*'));
      const pos = allEls.indexOf(el);
      // Use only id or name as stable key — NOT aria-label, which is often shared across
      // multiple elements (e.g. three "Close" buttons) and would produce false-positive traps.
      const stable = el.id || el.getAttribute('name') || '';
      const key = stable ? `${el.tagName}:${stable}` : `${pos}:${el.tagName}`;
      return { key, html: el.outerHTML.slice(0, 150), tagName: el.tagName.toLowerCase() };
    });

    if (!activeInfo) break; // focus left the page or hit body

    recentKeys.push(activeInfo.key);
    if (recentKeys.length > CYCLE_WINDOW) recentKeys.shift();

    // Detect two trap patterns:
    // 1. Stuck: same element focused 3+ times consecutively (1-element trap)
    const isStuck = recentKeys.length >= 3 && recentKeys.every(k => k === recentKeys[0]);
    // 2. Two-element cycle: A→B→A→B (most common dialog/tooltip trap)
    const n = recentKeys.length;
    const isTwoElemCycle = n >= 4 &&
      recentKeys[n - 1] === recentKeys[n - 3] &&
      recentKeys[n - 2] === recentKeys[n - 4] &&
      recentKeys[n - 1] !== recentKeys[n - 2];
    const isConsecutiveTrap = isStuck || isTwoElemCycle;

    if (isConsecutiveTrap) {
      // Verify it's a real trap: try Escape then Tab
      // Settle after Escape to allow modal-close / focus-restore handlers to run
      await page.keyboard.press('Escape');
      await settle(page, 60);
      await page.keyboard.press('Tab');
      await settle(page, 60);

      const afterEscape = await page.evaluate(() => {
        const el = document.activeElement;
        if (!el || el === document.body) return null;
        const allEls = Array.from(document.querySelectorAll('*'));
        const pos = allEls.indexOf(el);
        const stable = el.id || el.getAttribute('name') || el.getAttribute('aria-label') || '';
        return stable ? `${el.tagName}:${stable}` : `${pos}:${el.tagName}`;
      });

      if (afterEscape === activeInfo.key) {
        trapHtml = activeInfo.html;
        break;
      }
      // Escape worked — reset tracking and continue
      recentKeys.length = 0;
    }
  }

  // FN fix: also test Shift+Tab (backward) navigation for traps.
  // A trap may only manifest when tabbing backward through the component.
  // Puppeteer helper: 'Shift+Tab' is not a valid key name — use down/press/up.
  const shiftTab = async () => {
    await page.keyboard.down('Shift');
    await page.keyboard.press('Tab');
    await page.keyboard.up('Shift');
  };

  if (!trapHtml) {
    const recentShiftKeys = [];

    for (let i = 0; i < MAX_TABS; i++) {
      await shiftTab();
      await settle(page, 60);

      const activeInfo = await page.evaluate(() => {
        const el = document.activeElement;
        if (!el || el === document.body || el === document.documentElement) return null;
        const allEls = Array.from(document.querySelectorAll('*'));
        const pos = allEls.indexOf(el);
        const stable = el.id || el.getAttribute('name') || '';
        const key = stable ? `${el.tagName}:${stable}` : `${pos}:${el.tagName}`;
        return { key, html: el.outerHTML.slice(0, 150), tagName: el.tagName.toLowerCase() };
      });

      if (!activeInfo) break;

      recentShiftKeys.push(activeInfo.key);
      if (recentShiftKeys.length > CYCLE_WINDOW) recentShiftKeys.shift();

      const sn = recentShiftKeys.length;
      const isShiftStuck = sn >= 3 && recentShiftKeys.every(k => k === recentShiftKeys[0]);
      const isShiftTwoElemCycle = sn >= 4 &&
        recentShiftKeys[sn - 1] === recentShiftKeys[sn - 3] &&
        recentShiftKeys[sn - 2] === recentShiftKeys[sn - 4] &&
        recentShiftKeys[sn - 1] !== recentShiftKeys[sn - 2];
      const isConsecutiveTrap = isShiftStuck || isShiftTwoElemCycle;

      if (isConsecutiveTrap) {
        // Verify: try Escape then Shift+Tab
        await page.keyboard.press('Escape');
        await settle(page, 60);
        await shiftTab();
        await settle(page, 60);

        const afterEscape = await page.evaluate(() => {
          const el = document.activeElement;
          if (!el || el === document.body) return null;
          const allEls = Array.from(document.querySelectorAll('*'));
          const pos = allEls.indexOf(el);
          const stable = el.id || el.getAttribute('name') || '';
          return stable ? `${el.tagName}:${stable}` : `${pos}:${el.tagName}`;
        });

        if (afterEscape === activeInfo.key) {
          trapHtml = activeInfo.html;
          break;
        }
        recentShiftKeys.length = 0;
      }
    }
  }

  // ── Arrow key trap detection in ARIA composite widgets ───────────────────
  // WCAG 2.1.2 for composite widgets: arrow keys SHOULD navigate within the
  // widget; Tab MUST be able to exit.  We test both concerns:
  // 1. Arrow keys do nothing at all (unimplemented widget — AT users can't navigate)
  // 2. Tab cannot exit the widget container after entering it
  const ARROW_TRAP_ROLES = ['tree', 'grid', 'listbox', 'menu', 'tablist', 'radiogroup', 'treegrid', 'composite'];
  const arrowTrapFindings = [];

  if (!trapHtml) {
    for (const role of ARROW_TRAP_ROLES) {
      const widgetsResult = await page.evaluate((r) => {
        return Array.from(document.querySelectorAll(`[role="${r}"]`)).slice(0, 3).map(el => ({
          id: el.id || null,
          html: el.outerHTML.slice(0, 100),
          selector: el.id ? `#${CSS.escape(el.id)}` : null,
          role: r,
          childCount: el.querySelectorAll('[role]').length,
        }));
      }, role);
      const widgets = widgetsResult || [];

      for (const widget of widgets) {
        // Skip trivially empty widgets
        if (widget.childCount === 0) continue;

        const focusBeforeArrows = await page.evaluate((sel, r) => {
          const root = sel ? document.querySelector(sel) : document.querySelector(`[role="${r}"]`);
          if (!root) return { key: null, insideWidget: false };
          
          // Focus first focusable descendant or the widget itself
          const first = root.querySelector('[tabindex], button, a[href], input, select, textarea, [role="option"], [role="treeitem"], [role="menuitem"], [role="tab"], [role="row"], [role="gridcell"]');
          (first || root).focus({ preventScroll: true });

          const el = document.activeElement;
          if (!el) return { key: null, insideWidget: false };
          const allEls = Array.from(document.querySelectorAll('*'));
          return {
            key: `${allEls.indexOf(el)}:${el.tagName}`,
            insideWidget: root ? root.contains(el) : false,
          };
        }, widget.selector, role);

        if (!focusBeforeArrows || !focusBeforeArrows.insideWidget) continue;

        // Press ArrowDown then ArrowUp — if either changes active element, arrows work
        await page.keyboard.press('ArrowDown');
        await settle(page, 60);
        const afterDown = await page.evaluate(() => {
          const el = document.activeElement;
          const allEls = Array.from(document.querySelectorAll('*'));
          return el ? `${allEls.indexOf(el)}:${el.tagName}` : null;
        });

        await page.keyboard.press('ArrowUp');
        await settle(page, 60);
        const afterUp = await page.evaluate(() => {
          const el = document.activeElement;
          const allEls = Array.from(document.querySelectorAll('*'));
          return el ? `${allEls.indexOf(el)}:${el.tagName}` : null;
        });

        const arrowsDoNothing = afterDown === focusBeforeArrows.key && afterUp === focusBeforeArrows.key;

        // Also test: does Tab exit the widget container?
        await page.keyboard.press('Tab');
        await settle(page, 60);
        const afterTab = await page.evaluate((sel, r) => {
          const root = sel ? document.querySelector(sel) : document.querySelector(`[role="${r}"]`);
          const el = document.activeElement;
          if (!el || el === document.body) return { key: null, insideWidget: false };
          const allEls = Array.from(document.querySelectorAll('*'));
          return {
            key: `${allEls.indexOf(el)}:${el.tagName}`,
            insideWidget: root ? root.contains(el) : false,
          };
        }, widget.selector, role);

        const tabCannotExit = afterTab.insideWidget;

        if (arrowsDoNothing || tabCannotExit) {
          arrowTrapFindings.push({
            type: 'arrow-key-trap',
            role,
            html: widget.html,
            detail: arrowsDoNothing ? 'arrows unresponsive' : 'Tab cannot exit widget',
          });
        }
      }
    }
  }

  // ── Same-origin iframe Tab trap detection ─────────────────────────────────
  const iframeTrapFindings = [];

  if (!trapHtml) {
    const frames = (typeof page.frames === 'function' ? page.frames() : []).filter(f => typeof page.mainFrame === 'function' ? f !== page.mainFrame() : true);
    for (const frame of frames) {
      try {
        // Try a basic Tab-trap detection in the frame (forward only, 30 iterations)
        const frameRecentKeys = [];
        let frameTrapHtml = null;

        await frame.evaluate(() => {
          try { document.body.focus(); } catch (_) {}
        });

        for (let i = 0; i < 30; i++) {
          await page.keyboard.press('Tab');
          await settle(page, 60);

          const frameActive = await frame.evaluate(() => {
            const el = document.activeElement;
            if (!el || el === document.body || el === document.documentElement) return null;
            const allEls = Array.from(document.querySelectorAll('*'));
            const pos = allEls.indexOf(el);
            const stable = el.id || el.getAttribute('name') || '';
            return { key: stable ? `${el.tagName}:${stable}` : `${pos}:${el.tagName}`, html: el.outerHTML.slice(0, 100) };
          }).catch(() => null);

          if (!frameActive) break;

          frameRecentKeys.push(frameActive.key);
          if (frameRecentKeys.length > CYCLE_WINDOW) frameRecentKeys.shift();

          const fn = frameRecentKeys.length;
          const frameStuck = fn >= 3 && frameRecentKeys.every(k => k === frameRecentKeys[0]);
          const frameCycle = fn >= 4 &&
            frameRecentKeys[fn - 1] === frameRecentKeys[fn - 3] &&
            frameRecentKeys[fn - 2] === frameRecentKeys[fn - 4] &&
            frameRecentKeys[fn - 1] !== frameRecentKeys[fn - 2];

          if (frameStuck || frameCycle) {
            frameTrapHtml = frameActive.html;
            break;
          }
        }

        if (frameTrapHtml) {
          iframeTrapFindings.push({
            type: 'iframe-tab-trap',
            html: frameTrapHtml,
            frameUrl: frame.url(),
          });
        }
      } catch (_) {
        // Cross-origin frame — skip
      }
    }
  }

  // ── F85 modal-without-escape detection ──────────────────────────────────
  // Focus visible dialogs and check whether Escape returns focus outside.
  // Open-but-focus-scoped modals that can't be escape-closed are flagged.
  const modalFindings = [];

  if (!trapHtml) {
    const dialogs = await page.evaluate(() => {
      const SEL = 'dialog[open], [role="dialog"], [role="alertdialog"], [aria-modal="true"]';
      return Array.from(document.querySelectorAll(SEL))
        .filter(el => {
          const cs = window.getComputedStyle(el);
          if (cs.display === 'none' || cs.visibility === 'hidden') return false;
          const rect = el.getBoundingClientRect();
          return rect.width > 0 && rect.height > 0;
        })
        .slice(0, 5)
        .map(el => ({
          id: el.id || null,
          html: el.outerHTML.slice(0, 150),
          selector: el.id ? `#${el.id}` : null,
          hasCloseBtn: !!el.querySelector(
            'button[aria-label*="close" i], button[aria-label*="閉じる"], [aria-label*="close" i][role="button"], button.close, .modal-close'
          ),
        }));
    });

    for (const dlg of (dialogs || [])) {
      // Focus the dialog (or first focusable within).
      await page.evaluate((sel) => {
        const root = sel ? document.querySelector(sel) : null;
        const target = root
          ? (root.querySelector('[autofocus], button, [href], input, [tabindex]:not([tabindex="-1"])') || root)
          : null;
        if (target && typeof target.focus === 'function') {
          target.focus({ preventScroll: true });
        }
      }, dlg.selector);
      await settle(page, 60);

      // Press Escape and see if focus leaves the dialog.
      await page.keyboard.press('Escape');
      await settle(page, 100);

      const stillInside = await page.evaluate((sel) => {
        const root = sel ? document.querySelector(sel) : null;
        if (!root) return false; // dialog gone → Escape closed it, good.
        // If dialog still visible AND focus is inside it, the modal is a trap.
        const cs = window.getComputedStyle(root);
        if (cs.display === 'none' || cs.visibility === 'hidden') return false;
        const rect = root.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return false;
        const active = document.activeElement;
        return !!active && root.contains(active);
      }, dlg.selector);

      if (stillInside) {
        modalFindings.push({
          type: 'modal-no-escape',
          html: dlg.html,
          hasCloseBtn: dlg.hasCloseBtn,
        });
      }
    }
  }

  // ── F60 non-modal popup dismissibility probe ─────────────────────────────
  // Heuristic: visible popups/menus/tooltips should either dismiss on Escape
  // or expose a close affordance.
  const nonModalFindings = [];
  if (!trapHtml) {
    const nonModalCandidates = await page.evaluate(() => {
      const SEL = [
        '[role="tooltip"]',
        '[role="menu"]',
        '[role="listbox"]',
        '.popover',
        '.tooltip',
        '.dropdown-menu',
        '[data-popup]',
        '[data-popover]',
      ].join(', ');
      return Array.from(document.querySelectorAll(SEL))
        .filter(el => {
          if (el.closest('dialog[open], [role="dialog"], [aria-modal="true"]')) return false;
          const cs = window.getComputedStyle(el);
          if (cs.display === 'none' || cs.visibility === 'hidden') return false;
          const rect = el.getBoundingClientRect();
          return rect.width > 0 && rect.height > 0;
        })
        .slice(0, 5)
        .map((el, idx) => {
          if (!el.id) el.setAttribute('data-ka11y-popup-index', String(idx));
          const selector = el.id
            ? `#${CSS.escape(el.id)}`
            : `[data-ka11y-popup-index="${idx}"]`;
          return {
            selector,
            html: el.outerHTML.slice(0, 150),
          };
        });
    });

    for (const candidate of (nonModalCandidates || [])) {
      await page.evaluate((sel) => {
        const root = document.querySelector(sel);
        if (!root) return;
        const focusable = root.querySelector(
          '[autofocus], button, [href], input, [tabindex]:not([tabindex="-1"])'
        );
        (focusable || root).focus({ preventScroll: true });
      }, candidate.selector);
      await settle(page, 60);

      await page.keyboard.press('Escape');
      await settle(page, 80);

      const outcome = await page.evaluate((sel) => {
        const root = document.querySelector(sel);
        if (!root) return { stillVisible: false, hasCloseAffordance: true };
        const cs = window.getComputedStyle(root);
        const rect = root.getBoundingClientRect();
        const stillVisible = cs.display !== 'none' &&
          cs.visibility !== 'hidden' &&
          rect.width > 0 &&
          rect.height > 0;
        const hasCloseAffordance = !!root.querySelector(
          'button[aria-label*="close" i], button[aria-label*="dismiss" i], button[aria-label*="閉じる"], .close, .btn-close, [data-dismiss], [data-bs-dismiss]'
        );
        return { stillVisible, hasCloseAffordance };
      }, candidate.selector);

      if (outcome && outcome.stillVisible && !outcome.hasCloseAffordance) {
        nonModalFindings.push({
          type: 'nonmodal-no-close',
          selector: candidate.selector,
          html: candidate.html,
        });
      }
    }
  }

  // ── F58 scripted key suppression heuristic ───────────────────────────────
  const keySuppressionFindings = !trapHtml
    ? (await page.evaluate(() => {
        const findings = [];
        const KEY_HINT_RE = /(Tab|Escape|Arrow(?:Up|Down|Left|Right))/i;
        const PRESS_ATTRS = ['onkeydown', 'onkeyup', 'onkeypress'];

        for (const el of Array.from(document.querySelectorAll('[onkeydown], [onkeyup], [onkeypress]')).slice(0, 200)) {
          const handler = PRESS_ATTRS.map(attr => el.getAttribute(attr) || '').join(' ');
          if (!handler) continue;
          if (!/preventDefault\s*\(/i.test(handler)) continue;
          const keyMatch = handler.match(KEY_HINT_RE);
          if (!keyMatch) continue;
          findings.push({
            type: 'script-key-suppression',
            keys: keyMatch[1],
            snippet: handler.slice(0, 120),
            html: el.outerHTML.slice(0, 120),
          });
          if (findings.length >= 3) break;
        }

        if (findings.length === 0) {
          for (const script of Array.from(document.querySelectorAll('script:not([src])')).slice(0, 30)) {
            const src = script.textContent || '';
            if (!/addEventListener\s*\(\s*['"]key(?:down|press|up)['"]/i.test(src)) continue;
            if (!/preventDefault\s*\(/i.test(src)) continue;
            const keyMatch = src.match(KEY_HINT_RE);
            if (!keyMatch) continue;
            findings.push({
              type: 'script-key-suppression',
              keys: keyMatch[1],
              snippet: src.slice(0, 120).replace(/\s+/g, ' '),
              html: '<script>',
            });
            break;
          }
        }
        return findings;
      }) || [])
    : [];

  if (
    !trapHtml
    && arrowTrapFindings.length === 0
    && iframeTrapFindings.length === 0
    && modalFindings.length === 0
    && nonModalFindings.length === 0
    && keySuppressionFindings.length === 0
  ) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: 'Keyboard focus must not be trapped in a component', impact: null, status: 'pass', reason: _t(sharedContext, 'No keyboard focus traps detected during Tab navigation.', 'Tab ナビゲーション中にキーボードフォーカストラップは検出されませんでした。'), helpUrl: HELP_URL }],
    };
  }

  if (modalFindings.length > 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Keyboard focus must not be trapped in a component',
        impact: 'critical',
        status: 'fail',
        reason: _t(
          sharedContext,
          '{count} modal dialog(s) do not release keyboard focus when Escape is pressed (F85). Keyboard-only users cannot exit.',
          '{count} 件のモーダルダイアログで Escape キーを押してもフォーカスが解放されません（F85）。キーボード操作のみのユーザーは抜け出せません。',
          { count: modalFindings.length },
        ),
        elements: modalFindings.map(m => ({ html: m.html, tag: 'DIALOG' })),
        helpUrl: HELP_URL,
      }],
    };
  }

  if (!trapHtml) {
    const arrowDetail = arrowTrapFindings
      .map(f => _formatTrapDetail(f, sharedContext))
      .filter(Boolean)
      .join('; ');
    const iframeDetail = iframeTrapFindings
      .map(f => _formatTrapDetail({ ...f, frameUrl: f.frameUrl.slice(0, 60) }, sharedContext))
      .filter(Boolean)
      .join('; ');
    const nonModalDetail = nonModalFindings
      .map(f => _formatTrapDetail(f, sharedContext))
      .filter(Boolean)
      .join('; ');
    const scriptDetail = keySuppressionFindings
      .map(f => _formatTrapDetail(f, sharedContext))
      .filter(Boolean)
      .join('; ');
    const allDetail = [arrowDetail, iframeDetail, nonModalDetail, scriptDetail].filter(Boolean).join('; ');
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Keyboard focus must not be trapped in a component',
        impact: 'serious',
        status: 'incomplete',
        reason: _t(sharedContext, 'Potential keyboard trap signals detected: {detail}. Verify Tab/Shift+Tab escape paths, popup dismissibility, and key handlers that suppress Tab/Escape.', 'キーボードトラップの可能性があるシグナルを検出しました: {detail}。Tab/Shift+Tab で離脱できるか、ポップアップが閉じられるか、Tab/Escape を抑止するキー処理がないか確認してください。', { detail: allDetail }),
        helpUrl: HELP_URL,
      }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Keyboard focus must not be trapped in a component',
      impact: 'critical',
      status: 'fail',
      reason: _t(sharedContext, 'Keyboard focus appears trapped in: {snippet}. Tab key could not escape the component even after pressing Escape.', 'キーボードフォーカスが次の要素内に閉じ込められているように見えます: {snippet}。Escape を押した後でも Tab キーでそのコンポーネントから抜け出せませんでした。', { snippet: trapHtml.slice(0, 120) }),
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
