'use strict';

const { run, SC, RULE_ID, HELP_URL } = require('../../src/custom-checks/pronunciation.check');

function makePage(data) {
  return { evaluate: jest.fn().mockResolvedValue(data) };
}

const NOT_APPLICABLE = {
  applicable: false,
  rubyCount: 0,
  kanjiCount: 0,
  kanjiWithRuby: 0,
  sampleKanji: [],
  htmlLang: 'en',
  cjkDensityPct: 0,
  cjkSectionIssues: [],
};

describe('pronunciation.check (WCAG 3.1.6)', () => {
  // ── Module exports ─────────────────────────────────────────────────────────
  test('exports SC as 3.1.6', () => { expect(SC).toBe('3.1.6'); });
  test('exports RULE_ID as custom-pronunciation', () => { expect(RULE_ID).toBe('custom-pronunciation'); });
  test('exports HELP_URL', () => { expect(HELP_URL).toContain('pronunciation'); });

  // ── Not applicable: non-CJK page ──────────────────────────────────────────
  test('passes when the page is not applicable (English page)', async () => {
    const page = makePage(NOT_APPLICABLE);
    const result = await run(page);
    expect(result.successCriteriaId).toBe('3.1.6');
    expect(result.rules[0].ruleId).toBe('custom-pronunciation');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('not applicable');
    expect(result.rules[0].impact).toBeNull();
    expect(result.rules[0].helpUrl).toBe(HELP_URL);
  });

  test('pass reason includes language and CJK density', async () => {
    const page = makePage({ ...NOT_APPLICABLE, htmlLang: 'fr', cjkDensityPct: 1 });
    const result = await run(page);
    expect(result.rules[0].reason).toContain('"fr"');
    expect(result.rules[0].reason).toContain('1%');
  });

  // ── Not applicable but has CJK sections ───────────────────────────────────
  test('returns incomplete when non-CJK page has CJK sections with low ruby coverage', async () => {
    const page = makePage({
      ...NOT_APPLICABLE,
      htmlLang: 'en',
      cjkSectionIssues: [
        { lang: 'ja', kanjiCount: 50, rubyPct: 10, html: '<div lang="ja">...' },
        { lang: 'zh', kanjiCount: 30, rubyPct: 5, html: '<div lang="zh">...' },
      ],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].impact).toBe('moderate');
    expect(result.rules[0].reason).toContain('section(s) with explicit CJK lang attributes');
    expect(result.rules[0].reason).toContain('2 section');
  });

  test('CJK section issues reason includes sample section details', async () => {
    const page = makePage({
      ...NOT_APPLICABLE,
      cjkSectionIssues: [
        { lang: 'ja', kanjiCount: 20, rubyPct: 15, html: '<p lang="ja">...' },
      ],
    });
    const result = await run(page);
    expect(result.rules[0].reason).toContain('lang="ja"');
    expect(result.rules[0].reason).toContain('20 kanji');
    expect(result.rules[0].reason).toContain('15% ruby coverage');
  });

  test('up to 3 CJK sections included in reason', async () => {
    const page = makePage({
      ...NOT_APPLICABLE,
      cjkSectionIssues: [
        { lang: 'ja', kanjiCount: 10, rubyPct: 0, html: '<p>' },
        { lang: 'zh', kanjiCount: 15, rubyPct: 5, html: '<p>' },
        { lang: 'ko', kanjiCount: 20, rubyPct: 10, html: '<p>' },
        { lang: 'ja', kanjiCount: 25, rubyPct: 15, html: '<p>' }, // 4th — should not appear
      ],
    });
    const result = await run(page);
    expect(result.rules[0].reason).toContain('4 section');
  });

  // ── Applicable: no kanji ──────────────────────────────────────────────────
  test('passes when CJK page has no kanji characters', async () => {
    const page = makePage({
      applicable: true,
      rubyCount: 0,
      kanjiCount: 0,
      kanjiWithRuby: 0,
      sampleKanji: [],
      htmlLang: 'ja',
      cjkDensityPct: 40,
      cjkSectionIssues: [],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('no kanji');
    expect(result.rules[0].impact).toBeNull();
  });

  test('pass reason for no-kanji includes language and density', async () => {
    const page = makePage({
      applicable: true,
      rubyCount: 0,
      kanjiCount: 0,
      kanjiWithRuby: 0,
      sampleKanji: [],
      htmlLang: 'ko',
      cjkDensityPct: 25,
      cjkSectionIssues: [],
    });
    const result = await run(page);
    expect(result.rules[0].reason).toContain('"ko"');
    expect(result.rules[0].reason).toContain('25%');
  });

  // ── Applicable: good ruby coverage ────────────────────────────────────────
  test('returns incomplete (not pass) when ruby coverage is ≥30%', async () => {
    const page = makePage({
      applicable: true,
      rubyCount: 4,
      kanjiCount: 20,
      kanjiWithRuby: 12,
      sampleKanji: [],
      htmlLang: 'ja',
      cjkDensityPct: 40,
      cjkSectionIssues: [],
    });
    const result = await run(page);
    // rubyPct = round(12/20 * 100) = 60% >= 30% → incomplete with "manual verification"
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('manual verification');
    expect(result.rules[0].impact).toBeNull();
  });

  test('good ruby coverage reason includes rubyCount and rubyPct', async () => {
    const page = makePage({
      applicable: true,
      rubyCount: 6,
      kanjiCount: 10,
      kanjiWithRuby: 8,
      sampleKanji: [],
      htmlLang: 'ja',
      cjkDensityPct: 50,
      cjkSectionIssues: [],
    });
    const result = await run(page);
    expect(result.rules[0].reason).toContain('6 <ruby>');
    expect(result.rules[0].reason).toContain('80%');
  });

  // ── Applicable: low ruby coverage ─────────────────────────────────────────
  test('returns incomplete when ruby is present but coverage is < 30%', async () => {
    const page = makePage({
      applicable: true,
      rubyCount: 1,
      kanjiCount: 100,
      kanjiWithRuby: 5,
      sampleKanji: [],
      htmlLang: 'ja',
      cjkDensityPct: 60,
      cjkSectionIssues: [],
    });
    const result = await run(page);
    // rubyPct = round(5/100 * 100) = 5% < 30%
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].impact).toBe('moderate');
    expect(result.rules[0].reason).toContain('5/100');
  });

  test('low ruby reason mentions adding furigana', async () => {
    const page = makePage({
      applicable: true,
      rubyCount: 2,
      kanjiCount: 50,
      kanjiWithRuby: 5,
      sampleKanji: [],
      htmlLang: 'ja',
      cjkDensityPct: 45,
      cjkSectionIssues: [],
    });
    const result = await run(page);
    expect(result.rules[0].reason).toMatch(/furigana|ruby/i);
  });

  // ── Applicable: no ruby at all ─────────────────────────────────────────────
  test('does not auto-fail kanji-heavy pages with no ruby', async () => {
    const page = makePage({
      applicable: true,
      rubyCount: 0,
      kanjiCount: 10,
      kanjiWithRuby: 0,
      sampleKanji: ['東京駅'],
      htmlLang: 'ja',
      cjkDensityPct: 35,
      cjkSectionIssues: [],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].impact).toBe('moderate');
    expect(result.rules[0].reason).toContain('not enough to auto-fail');
  });

  test('no-ruby reason includes sample kanji text', async () => {
    const page = makePage({
      applicable: true,
      rubyCount: 0,
      kanjiCount: 5,
      kanjiWithRuby: 0,
      sampleKanji: ['東京', '大阪', '山田'],
      htmlLang: 'ja',
      cjkDensityPct: 30,
      cjkSectionIssues: [],
    });
    const result = await run(page);
    expect(result.rules[0].reason).toContain('"東京"');
    expect(result.rules[0].reason).toContain('"大阪"');
    expect(result.rules[0].reason).toContain('"山田"');
  });

  test('no-ruby reason includes language and density', async () => {
    const page = makePage({
      applicable: true,
      rubyCount: 0,
      kanjiCount: 8,
      kanjiWithRuby: 0,
      sampleKanji: ['漢字'],
      htmlLang: 'zh',
      cjkDensityPct: 55,
      cjkSectionIssues: [],
    });
    const result = await run(page);
    expect(result.rules[0].reason).toContain('zh');
    expect(result.rules[0].reason).toContain('55%');
    expect(result.rules[0].reason).toContain('8 kanji');
  });

  // ── Result structure ───────────────────────────────────────────────────────
  test('result always has successCriteriaId and rules array', async () => {
    const result = await run(makePage(NOT_APPLICABLE));
    expect(result.successCriteriaId).toBe('3.1.6');
    expect(Array.isArray(result.rules)).toBe(true);
  });

  test('description is always set', async () => {
    const result = await run(makePage(NOT_APPLICABLE));
    expect(result.rules[0].description).toContain('Pronunciation');
  });
});
