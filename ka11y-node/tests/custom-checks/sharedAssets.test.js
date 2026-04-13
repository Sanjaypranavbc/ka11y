'use strict';

const {
  buildKeywordPattern,
  getKeywordList,
  renderReasonTemplate,
} = require('../../src/custom-checks/sharedAssets');

describe('sharedAssets', () => {
  test('loads merged multilingual keyword lists from universal config', () => {
    const keywords = getKeywordList('consistent_help', 'help_keywords');

    expect(keywords).toContain('help');
    expect(keywords).toContain('お問い合わせ');
  });

  test('builds a safe alternation regex pattern from keyword lists', () => {
    const pattern = buildKeywordPattern(['help', 'site map', 'open(']);

    expect(pattern).toContain('help');
    expect(pattern).toContain('site map');
    expect(pattern).toContain('open\\(');
  });

  test('renders localized reason templates from universal config', () => {
    const reason = renderReasonTemplate(
      'audio_transcript',
      'no_audio',
      {},
      { lang: 'ja' },
      'fallback',
    );

    expect(reason).toBe('このページに <audio> 要素はありません。');
  });
});
