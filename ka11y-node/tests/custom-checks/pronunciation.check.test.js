'use strict';

const { run } = require('../../src/custom-checks/pronunciation.check');

function makePage(data) {
  return { evaluate: jest.fn().mockResolvedValue(data) };
}

describe('pronunciation.check (WCAG 3.1.6)', () => {
  test('passes when the page is not applicable', async () => {
    const page = makePage({
      applicable: false,
      rubyCount: 0,
      kanjiCount: 0,
      kanjiWithRuby: 0,
      sampleKanji: [],
      htmlLang: 'en',
      cjkDensityPct: 0,
      cjkSectionIssues: [],
    });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('3.1.6');
    expect(result.rules[0].status).toBe('pass');
  });

  test('returns incomplete when ruby coverage is high but ambiguity still needs review', async () => {
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
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('manual verification');
  });

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
    expect(result.rules[0].reason).toContain('not enough to auto-fail');
  });
});
