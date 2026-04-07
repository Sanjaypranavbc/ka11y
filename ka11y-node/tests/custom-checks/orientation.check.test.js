'use strict';

const { run } = require('../../src/custom-checks/orientation.check');

function makePage({ manifestUrl = null, manifestContent = null, domFindings = [] } = {}) {
  let call = 0;
  return {
    evaluate: jest.fn().mockImplementation(() => {
      call += 1;
      if (call === 1) return Promise.resolve(manifestUrl);
      if (manifestUrl && call === 2) return Promise.resolve(manifestContent);
      return Promise.resolve(domFindings);
    }),
  };
}

describe('orientation.check (WCAG 1.3.4)', () => {
  test('passes when no orientation findings are produced', async () => {
    const page = makePage({ domFindings: [] });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('1.3.4');
    expect(result.rules[0].status).toBe('pass');
  });

  test('maps definite orientation locks to fail', async () => {
    const page = makePage({
      domFindings: [{ type: 'script-lock', reason: 'lock found', selector: 'script' }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].ruleId).toBe('custom-orientation-script-lock');
  });

  test('maps CSS orientation heuristics to incomplete', async () => {
    const page = makePage({
      domFindings: [{ type: 'css-media-hide', reason: 'media hide', selector: '.hero' }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].ruleId).toBe('custom-orientation-css-media-hide');
  });

  test('does not classify maximum-scale viewport restrictions as orientation issues', () => {
    const src = require('fs').readFileSync(
      require('path').resolve(__dirname, '../../src/custom-checks/orientation.check.js'),
      'utf8'
    );
    expect(src).not.toContain('maximum-scale');
    expect(src).not.toContain('viewport-scale');
  });
});
