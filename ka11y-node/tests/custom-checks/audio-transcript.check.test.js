'use strict';

const { run, SC, RULE_ID, HELP_URL } = require('../../src/custom-checks/audio-transcript.check');

function makePage(data) {
  return { evaluate: jest.fn().mockResolvedValue(data) };
}

describe('audio-transcript.check (WCAG 1.2.1)', () => {
  // ── Module exports ─────────────────────────────────────────────────────────
  test('exports SC as 1.2.1', () => { expect(SC).toBe('1.2.1'); });
  test('exports RULE_ID as custom-audio-transcript', () => { expect(RULE_ID).toBe('custom-audio-transcript'); });
  test('exports HELP_URL', () => { expect(HELP_URL).toContain('audio-only'); });

  // ── No audio ───────────────────────────────────────────────────────────────
  test('passes when no audio elements exist', async () => {
    const page = makePage({ audioCount: 0, issues: [], trackOnlyCount: 0 });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('1.2.1');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].ruleId).toBe('custom-audio-transcript');
    expect(result.rules[0].impact).toBeNull();
    expect(result.rules[0].reason).toContain('No <audio>');
    expect(result.rules[0].helpUrl).toBe(HELP_URL);
  });

  // ── All audio with transcripts ─────────────────────────────────────────────
  test('passes when all audio elements have a detectable text alternative', async () => {
    const page = makePage({ audioCount: 2, issues: [], trackOnlyCount: 0 });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].impact).toBeNull();
    expect(result.rules[0].reason).toContain('2 <audio>');
    expect(result.rules[0].reason).toContain('transcript evidence');
  });

  test('passes when 1 audio element has transcript evidence', async () => {
    const page = makePage({ audioCount: 1, issues: [], trackOnlyCount: 0 });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('1 <audio>');
  });

  // ── Missing transcripts ────────────────────────────────────────────────────
  test('returns incomplete when audio has no detectable transcript', async () => {
    const page = makePage({
      audioCount: 1,
      trackOnlyCount: 0,
      issues: [{ html: '<audio src="talk.mp3" controls></audio>', id: null, src: 'talk.mp3', hasTrack: false }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].impact).toBe('serious');
    expect(result.rules[0].reason).toContain('1 of 1');
    expect(result.rules[0].reason).toContain('no detectable transcript evidence');
  });

  test('incomplete reason includes the audio element reference (by id)', async () => {
    const page = makePage({
      audioCount: 1,
      trackOnlyCount: 0,
      issues: [{ html: '<audio id="ep1">', id: 'ep1', src: 'ep1.mp3', hasTrack: false }],
    });
    const result = await run(page);
    expect(result.rules[0].reason).toContain('<audio id="ep1">');
  });

  test('incomplete reason includes the audio element reference (by src when no id)', async () => {
    const page = makePage({
      audioCount: 1,
      trackOnlyCount: 0,
      issues: [{ html: '<audio src="talk.mp3">', id: null, src: 'talk.mp3', hasTrack: false }],
    });
    const result = await run(page);
    expect(result.rules[0].reason).toContain('<audio src="talk.mp3">');
  });

  test('incomplete reason uses html snippet when no id or src', async () => {
    const page = makePage({
      audioCount: 1,
      trackOnlyCount: 0,
      issues: [{ html: '<audio controls>', id: null, src: '', hasTrack: false }],
    });
    const result = await run(page);
    expect(result.rules[0].reason).toContain('<audio');
  });

  test('reports the correct counts when some audio is missing transcript', async () => {
    const page = makePage({
      audioCount: 3,
      trackOnlyCount: 0,
      issues: [
        { html: '<audio src="a.mp3">', id: null, src: 'a.mp3', hasTrack: false },
        { html: '<audio src="b.mp3">', id: null, src: 'b.mp3', hasTrack: false },
      ],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('2 of 3');
  });

  // ── Track-only ─────────────────────────────────────────────────────────────
  test('track-only evidence still needs manual review', async () => {
    const page = makePage({
      audioCount: 1,
      trackOnlyCount: 1,
      issues: [{ html: '<audio src="talk.mp3"><track kind="captions"></audio>', id: null, src: 'talk.mp3', hasTrack: true }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('rely only on <track> elements');
  });

  test('track-only reason includes the count', async () => {
    const page = makePage({
      audioCount: 2,
      trackOnlyCount: 2,
      issues: [
        { html: '<audio src="a.mp3">', id: null, src: 'a.mp3', hasTrack: true },
        { html: '<audio src="b.mp3">', id: null, src: 'b.mp3', hasTrack: true },
      ],
    });
    const result = await run(page);
    expect(result.rules[0].reason).toContain('2 rely only on <track>');
  });

  test('trackOnlyCount=0 does not add track-only note to reason', async () => {
    const page = makePage({
      audioCount: 1,
      trackOnlyCount: 0,
      issues: [{ html: '<audio src="x.mp3">', id: null, src: 'x.mp3', hasTrack: false }],
    });
    const result = await run(page);
    expect(result.rules[0].reason).not.toContain('rely only on <track>');
  });

  // ── Element list sampling ──────────────────────────────────────────────────
  test('incomplete reason lists up to 3 audio elements', async () => {
    const page = makePage({
      audioCount: 5,
      trackOnlyCount: 0,
      issues: [
        { html: '<audio id="a1">', id: 'a1', src: '', hasTrack: false },
        { html: '<audio id="a2">', id: 'a2', src: '', hasTrack: false },
        { html: '<audio id="a3">', id: 'a3', src: '', hasTrack: false },
        { html: '<audio id="a4">', id: 'a4', src: '', hasTrack: false }, // 4th — not shown
      ],
    });
    const result = await run(page);
    expect(result.rules[0].reason).toContain('<audio id="a1">');
    expect(result.rules[0].reason).toContain('<audio id="a2">');
    expect(result.rules[0].reason).toContain('<audio id="a3">');
    expect(result.rules[0].reason).not.toContain('<audio id="a4">');
  });

  // ── Description ───────────────────────────────────────────────────────────
  test('description is consistent', async () => {
    const pass = await run(makePage({ audioCount: 0, issues: [], trackOnlyCount: 0 }));
    expect(pass.rules[0].description).toContain('text alternative');

    const incomplete = await run(makePage({
      audioCount: 1, trackOnlyCount: 0,
      issues: [{ html: '<audio>', id: null, src: '', hasTrack: false }],
    }));
    expect(incomplete.rules[0].description).toContain('text alternative');
  });

  // ── Source validation ─────────────────────────────────────────────────────
  test('impact is null when passing', async () => {
    const page = makePage({ audioCount: 0, issues: [], trackOnlyCount: 0 });
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

  test('source checks for aria-describedby as transcript evidence', () => {
    const src = require('fs').readFileSync(
      require('path').resolve(__dirname, '../../src/custom-checks/audio-transcript.check.js'),
      'utf8'
    );
    expect(src).toContain('aria-describedby');
  });

  test('source checks for <details> element transcript evidence', () => {
    const src = require('fs').readFileSync(
      require('path').resolve(__dirname, '../../src/custom-checks/audio-transcript.check.js'),
      'utf8'
    );
    expect(src).toContain('hasDetailsTranscript');
  });
});
