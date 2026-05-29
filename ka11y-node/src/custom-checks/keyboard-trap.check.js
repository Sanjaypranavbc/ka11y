'use strict';

const {
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '2.1.2';
const RULE_ID = 'custom-keyboard-trap';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/no-keyboard-trap';
const MAX_TABS = 200;
const SETTLE_MS = 60;
const CYCLE_WINDOW = 4;

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

function _formatTrapDetail(context, detail) {
  if (detail.type === 'trap-signal') {
    return _t(
      context,
      'Keyboard focus appears trapped in: {snippet}. Tab key could not escape the component.',
      'キーボードフォーカスが次の要素内に閉じ込められているように見えます: {snippet}。Tab キーでそのコンポーネントから抜け出せませんでした。',
      { snippet: detail.html.slice(0, 120) },
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
  const recentKeys = [];
  let trapHtml = null;

  for (let i = 0; i < MAX_TABS; i++) {
    await page.keyboard.press('Tab');
    await new Promise(r => setTimeout(r, SETTLE_MS));

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

    recentKeys.push(activeInfo.key);
    if (recentKeys.length > CYCLE_WINDOW) recentKeys.shift();

    const isStuck = recentKeys.length >= 3 && recentKeys.every(k => k === recentKeys[0]);
    const isCycle = recentKeys.length === 4 && recentKeys[0] === recentKeys[2] && recentKeys[1] === recentKeys[3] && recentKeys[0] !== recentKeys[1];
    
    if (isStuck || isCycle) {
      await page.keyboard.press('Escape');
      await new Promise(r => setTimeout(r, SETTLE_MS));
      await page.keyboard.press('Tab');
      await new Promise(r => setTimeout(r, SETTLE_MS));

      const afterEscape = await page.evaluate(() => {
        const el = document.activeElement;
        if (!el || el === document.body || el === document.documentElement) return null;
        const allEls = Array.from(document.querySelectorAll('*'));
        const pos = allEls.indexOf(el);
        const stable = el.id || el.getAttribute('name') || '';
        const key = stable ? `${el.tagName}:${stable}` : `${pos}:${el.tagName}`;
        return { key, html: el.outerHTML.slice(0, 150) };
      });

      if (afterEscape && (afterEscape.key || afterEscape) === activeInfo.key) {
        trapHtml = activeInfo.html;
        break;
      }
      recentKeys.length = 0;
    }
  }

  const shiftTab = async () => {
    await page.keyboard.down('Shift');
    await page.keyboard.press('Tab');
    await page.keyboard.up('Shift');
  };

  if (!trapHtml) {
    recentKeys.length = 0;
    for (let i = 0; i < MAX_TABS; i++) {
      await shiftTab();
      await new Promise(r => setTimeout(r, SETTLE_MS));

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

      recentKeys.push(activeInfo.key);
      if (recentKeys.length > CYCLE_WINDOW) recentKeys.shift();

      const isStuck = recentKeys.length >= 3 && recentKeys.every(k => k === recentKeys[0]);
      const isCycle = recentKeys.length === 4 && recentKeys[0] === recentKeys[2] && recentKeys[1] === recentKeys[3] && recentKeys[0] !== recentKeys[1];

      if (isStuck || isCycle) {
        await page.keyboard.press('Escape');
        await new Promise(r => setTimeout(r, SETTLE_MS));
        await shiftTab();
        await new Promise(r => setTimeout(r, SETTLE_MS));

        const afterEscape = await page.evaluate(() => {
          const el = document.activeElement;
          if (!el || el === document.body || el === document.documentElement) return null;
          const allEls = Array.from(document.querySelectorAll('*'));
          const pos = allEls.indexOf(el);
          const stable = el.id || el.getAttribute('name') || '';
          const key = stable ? `${el.tagName}:${stable}` : `${pos}:${el.tagName}`;
          return { key, html: el.outerHTML.slice(0, 150) };
        });

        if (afterEscape && (afterEscape.key || afterEscape) === activeInfo.key) {
          trapHtml = activeInfo.html;
          break;
        }
        recentKeys.length = 0;
      }
    }
  }

  const ARROW_TRAP_ROLES = ['tree', 'grid', 'listbox', 'menu', 'tablist', 'radiogroup'];
  const arrowTraps = [];

  if (!trapHtml) {
    for (const role of ARROW_TRAP_ROLES) {
      const widgets = await page.evaluate((r) => {
        return Array.from(document.querySelectorAll(`[role="${r}"]`)).slice(0, 3).map(el => ({
          id: el.id || null,
          html: el.outerHTML.slice(0, 100),
          selector: el.id ? `#${CSS.escape(el.id)}` : null,
          role: r,
          childCount: el.querySelectorAll('[role]').length,
        }));
      }, role);

      for (const widget of (widgets || [])) {
        if (widget.childCount === 0) continue;

        await page.evaluate((sel, r) => {
          const root = sel ? document.querySelector(sel) : document.querySelector(`[role="${r}"]`);
          if (!root) return;
          const first = root.querySelector('[tabindex], button, a[href], input, select, textarea, [role="option"], [role="treeitem"], [role="menuitem"], [role="tab"], [role="row"], [role="gridcell"]');
          (first || root).focus({ preventScroll: true });
        }, widget.selector, role);
        await new Promise(res => setTimeout(res, SETTLE_MS));

        const focusBeforeArrows = await page.evaluate((sel, r) => {
          const root = sel ? document.querySelector(sel) : document.querySelector(`[role="${r}"]`);
          const el = document.activeElement;
          if (!el) return { key: null, insideWidget: false };
          const allEls = Array.from(document.querySelectorAll('*'));
          return {
            key: `${allEls.indexOf(el)}:${el.tagName}`,
            insideWidget: root ? root.contains(el) : false,
          };
        }, widget.selector, role);

        if (!focusBeforeArrows.insideWidget) continue;

        await page.keyboard.press('ArrowDown');
        await new Promise(res => setTimeout(res, SETTLE_MS));
        const afterDown = await page.evaluate(() => {
          const el = document.activeElement;
          const allEls = Array.from(document.querySelectorAll('*'));
          return `${allEls.indexOf(el)}:${el.tagName}`;
        });

        await page.keyboard.press('ArrowUp');
        await new Promise(res => setTimeout(res, SETTLE_MS));
        const afterUp = await page.evaluate(() => {
          const el = document.activeElement;
          const allEls = Array.from(document.querySelectorAll('*'));
          return `${allEls.indexOf(el)}:${el.tagName}`;
        });

        const arrowsDoNothing = afterDown === focusBeforeArrows.key && afterUp === focusBeforeArrows.key;

        await page.keyboard.press('Tab');
        await new Promise(res => setTimeout(res, SETTLE_MS));
        const afterTab = await page.evaluate((sel, r) => {
          const root = sel ? document.querySelector(sel) : document.querySelector(`[role="${r}"]`);
          const el = document.activeElement;
          return {
            key: Array.from(document.querySelectorAll('*')).indexOf(el),
            insideWidget: root ? root.contains(el) : false,
          };
        }, widget.selector, role);

        if (arrowsDoNothing && afterTab.insideWidget) {
          arrowTraps.push(widget);
        }
      }
    }
  }

  const modalFindings = [];
  if (!trapHtml) {
    const dialogs = await page.evaluate(() => {
      const SEL = 'dialog[open], [role="dialog"], [role="alertdialog"], [aria-modal="true"]';
      return Array.from(document.querySelectorAll(SEL)).slice(0, 3).map(el => ({
        id: el.id || null,
        html: el.outerHTML.slice(0, 100),
        selector: el.id ? `#${CSS.escape(el.id)}` : null,
      }));
    });

    for (const dlg of (dialogs || [])) {
      await page.evaluate((sel) => {
        const root = document.querySelector(sel);
        if (root) {
          const target = root.querySelector('[tabindex], button, a[href], input, select, textarea');
          (target && typeof target.focus === 'function') ? target.focus({ preventScroll: true }) : null;
        }
      }, dlg.selector);
      await new Promise(r => setTimeout(r, SETTLE_MS));

      await page.keyboard.press('Escape');
      await new Promise(r => setTimeout(r, SETTLE_MS + 40));

      const stillInside = await page.evaluate((sel) => {
        const root = sel ? document.querySelector(sel) : null;
        if (!root) return false;
        const el = document.activeElement;
        return root.contains(el);
      }, dlg.selector);

      if (stillInside) {
        modalFindings.push(dlg);
      }
    }
  }

  const incompleteHeuristics = [];
  if (!trapHtml && modalFindings.length === 0) {
    const nonModals = await page.evaluate(() => {
      const SEL = '.modal, .dialog, .popup, [class*="modal" i], [class*="dialog" i]';
      return Array.from(document.querySelectorAll(SEL)).slice(0, 3).filter(el => {
        const cs = window.getComputedStyle(el);
        return cs.display !== 'none' && cs.visibility !== 'hidden' && cs.position === 'fixed';
      }).map(el => ({ id: el.id || null, html: el.outerHTML.slice(0, 100), selector: el.id ? `#${CSS.escape(el.id)}` : null }));
    });

    for (const candidate of (nonModals || [])) {
      await page.evaluate((sel) => {
        const root = document.querySelector(sel);
        const focusable = root.querySelector('[tabindex], button, a[href]');
        (focusable || root).focus({ preventScroll: true });
      }, candidate.selector);
      await new Promise(r => setTimeout(r, SETTLE_MS));

      await page.keyboard.press('Escape');
      await new Promise(r => setTimeout(r, SETTLE_MS + 20));

      const outcome = await page.evaluate((sel) => {
        const root = document.querySelector(sel);
        if (!root) return { stillVisible: false, hasCloseAffordance: true };
        const cs = window.getComputedStyle(root);
        const stillVisible = cs.display !== 'none' && cs.visibility !== 'hidden';
        const hasCloseAffordance = !!root.querySelector('button[aria-label*="close" i], button[aria-label*="閉じる"], [aria-label*="close" i][role="button"], button.close, .modal-close');
        return { stillVisible, hasCloseAffordance };
      }, candidate.selector);

      if (outcome.stillVisible && outcome.hasCloseAffordance) {
        incompleteHeuristics.push({ type: 'nonmodal-no-close', ...candidate });
      }
    }
  }

  if (!trapHtml && modalFindings.length === 0 && arrowTraps.length > 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Keyboard focus must not be trapped in a component',
        impact: 'serious',
        status: 'incomplete',
        reason: _t(sharedContext, 'Possible arrow-key trap in {role} widgets: {count} elements found. Ensure that users can navigate into and out of these components using only the Tab key, even if internal navigation uses arrow keys.', '{role} ウィジェットに矢印キーのトラップがある可能性があります（矢印キー操作）：{count} 個の要素が見つかりました。内部のナビゲーションに矢印キーを使用している場合でも、Tab キーだけでこれらのコンポーネントに入退できることを確認してください。', { role: arrowTraps[0].role, count: arrowTraps.length }),
        elements: arrowTraps.map(t => ({ html: t.html, tag: t.role.toUpperCase() })),
        helpUrl: HELP_URL,
      }],
    };
  }

  if (!trapHtml && modalFindings.length === 0 && arrowTraps.length === 0) {
    // Check for scripted suppression heuristics (F58)
    const suppression = await page.evaluate(() => {
      const results = [];
      const all = document.querySelectorAll('*');
      for (const el of all) {
        const str = el.outerHTML.slice(0, 1000);
        if (str.includes('onkeydown') || str.includes('addEventListener')) {
          if (str.includes('preventDefault') && (str.includes('9') || str.includes('Tab') || str.includes('27') || str.includes('Escape'))) {
            results.push({ type: 'script-key-suppression', html: el.outerHTML.slice(0, 200) });
          }
        }
      }
      return results;
    });
    if (suppression.length > 0) {
      incompleteHeuristics.push(suppression[0]);
    }
  }

  if (trapHtml) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Keyboard focus must not be trapped in a component',
        impact: 'critical',
        status: 'fail',
        reason: _t(sharedContext, 'Keyboard focus appears trapped in: {snippet}. Tab key could not escape the component even after pressing Escape.', 'キーボードフォーカスが次の要素内に閉じ込められているように見えます: {snippet}。Escape を押した後でも Tab キーでそのコンポーネントから抜け出せませんでした。', { snippet: trapHtml.slice(0, 120) }),
        elements: [{ html: trapHtml }],
        helpUrl: HELP_URL,
      }],
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

  if (incompleteHeuristics.length > 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Keyboard focus must not be trapped in a component',
        impact: 'serious',
        status: 'incomplete',
        reason: _formatTrapDetail(sharedContext, incompleteHeuristics[0]),
        elements: incompleteHeuristics.map(h => ({ html: h.html, tag: 'POPUP' })),
        helpUrl: HELP_URL,
      }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{ ruleId: RULE_ID, description: 'Keyboard focus must not be trapped in a component', impact: null, status: 'pass', reason: _t(sharedContext, 'No keyboard focus traps detected during Tab navigation.', 'Tab ナビゲーション中にキーボードフォーカストラップは検出されませんでした。'), helpUrl: HELP_URL }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
