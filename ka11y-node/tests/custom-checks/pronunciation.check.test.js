'use strict';

const {
  MODE,
  run,
} = require('../../src/custom-checks/pronunciation.check');

function makePage(data) {
  return { evaluate: jest.fn().mockResolvedValue(data) };
}

describe('pronunciation.check (WCAG 3.1.6)', () => {
  test('declares explicit static mode metadata', () => {
    expect(MODE).toBe('static');
  });

  test('passes when pronunciation is not applicable to a non-CJK page', async () => {
    const page = makePage({
      applicable: false,
      htmlLang: 'en',
      cjkDensityPct: 0,
      cjkSectionIssues: [],
    });
    const result = await run(page);

    expect(result.successCriteriaId).toBe('3.1.6');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('Pronunciation is not applicable');
  });

  test('returns needs review for low ruby coverage in explicit CJK sections', async () => {
    const page = makePage({
      applicable: false,
      htmlLang: 'en',
      cjkDensityPct: 2,
      cjkSectionIssues: [
        { lang: 'ja', kanjiCount: 12, rubyPct: 0, html: '<section lang="ja">漢字</section>' },
      ],
    });
    const result = await run(page);

    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('[lang="ja"]');
    expect(result.rules[0].reason).toContain('ruby coverage');
  });

  test('fails when a Japanese page has no ruby support for kanji text', async () => {
    const page = makePage({
      applicable: true,
      rubyCount: 0,
      kanjiCount: 18,
      kanjiWithRuby: 0,
      sampleKanji: ['東京都庁', '障害者支援'],
      htmlLang: 'ja',
      cjkDensityPct: 68,
      cjkSectionIssues: [],
    });
    const result = await run(page);

    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].reason).toContain('No <ruby> elements');
    expect(result.rules[0].reason).toContain('東京都庁');
  });

  test('localizes rendered reason text when lang=ja', async () => {
    const page = makePage({
      applicable: false,
      htmlLang: 'en',
      cjkDensityPct: 1,
      cjkSectionIssues: [],
    });
    const result = await run(page, { lang: 'ja' });

    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('適用対象外');
  });
});
