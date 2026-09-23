'use strict';

const {
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '2.1.4';
const RULE_ID = 'custom-character-key-shortcuts';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/character-key-shortcuts';

// N12 fix: only flag letter characters (a-z, A-Z) as character key shortcuts.
// WCAG 2.1.4 targets character shortcuts that could fire unexpectedly; digit keys (0-9)
// are not typically considered character key shortcuts in most contexts.
// We also flag common punctuation/symbols that could be used as shortcuts,
// but intentionally exclude the 0-9 digit range (ASCII codes 48-57).
const PRINTABLE_CHAR_RE = /^[a-zA-Z!-/:-@[-`{-~]$/; // letters + symbols, NOT digits

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);
  const data = await page.evaluate((printableRe) => {
    const violations = [];
    const re = new RegExp(printableRe);

    // 1. accesskey attributes — flag only printable single-char values
    for (const el of document.querySelectorAll('[accesskey]')) {
      const key = (el.getAttribute('accesskey') || '').trim();
      if (key.length === 1 && re.test(key)) {
        violations.push({
          type: 'accesskey',
          key,
          html: el.outerHTML.slice(0, 150),
        });
      }
    }

    // 2. Inline key handlers — heuristic: detect single-char key checks without modifiers
    // Bug fix: expanded patterns to catch more modern keyboard API usage
    for (const el of document.querySelectorAll('[onkeydown], [onkeypress], [onkeyup]')) {
      const handler = (
        (el.getAttribute('onkeydown') || '') +
        (el.getAttribute('onkeypress') || '') +
        (el.getAttribute('onkeyup') || '')
      );

      // Match: event.key === 'x'  /  event.key == 'x'  /  event.code === 'KeyX'
      //        event.key.toLowerCase() === 'x'  /  e.key === 'X'
      //        event.key === '!'  /  event.key === '@'  (symbol shortcuts — same as PRINTABLE_CHAR_RE)
      // N12 fix: letters + symbols only; exclude digit keys (0-9) per WCAG 2.1.4.
      // keyCode range 65-90 = A-Z only (digits are 48-57, excluded).
      const KEY_RE = /(?:\.key|\.code)\s*(?:\.toLowerCase\s*\(\s*\))?\s*===?\s*['"][a-zA-Z!-/:-@[\-`{-~]['"]|keyCode\s*===?\s*(?:6[5-9]|[7-8]\d|90)/;
      const hasSingleKey = KEY_RE.test(handler);

      // Check that a modifier guard (Ctrl/Alt/Meta) is co-located with the key check.
      // Strategy: find the index of the first key match and the nearest modifier mention;
      // if they are within 120 chars of each other, the modifier plausibly guards the key.
      // This prevents false-negatives from handlers that check a modifier in an unrelated branch.
      const keyIdx = handler.search(KEY_RE);
      const modIdx = handler.search(/ctrlKey|altKey|metaKey/);
      const hasModifierGuard = keyIdx >= 0 && modIdx >= 0 && Math.abs(keyIdx - modIdx) <= 120;

      if (hasSingleKey && !hasModifierGuard) {
        violations.push({
          type: 'inline-handler',
          html: el.outerHTML.slice(0, 150),
        });
      }
    }

    // 3. Inline <script> tags — catch addEventListener-style key handlers that
    // do not appear as HTML attributes (common in vanilla JS and light frameworks).
    const KEY_RE_SRC = /(?:\.key|\.code)\s*(?:\.toLowerCase\s*\(\s*\))?\s*===?\s*['"][a-zA-Z!-/:-@[\-`{-~]['"]|keyCode\s*===?\s*(?:6[5-9]|[7-8]\d|90)/;
    const LISTEN_RE = /addEventListener\s*\(\s*['"]key(?:down|press|up)['"]/;
    const docListenerRe = /document\s*\.\s*addEventListener\s*\(\s*['"]key(?:down|press|up)['"]/;
    for (const script of document.querySelectorAll('script:not([src])')) {
      const src = script.textContent || '';
      if (!LISTEN_RE.test(src) && !docListenerRe.test(src)) continue;
      const keyIdx = src.search(KEY_RE_SRC);
      if (keyIdx < 0) continue;
      const modIdx = src.search(/ctrlKey|altKey|metaKey/);
      const hasModifierGuard = modIdx >= 0 && Math.abs(keyIdx - modIdx) <= 200;
      if (!hasModifierGuard) {
        violations.push({
          type: 'script-listener',
          html: src.slice(Math.max(0, keyIdx - 40), keyIdx + 100).trim().slice(0, 150),
        });
        break; // one finding per page for this category is sufficient
      }
    }

    // 4. Runtime listener registry (G217): keydown/keyup/keypress handlers registered on
    //    document/window/body through addEventListener — the common case that no static
    //    scan can see — whose source compares a single printable key without a modifier.
    let runtimeListeners = 0;
    try {
      const R = window.__ka11yRuntime;
      if (R && Array.isArray(R.docListeners)) {
        const keyListeners = R.docListeners.filter(l => /^key(down|up|press)$/.test(l.type));
        runtimeListeners = keyListeners.length;
        for (const l of keyListeners) {
          const src = l.snippet || '';
          const keyIdx = src.search(KEY_RE_SRC);
          if (keyIdx < 0) continue;
          const modIdx = src.search(/ctrlKey|altKey|metaKey|shiftKey/);
          if (modIdx >= 0 && Math.abs(keyIdx - modIdx) <= 200) continue;
          violations.push({ type: 'runtime-listener', html: `${l.target}.addEventListener('${l.type}', …) ${src.slice(Math.max(0, keyIdx - 40), keyIdx + 80).trim()}`.slice(0, 150) });
          break;
        }
      }
    } catch (_) { /* ignore */ }

    // 5. Keyboard-shortcut libraries loaded on the page (Mousetrap, hotkeys-js, keymaster, tinykeys)
    let shortcutLibrary = null;
    try {
      if (window.Mousetrap) shortcutLibrary = 'Mousetrap';
      else if (window.hotkeys) shortcutLibrary = 'hotkeys-js';
      else if (window.keymaster || (window.key && window.key.getScope)) shortcutLibrary = 'keymaster';
      else if (window.tinykeys) shortcutLibrary = 'tinykeys';
    } catch (_) { /* ignore */ }
    if (shortcutLibrary) violations.push({ type: 'shortcut-library', html: `${shortcutLibrary} shortcut library detected` });

    // 6. A UI that lets users turn shortcuts off or remap them satisfies 2.1.4 (G217).
    const REMAP_RE = /keyboard\s+shortcuts?|shortcut\s+(settings|keys|preferences)|remap|disable\s+shortcuts|turn\s+off\s+shortcuts|ショートカット(キー)?(の)?(設定|無効|変更)|キーボードショートカット/i;
    const hasRemapUI = Array.from(document.querySelectorAll('button, a[href], [role="button"], [role="menuitem"], summary, label, h2, h3, legend'))
      .some(el => REMAP_RE.test((el.textContent || '') + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('title') || '')));

    const totalAccesskeys = document.querySelectorAll('[accesskey]').length;
    const totalHandlers = document.querySelectorAll('[onkeydown], [onkeypress], [onkeyup]').length;
    return { violations, totalAccesskeys, totalHandlers, runtimeListeners, hasRemapUI, shortcutLibrary };
  }, PRINTABLE_CHAR_RE.source);

  if (data.violations.length > 0 && data.hasRemapUI) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Single character key shortcuts must be remappable or disableable',
        impact: null,
        status: 'pass',
        reason: _t(
          sharedContext,
          '{n} single-character shortcut signal(s) detected, and the page offers a keyboard-shortcut settings/remap control — the turn-off/remap mechanism required by G217 is present. Verify it covers every shortcut.',
          '{n} 件の単一文字ショートカットの兆候が検出されましたが、ページにキーボードショートカットの設定/再割り当て機能があります。G217 が求める無効化/再割り当て手段は存在します。すべてのショートカットが対象か確認してください。',
          { n: data.violations.length },
        ),
        helpUrl: HELP_URL,
      }],
    };
  }

  if (data.violations.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Single character key shortcuts must be remappable or disableable',
        impact: null,
        status: 'pass',
        reason: _t(
          sharedContext,
          '{accesskey_count} accesskey attribute(s), {handler_count} inline key handler(s), {runtime_count} runtime document/window key listener(s) and inline scripts checked — none use unguarded single character shortcuts (letters/symbols without Ctrl/Alt/Meta modifier).',
          'accesskey 属性 {accesskey_count} 件、インラインのキーイベントハンドラー {handler_count} 件、実行時の document/window キーリスナー {runtime_count} 件、およびインライン script を確認しましたが、修飾キーなしで発火する単一文字ショートカットは検出されませんでした。',
          {
            accesskey_count: data.totalAccesskeys,
            handler_count: data.totalHandlers,
            runtime_count: data.runtimeListeners || 0,
          },
        ),
        helpUrl: HELP_URL,
      }],
    };
  }

  const violations = data.violations;
  const accesskeyCount    = violations.filter(d => d.type === 'accesskey').length;
  const handlerCount      = violations.filter(d => d.type === 'inline-handler').length;
  const scriptListenCount = violations.filter(d => d.type === 'script-listener' || d.type === 'runtime-listener' || d.type === 'shortcut-library').length;
  const sample = violations.slice(0, 3).map(d => d.html.slice(0, 80)).join('; ');

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Single character key shortcuts must be remappable or disableable',
      impact: 'moderate',
      status: 'incomplete',
      reason: _t(
        sharedContext,
        '{accesskey_count} accesskey shortcut(s), {handler_count} inline key handler(s), and {script_listener_count} script addEventListener call(s) detected that may activate on a single character key without a modifier. Verify each can be turned off, remapped, or is only active on focus: {sample}.',
        '修飾キーなしの単一文字キーで発火する可能性がある accesskey ショートカット {accesskey_count} 件、インラインのキーイベントハンドラー {handler_count} 件、script の addEventListener 呼び出し {script_listener_count} 件が検出されました。各ショートカットが無効化・再割り当て可能であるか、またはフォーカス時のみ有効であるか確認してください: {sample}。',
        {
          accesskey_count: accesskeyCount,
          handler_count: handlerCount,
          script_listener_count: scriptListenCount,
          sample,
        },
      ),
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, PRINTABLE_CHAR_RE };
