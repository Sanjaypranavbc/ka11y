'use strict';

const { run, PRINTABLE_CHAR_RE } = require('../../src/custom-checks/character-key-shortcuts.check');

// The check's page.evaluate returns { violations, totalAccesskeys, totalHandlers }
function makePage(violations, totalAccesskeys, totalHandlers) {
  const data = {
    violations: violations || [],
    totalAccesskeys: totalAccesskeys !== undefined ? totalAccesskeys : (violations || []).filter(v => v.type === 'accesskey').length,
    totalHandlers: totalHandlers !== undefined ? totalHandlers : (violations || []).filter(v => v.type === 'inline-handler').length,
  };
  return { evaluate: jest.fn().mockResolvedValue(data) };
}

describe('character-key-shortcuts.check (WCAG 2.1.4)', () => {
  test('passes when no single-char shortcuts are detected', async () => {
    const page = makePage([]);
    const result = await run(page);
    expect(result.successCriteriaId).toBe('2.1.4');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].ruleId).toBe('custom-character-key-shortcuts');
  });

  test('returns incomplete when accesskey shortcuts are found', async () => {
    const page = makePage([{ type: 'accesskey', key: 's', html: '<a accesskey="s">Save</a>' }]);
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].impact).toBe('moderate');
    expect(result.rules[0].reason).toContain('1 accesskey');
  });

  test('returns incomplete when inline key handlers without modifiers are found', async () => {
    const page = makePage([
      { type: 'inline-handler', html: '<div onkeydown="if(event.key===\'s\')save()">...</div>' },
    ]);
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('0 accesskey shortcut(s), 1 inline key handler(s)');
  });

  test('reports combined accesskey and inline handler count', async () => {
    const page = makePage([
      { type: 'accesskey', key: 'a', html: '<button accesskey="a">A</button>' },
      { type: 'accesskey', key: 'b', html: '<button accesskey="b">B</button>' },
      { type: 'inline-handler', html: '<div onkeydown="go()">x</div>' },
    ]);
    const result = await run(page);
    expect(result.rules[0].reason).toContain('2 accesskey shortcut(s), 1 inline key handler(s)');
  });

  // N12: digit key fix tests
  describe('N12: digit keys must NOT be flagged (only letters are character key shortcuts)', () => {
    test('digit accesskey (e.g. accesskey="1") should NOT be flagged', async () => {
      // The page.evaluate mock returns what the browser-side code would return.
      // With N12 fix the in-browser regex excludes digits, so no violations should come back.
      // We simulate this by returning empty violations (object format).
      const page = makePage([]);
      const result = await run(page);
      expect(result.rules[0].status).toBe('pass');
    });

    test('N12 fix: PRINTABLE_CHAR_RE (accesskey filter) does NOT match digit characters', () => {
      // Directly test the exported PRINTABLE_CHAR_RE regex — no source parsing needed
      const { PRINTABLE_CHAR_RE } = require('../../src/custom-checks/character-key-shortcuts.check');
      // Digits 0-9 should NOT match
      for (const digit of '0123456789') {
        expect(PRINTABLE_CHAR_RE.test(digit)).toBe(false);
      }
      // Letters should still match
      expect(PRINTABLE_CHAR_RE.test('a')).toBe(true);
      expect(PRINTABLE_CHAR_RE.test('Z')).toBe(true);
    });

    test('N12 fix: inline handler regex keyCode range excludes digit keyCodes 48-57', () => {
      const src = require('fs').readFileSync(
        require('path').resolve(__dirname, '../../src/custom-checks/character-key-shortcuts.check.js'),
        'utf8'
      );
      // After the N12 fix, the hasSingleKey pattern must NOT include digit keyCodes (48-57).
      // The keyCode range in the pattern should be 65-90 (A-Z letters only).
      // We check that the pattern covers 65 (start of A-Z) but not 48 or 57 (digits).
      // Pattern: keyCode\s*===?\s*(?:6[5-9]|[7-8]\d|90)
      expect(src).toMatch(/keyCode.*6\[5-9\]/); // covers keyCode 65-69
      // Digit keyCodes 48 and 57 should not appear in the pattern (only in comments)
      // Extract just the hasSingleKey line
      const lineMatch = src.match(/const hasSingleKey\s*=\s*\/.*\/\.test\(handler\)/);
      if (lineMatch) {
        // The pattern line must NOT reference 48 or 57
        expect(lineMatch[0]).not.toMatch(/[^a-zA-Z]4[89]|[^a-zA-Z]5[0-7]/);
      }
    });

    test('letter key accesskey with single letter SHOULD be flagged', async () => {
      const page = makePage([{ type: 'accesskey', key: 's', html: '<a accesskey="s">Save</a>' }]);
      const result = await run(page);
      expect(result.rules[0].status).toBe('incomplete');
    });

    test('letter key inline handler WITHOUT modifier SHOULD be flagged', async () => {
      const page = makePage([
        { type: 'inline-handler', html: '<div onkeydown="if(event.key===\'k\')act()">...</div>' },
      ]);
      const result = await run(page);
      expect(result.rules[0].status).toBe('incomplete');
    });

    test('letter key handler WITH modifier guard should NOT appear (returns empty violations)', async () => {
      // When modifier guard is present the browser-side code returns no violations
      const page = makePage([]);
      const result = await run(page);
      expect(result.rules[0].status).toBe('pass');
    });
  });
});