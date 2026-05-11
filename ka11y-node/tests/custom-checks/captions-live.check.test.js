'use strict';

const { run } = require('../../src/custom-checks/captions-live.check');

function makePage(data) {
  return { evaluate: jest.fn().mockResolvedValue(data) };
}

describe('captions-live.check (WCAG 1.2.4)', () => {
  test('passes when no live streams exist', async () => {
    const page = makePage({ liveCount: 0, unverifiedLiveCount: 0, issues: [] });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('No live audio/video streams');
  });

  test('passes when live streams have captions and are verified', async () => {
    const page = makePage({ liveCount: 1, unverifiedLiveCount: 0, issues: [] });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('1 live media stream(s) checked');
  });

  test('returns incomplete when live stream has no captions', async () => {
    const page = makePage({
      liveCount: 1,
      unverifiedLiveCount: 0,
      issues: [{ html: '<video data-wcag-live-captions="true"></video>' }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
  });

  test('returns needs_review when captions exist but liveness is unverified', async () => {
    const page = makePage({ liveCount: 1, unverifiedLiveCount: 1, issues: [] });
    const result = await run(page);
    expect(result.rules[0].status).toBe('needs_review');
    expect(result.rules[0].reason).toBe('cannot verify captions are live; appears prerecorded');
  });
});
