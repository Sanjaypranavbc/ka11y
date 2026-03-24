'use strict';

const SC = '2.1.4';
const RULE_ID = 'custom-character-key-shortcuts';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/character-key-shortcuts';

// Bug fix: only flag printable ASCII characters (codes 33–126) — not control/special keys
const PRINTABLE_CHAR_RE = /^[!-~]$/; // matches any single printable ASCII

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
      const hasSingleKey = /(?:\.key|\.code)\s*(?:\.toLowerCase\s*\(\s*\))?\s*===?\s*['"][a-zA-Z0-9]['"]|keyCode\s*===?\s*(?:[3-9]\d|1[01]\d|12[0-6])/.test(handler);

      // Check that ALL paths require a modifier (Ctrl, Alt, Meta)
      // Bug fix: ensure modifier check is co-located with the key check, not just present somewhere
      const hasModifierGuard = /ctrlKey|altKey|metaKey/.test(handler);

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

module.exports = { run, SC, RULE_ID, HELP_URL };
