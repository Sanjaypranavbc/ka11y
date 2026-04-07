'use strict';

const { run, SC, RULE_ID, HELP_URL } = require('../../src/custom-checks/link-purpose.check');

function makePage(data) {
  return { evaluate: jest.fn().mockResolvedValue(data) };
}

describe('link-purpose.check (WCAG 2.4.9 AAA)', () => {
  // ── Module exports ─────────────────────────────────────────────────────────
  test('exports SC as 2.4.9', () => { expect(SC).toBe('2.4.9'); });
  test('exports RULE_ID as custom-link-purpose', () => { expect(RULE_ID).toBe('custom-link-purpose'); });
  test('exports HELP_URL', () => { expect(HELP_URL).toContain('link-purpose'); });

  // ── Pass: no links ─────────────────────────────────────────────────────────
  test('passes when no links exist', async () => {
    const page = makePage({ violations: [], checkedCount: 0 });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('2.4.9');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].ruleId).toBe('custom-link-purpose');
    expect(result.rules[0].reason).toContain('No links');
    expect(result.rules[0].impact).toBeNull();
    expect(result.rules[0].helpUrl).toBe(HELP_URL);
  });

  // ── Pass: descriptive links ─────────────────────────────────────────────────
  test('passes when all links have descriptive text', async () => {
    const page = makePage({ violations: [], checkedCount: 5 });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('5 link(s) checked');
    expect(result.rules[0].reason).toContain('none use generic');
  });

  test('passes with 1 descriptive link', async () => {
    const page = makePage({ violations: [], checkedCount: 1 });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('1 link(s) checked');
  });

  // ── Fail: generic text ─────────────────────────────────────────────────────
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
    expect(result.rules[0].reason).toContain('"read more"');
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

  test('fail reason includes suggestion to replace with descriptive text', async () => {
    const page = makePage({
      violations: [{ text: 'more', html: '<a href="/y">more</a>', id: null }],
      checkedCount: 2,
    });
    const result = await run(page);
    expect(result.rules[0].reason).toMatch(/descriptive|aria-label/i);
  });

  test('fail result lists up to 3 sample texts', async () => {
    const page = makePage({
      violations: [
        { text: 'click here',  html: '<a>1</a>', id: null },
        { text: 'read more',   html: '<a>2</a>', id: null },
        { text: 'learn more',  html: '<a>3</a>', id: null },
        { text: 'details',     html: '<a>4</a>', id: null },
      ],
      checkedCount: 20,
    });
    const result = await run(page);
    expect(result.rules[0].reason).toContain('4 link(s)');
    expect(result.rules[0].reason).toContain('"click here"');
    expect(result.rules[0].reason).toContain('"read more"');
    expect(result.rules[0].reason).toContain('"learn more"');
    // 4th not shown (only 3 sampled)
    expect(result.rules[0].reason).not.toContain('"details"');
  });

  // ── Result structure ───────────────────────────────────────────────────────
  test('impact is null when passing', async () => {
    const page = makePage({ violations: [], checkedCount: 2 });
    const result = await run(page);
    expect(result.rules[0].impact).toBeNull();
  });

  test('fail result has impact: moderate', async () => {
    const page = makePage({
      violations: [{ text: 'go', html: '<a>go</a>', id: null }],
      checkedCount: 1,
    });
    const result = await run(page);
    expect(result.rules[0].impact).toBe('moderate');
  });

  test('description is consistent across pass and fail', async () => {
    const passResult = await run(makePage({ violations: [], checkedCount: 0 }));
    const failResult = await run(makePage({
      violations: [{ text: 'here', html: '<a>here</a>', id: null }],
      checkedCount: 1,
    }));
    expect(passResult.rules[0].description).toContain('determinable from link text alone');
    expect(failResult.rules[0].description).toContain('determinable from link text alone');
  });

  test('evaluate is called with MAX_LINKS (100) and GENERIC_LINK_RE', async () => {
    const page = makePage({ violations: [], checkedCount: 0 });
    await run(page);
    expect(page.evaluate).toHaveBeenCalledWith(expect.any(Function), 100, expect.any(String));
  });

  test('successCriteriaId is 2.4.9 for fail path too', async () => {
    const result = await run(makePage({
      violations: [{ text: 'click', html: '<a>click</a>', id: null }],
      checkedCount: 1,
    }));
    expect(result.successCriteriaId).toBe('2.4.9');
  });

  test('helpUrl is included in fail result', async () => {
    const result = await run(makePage({
      violations: [{ text: 'here', html: '<a>here</a>', id: null }],
      checkedCount: 1,
    }));
    expect(result.rules[0].helpUrl).toBe(HELP_URL);
  });
});
