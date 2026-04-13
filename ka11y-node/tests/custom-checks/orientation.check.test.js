'use strict';

const { run } = require('../../src/custom-checks/orientation.check');

function makePage(...values) {
  return {
    evaluate: jest.fn()
      .mockResolvedValueOnce(values[0])
      .mockResolvedValueOnce(values[1])
      .mockResolvedValueOnce(values[2]),
  };
}

describe('orientation.check (WCAG 1.3.4)', () => {
  test('passes when no manifest or DOM orientation locks are found', async () => {
    const page = makePage(null, null, []);
    const result = await run(page);

    expect(result.successCriteriaId).toBe('1.3.4');
    expect(result.rules).toHaveLength(1);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].ruleId).toBe('custom-orientation');
  });

  test('fails for manifest orientation locks and preserves structured evidence', async () => {
    const page = makePage(
      'https://example.com/manifest.json',
      JSON.stringify({ orientation: 'portrait' }),
      [],
    );
    const result = await run(page);

    expect(result.rules).toHaveLength(1);
    expect(result.rules[0]).toMatchObject({
      ruleId: 'custom-orientation-manifest',
      status: 'fail',
      target: 'manifest.json',
    });
    expect(result.rules[0].snippet).toContain('"orientation": "portrait"');
  });

  test('marks CSS orientation media queries as needs review', async () => {
    const page = makePage(null, null, [{
      type: 'css-media-structural',
      target: '.app-shell',
      selector: '.app-shell',
      snippet: '.app-shell { overflow: hidden; }',
      source: 'https://example.com/app.css',
      mediaQuery: '(orientation: landscape)',
      reason: 'Structural CSS may break layout in landscape orientation.',
    }]);
    const result = await run(page);

    expect(result.rules).toHaveLength(1);
    expect(result.rules[0]).toMatchObject({
      ruleId: 'custom-orientation-css-media-structural',
      status: 'incomplete',
      selector: '.app-shell',
      source: 'https://example.com/app.css',
      mediaQuery: '(orientation: landscape)',
    });
  });
});
