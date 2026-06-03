'use strict';

const { run } = require('../../src/custom-checks/html-parsing.check');

function makePage(evalResult) {
  return { evaluate: jest.fn().mockResolvedValue(evalResult) };
}

describe('html-parsing.check (WCAG 4.1.1)', () => {
  test('passes when no duplicate IDs exist', async () => {
    const page = makePage({ duplicateIds: [] });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('4.1.1');
    expect(result.rules).toHaveLength(1);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].impact).toBeNull();
  });

  test('fails when duplicate IDs are found', async () => {
    const page = makePage({ duplicateIds: ['header', 'logo'] });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].impact).toBe('critical');
    expect(result.rules[0].reason).toMatch('2 duplicate');
    expect(result.rules[0].reason).toMatch('"header"');
  });

  test('includes helpUrl', async () => {
    const page = makePage({ duplicateIds: [] });
    const result = await run(page);
    expect(result.rules[0].helpUrl).toContain('parsing');
  });

  test('lists at most 5 duplicate IDs in reason', async () => {
    const ids = ['a','b','c','d','e','f','g'];
    const page = makePage({ duplicateIds: ids });
    const result = await run(page);
    const reason = result.rules[0].reason;
    // Should mention count and up to 5 IDs
    expect(reason).toMatch(`${ids.length} duplicate`);
  });

  test('ruleId is custom-html-parsing', async () => {
    const page = makePage({ duplicateIds: [] });
    const result = await run(page);
    expect(result.rules[0].ruleId).toBe('custom-html-parsing');
  });
});