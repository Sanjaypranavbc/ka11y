'use strict';

const SC = '2.1.4';
const RULE_ID = 'custom-character-key-shortcuts';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/character-key-shortcuts';

// N12 fix: only flag letter characters (a-z, A-Z) as character key shortcuts.
// WCAG 2.1.4 targets character shortcuts that could fire unexpectedly; digit keys (0-9)
// are not typically considered character key shortcuts in most contexts.
// We also flag common punctuation/symbols that could be used as shortcuts,
// but intentionally exclude the 0-9 digit range (ASCII codes 48-57).
const PRINTABLE_CHAR_RE = /^[a-zA-Z!-/:-@[-`{-~]$/; // letters + symbols, NOT digits

async function run(page) {
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
    for (const script of document.querySelectorAll('script:not([src])')) {
      const src = script.textContent || '';
      if (!LISTEN_RE.test(src)) continue;
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

    const totalAccesskeys = document.querySelectorAll('[accesskey]').length;
    const totalHandlers = document.querySelectorAll('[onkeydown], [onkeypress], [onkeyup]').length;
    return { violations, totalAccesskeys, totalHandlers };
  }, PRINTABLE_CHAR_RE.source);

  if (data.violations.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Single character key shortcuts must be remappable or disableable',
        impact: null,
        status: 'pass',
        reason: `${data.totalAccesskeys} accesskey attribute(s), ${data.totalHandlers} inline key handler(s), and inline script addEventListener calls checked — none use unguarded single character shortcuts (letters/symbols without Ctrl/Alt/Meta modifier).`,
        helpUrl: HELP_URL,
      }],
    };
  }

  const violations = data.violations;
  const accesskeyCount    = violations.filter(d => d.type === 'accesskey').length;
  const handlerCount      = violations.filter(d => d.type === 'inline-handler').length;
  const scriptListenCount = violations.filter(d => d.type === 'script-listener').length;
  const sample = violations.slice(0, 3).map(d => d.html.slice(0, 80)).join('; ');

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Single character key shortcuts must be remappable or disableable',
      impact: 'moderate',
      status: 'incomplete',
      reason: `${accesskeyCount} accesskey shortcut(s), ${handlerCount} inline key handler(s), and ${scriptListenCount} script addEventListener call(s) detected that may activate on a single character key without a modifier. Verify each can be turned off, remapped, or is only active on focus: ${sample}.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, PRINTABLE_CHAR_RE };
