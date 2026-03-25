'use strict';

const { run } = require('../../src/custom-checks/link-purpose.check');

function makePage(data) {
  return { evaluate: jest.fn().mockResolvedValue(data) };
}

describe('link-purpose.check (WCAG 2.4.9 AAA)', () => {
  test('passes when no links exist', async () => {
    const page = makePage({ violations: [], checkedCount: 0 });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('2.4.9');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].ruleId).toBe('custom-link-purpose');
    expect(result.rules[0].reason).toContain('No links');
  });

  test('passes when all links have descriptive text', async () => {
    const page = makePage({ violations: [], checkedCount: 5 });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('5 link(s) checked');
  });

  test('fails when links use generic text like "click here"', async () => {
    const page = makePage({
      violations: [
        { text: 'click here', html: '<a href="/docs">click here</a>', id: null },
        { text: 'read more',  html: '<a href="/more">read more</a>', id: null },
      ],
      checkedCount: 10,
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].impact).toBe('moderate');
    expect(result.rules[0].reason).toContain('2 link(s)');
    expect(result.rules[0].reason).toContain('"click here"');
  });

  test('fails when a single link uses generic text "here"', async () => {
    const page = makePage({
      violations: [{ text: 'here', html: '<a href="/x">here</a>', id: null }],
      checkedCount: 3,
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('"here"');
  });

  test('impact is null when passing', async () => {
    const page = makePage({ violations: [], checkedCount: 2 });
    const result = await run(page);
    expect(result.rules[0].impact).toBeNull();
  });
});