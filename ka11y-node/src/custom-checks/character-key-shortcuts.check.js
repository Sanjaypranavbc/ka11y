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
      // N12 fix: only match letter keys (a-z, A-Z) in key/code checks; exclude digit keys (0-9).
      // keyCode range 65-90 = A-Z only (digits are 48-57, excluded).
      const hasSingleKey = /(?:\.key|\.code)\s*(?:\.toLowerCase\s*\(\s*\))?\s*===?\s*['"][a-zA-Z]['"]|keyCode\s*===?\s*(?:6[5-9]|[7-8]\d|90)/.test(handler);

      // Check that a modifier guard (Ctrl/Alt/Meta) is co-located with the key check.
      // Strategy: find the index of the first key match and the nearest modifier mention;
      // if they are within 120 chars of each other, the modifier plausibly guards the key.
      // This prevents false-negatives from handlers that check a modifier in an unrelated branch.
      const keyIdx = handler.search(/(?:\.key|\.code)\s*(?:\.toLowerCase\s*\(\s*\))?\s*===?\s*['"][a-zA-Z]['"]|keyCode\s*===?\s*(?:6[5-9]|[7-8]\d|90)/);
      const modIdx = handler.search(/ctrlKey|altKey|metaKey/);
      const hasModifierGuard = keyIdx >= 0 && modIdx >= 0 && Math.abs(keyIdx - modIdx) <= 120;

      if (hasSingleKey && !hasModifierGuard) {
        violations.push({
          type: 'inline-handler',
          html: el.outerHTML.slice(0, 150),
        });
      }
    }

    return violations;
  }, PRINTABLE_CHAR_RE.source);

  if (data.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Single character key shortcuts must be remappable or disableable',
        impact: null,
        status: 'pass',
        reason: 'No problematic single character key shortcuts detected.',
        helpUrl: HELP_URL,
      }],
    };
  }

  const accesskeyCount = data.filter(d => d.type === 'accesskey').length;
  const handlerCount   = data.filter(d => d.type === 'inline-handler').length;
  const sample = data.slice(0, 3).map(d => d.html.slice(0, 80)).join('; ');

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Single character key shortcuts must be remappable or disableable',
      impact: 'moderate',
      status: 'incomplete',
      reason: `${accesskeyCount} accesskey shortcut(s) and ${handlerCount} inline key handler(s) detected that may activate on a single character key without a modifier. Verify each can be turned off, remapped, or is only active on focus: ${sample}.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, PRINTABLE_CHAR_RE };
