'use strict';

const { run } = require('../../src/custom-checks/audio-transcript.check');

function makePage(data) {
  return { evaluate: jest.fn().mockResolvedValue(data) };
}

describe('audio-transcript.check (WCAG 1.2.1)', () => {
  test('passes when no audio elements exist', async () => {
    const page = makePage({ audioCount: 0, issues: [] });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('1.2.1');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].ruleId).toBe('custom-audio-transcript');
    expect(result.rules[0].reason).toContain('No <audio>');
  });

  test('passes when all audio elements have a detectable text alternative', async () => {
    const page = makePage({ audioCount: 2, issues: [] });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('2 <audio>');
  });

  test('returns incomplete when audio has no detectable transcript', async () => {
    const page = makePage({
      audioCount: 1,
      issues: [{ html: '<audio src="talk.mp3" controls></audio>' }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].impact).toBe('serious');
    expect(result.rules[0].reason).toContain('1 of 1');
    expect(result.rules[0].reason).toContain('no <track>');
  });

  test('reports the correct counts when some audio is missing transcript', async () => {
    const page = makePage({
      audioCount: 3,
      issues: [
        { html: '<audio src="a.mp3" controls></audio>' },
        { html: '<audio src="b.mp3" controls></audio>' },
      ],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('2 of 3');
  });

  test('impact is null when passing', async () => {
    const page = makePage({ audioCount: 0, issues: [] });
    const result = await run(page);
    expect(result.rules[0].impact).toBeNull();
  });

  test('includes Japanese transcript keywords in source heuristics', () => {
    const src = require('fs').readFileSync(
      require('path').resolve(__dirname, '../../src/custom-checks/audio-transcript.check.js'),
      'utf8'
    );
    expect(src).toContain('文字起こし');
    expect(src).toContain('トランスクリプト');
    expect(src).toContain('字幕');
  });
});
