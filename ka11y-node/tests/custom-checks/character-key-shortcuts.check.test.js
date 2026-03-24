'use strict';

const { run } = require('../../src/custom-checks/character-key-shortcuts.check');

function makePage(result) {
  return { evaluate: jest.fn().mockResolvedValue(result) };
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
    expect(result.rules[0].reason).toContain('0 accesskey shortcut(s) and 1 inline key handler');
  });

  test('reports combined accesskey and inline handler count', async () => {
    const page = makePage([
      { type: 'accesskey', key: 'a', html: '<button accesskey="a">A</button>' },
      { type: 'accesskey', key: 'b', html: '<button accesskey="b">B</button>' },
      { type: 'inline-handler', html: '<div onkeydown="go()">x</div>' },
    ]);
    const result = await run(page);
    expect(result.rules[0].reason).toContain('2 accesskey shortcut(s) and 1 inline key handler');
  });
});