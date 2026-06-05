'use strict';

const { StageTimings, NULL_TIMINGS } = require('../../src/utils/stageTimings');

describe('StageTimings.record', () => {
  test('appends one row per call with default values', () => {
    const t = new StageTimings();
    t.record({ stage: 'axe_core', duration_ms: 12.5, page_url: 'https://a.com' });
    expect(t.rows).toHaveLength(1);
    expect(t.rows[0]).toEqual(
      expect.objectContaining({
        stage: 'axe_core',
        sub_stage: null,
        page_url: 'https://a.com',
        duration_ms: 12.5,
        status: 'ok',
        source: 'node',
      }),
    );
  });

  test('NULL_TIMINGS swallows all calls', () => {
    NULL_TIMINGS.record({ stage: 'x', duration_ms: 1 });
    expect(NULL_TIMINGS.rows).toHaveLength(0);
  });

  test('rounds duration_ms to 3 decimals to mirror the python schema', () => {
    const t = new StageTimings();
    t.record({ stage: 's', duration_ms: 1.234567 });
    expect(t.rows[0].duration_ms).toBe(1.235);
  });
});

describe('StageTimings.time', () => {
  test('records ok status when the function resolves', async () => {
    const t = new StageTimings();
    const result = await t.time(
      { stage: 'axe_core', sub_stage: 'page_navigate', page_url: 'https://a.com' },
      async () => {
        await new Promise((r) => setTimeout(r, 5));
        return 42;
      },
    );
    expect(result).toBe(42);
    expect(t.rows).toHaveLength(1);
    expect(t.rows[0].status).toBe('ok');
    expect(t.rows[0].duration_ms).toBeGreaterThanOrEqual(4);
  });

  test('records error status, captures message, and re-throws', async () => {
    const t = new StageTimings();
    await expect(
      t.time(
        { stage: 'axe_core', sub_stage: 'axe_run', page_url: 'https://a.com' },
        async () => {
          throw new Error('boom');
        },
      ),
    ).rejects.toThrow('boom');
    expect(t.rows).toHaveLength(1);
    expect(t.rows[0].status).toBe('error');
    expect(t.rows[0].error).toBe('boom');
  });
});
