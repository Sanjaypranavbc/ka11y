'use strict';

const { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION } = require('../../src/custom-checks/orientation.check');

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
  // ── Module exports ─────────────────────────────────────────────────────────
  test('exports SC as 1.3.4', () => { expect(SC).toBe('1.3.4'); });
  test('exports RULE_ID as custom-orientation', () => { expect(RULE_ID).toBe('custom-orientation'); });
  test('exports HELP_URL', () => { expect(HELP_URL).toContain('orientation'); });
  test('exports MODE as static', () => { expect(MODE).toBe('static'); });
  test('exports FALLBACK_DESCRIPTION', () => { expect(typeof FALLBACK_DESCRIPTION).toBe('string'); });

  // ── Pass path ──────────────────────────────────────────────────────────────
  test('passes when no orientation findings are produced', async () => {
    const page = makePage({ domFindings: [] });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('1.3.4');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].ruleId).toBe('custom-orientation');
    expect(result.rules[0].impact).toBeNull();
    expect(result.rules[0].target).toBeNull();
    expect(result.rules[0].selector).toBeNull();
    expect(result.rules[0].snippet).toBeNull();
    expect(result.rules[0].source).toBeNull();
    expect(result.rules[0].mediaQuery).toBeNull();
    expect(result.rules[0].helpUrl).toBe(HELP_URL);
  });

  // ── buildRule: definite-fail types ────────────────────────────────────────
  test('script-lock finding maps to status=fail', async () => {
    const page = makePage({
      domFindings: [{ type: 'script-lock', reason: 'lock found', selector: 'script', target: 'inline <script>' }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].ruleId).toBe('custom-orientation-script-lock');
    expect(result.rules[0].impact).toBe('serious');
    expect(result.rules[0].reason).toBe('lock found');
    expect(result.rules[0].target).toBe('inline <script>');
    expect(result.rules[0].selector).toBe('script');
  });

  test('meta-viewport-orientation finding maps to status=fail', async () => {
    const page = makePage({
      domFindings: [{
        type: 'meta-viewport-orientation',
        reason: 'viewport orientation set',
        selector: 'meta[name="viewport"]',
        snippet: '<meta name="viewport" content="orientation=portrait">',
      }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].ruleId).toBe('custom-orientation-meta-viewport');
    expect(result.rules[0].snippet).toBe('<meta name="viewport" content="orientation=portrait">');
  });

  test('manifest-orientation finding maps to status=fail', async () => {
    const page = makePage({
      domFindings: [{
        type: 'manifest-orientation',
        reason: 'manifest locks orientation',
        target: 'manifest.json',
        snippet: '"orientation": "portrait"',
      }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].ruleId).toBe('custom-orientation-manifest');
  });

  test('writing-mode finding maps to status=fail', async () => {
    const page = makePage({
      domFindings: [{
        type: 'writing-mode',
        reason: 'vertical writing mode',
        target: 'body',
      }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].ruleId).toBe('custom-orientation-writing-mode');
  });

  // ── buildRule: heuristic/incomplete types ─────────────────────────────────
  test('css-rotate finding maps to status=incomplete', async () => {
    const page = makePage({
      domFindings: [{ type: 'css-rotate', reason: 'forced rotation', selector: 'body', snippet: '<body>' }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].ruleId).toBe('custom-orientation-css-rotate');
  });

  test('css-media-hide finding maps to status=incomplete', async () => {
    const page = makePage({
      domFindings: [{ type: 'css-media-hide', reason: 'media hide', selector: '.hero', source: '<style[0]>', mediaQuery: 'orientation: portrait' }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].ruleId).toBe('custom-orientation-css-media-hide');
    expect(result.rules[0].source).toBe('<style[0]>');
    expect(result.rules[0].mediaQuery).toBe('orientation: portrait');
  });

  test('css-media-structural finding maps to status=incomplete', async () => {
    const page = makePage({
      domFindings: [{ type: 'css-media-structural', reason: 'structural css', selector: '.main' }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].ruleId).toBe('custom-orientation-css-media-structural');
  });

  test('cross-origin-sheet finding maps to status=incomplete', async () => {
    const page = makePage({
      domFindings: [{ type: 'cross-origin-sheet', reason: 'cross-origin stylesheet', target: 'https://cdn.example.com/styles.css' }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].ruleId).toBe('custom-orientation-cross-origin-sheet');
  });

  // ── buildRule: unknown type fallback ─────────────────────────────────────
  test('unknown finding type uses the type itself as ruleId suffix', async () => {
    const page = makePage({
      domFindings: [{ type: 'unknown-type', reason: 'some reason' }],
    });
    const result = await run(page);
    expect(result.rules[0].ruleId).toBe('custom-orientation-unknown-type');
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].target).toBeNull();
    expect(result.rules[0].selector).toBeNull();
    expect(result.rules[0].snippet).toBeNull();
    expect(result.rules[0].source).toBeNull();
    expect(result.rules[0].mediaQuery).toBeNull();
  });

  // ── Multiple findings ─────────────────────────────────────────────────────
  test('multiple findings each produce a rule entry', async () => {
    const page = makePage({
      domFindings: [
        { type: 'script-lock', reason: 'lock 1', selector: 'script' },
        { type: 'css-rotate',  reason: 'rotate 1', selector: 'body' },
        { type: 'css-media-hide', reason: 'hide 1', selector: '.hero' },
      ],
    });
    const result = await run(page);
    expect(result.rules).toHaveLength(3);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[1].status).toBe('incomplete');
    expect(result.rules[2].status).toBe('incomplete');
  });

  // ── Manifest path ─────────────────────────────────────────────────────────
  test('manifest with locked orientation produces manifest-orientation finding via manifestContent', async () => {
    // When manifestUrl is non-null, evaluate is called twice before domFindings
    // The manifest check runs server-side (Node); domFindings would be empty.
    // We test the manifest path by providing manifestContent with a locked orientation.
    const manifestJson = JSON.stringify({ orientation: 'portrait' });
    const page = makePage({
      manifestUrl: 'https://example.com/manifest.json',
      manifestContent: manifestJson,
      domFindings: [],
    });
    const result = await run(page);
    // manifestFindings should produce a manifest-orientation rule
    expect(result.rules.some(r => r.ruleId === 'custom-orientation-manifest')).toBe(true);
    expect(result.rules.some(r => r.status === 'fail')).toBe(true);
  });

  test('manifest with non-locked orientation produces no manifest finding', async () => {
    const manifestJson = JSON.stringify({ orientation: 'any' });
    const page = makePage({
      manifestUrl: 'https://example.com/manifest.json',
      manifestContent: manifestJson,
      domFindings: [],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
  });

  test('manifest with no orientation field produces no manifest finding', async () => {
    const manifestJson = JSON.stringify({ name: 'My App' });
    const page = makePage({
      manifestUrl: 'https://example.com/manifest.json',
      manifestContent: manifestJson,
      domFindings: [],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
  });

  test('invalid manifest JSON is silently skipped', async () => {
    const page = makePage({
      manifestUrl: 'https://example.com/manifest.json',
      manifestContent: '{ invalid JSON }',
      domFindings: [],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
  });

  test('null manifestContent is skipped', async () => {
    const page = makePage({
      manifestUrl: 'https://example.com/manifest.json',
      manifestContent: null,
      domFindings: [],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
  });

  test('null manifestUrl skips manifest fetch', async () => {
    const page = makePage({ manifestUrl: null, domFindings: [] });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
  });

  test('manifest with landscape-primary orientation produces fail finding', async () => {
    const manifestJson = JSON.stringify({ orientation: 'landscape-primary' });
    const page = makePage({
      manifestUrl: 'https://example.com/manifest.json',
      manifestContent: manifestJson,
      domFindings: [],
    });
    const result = await run(page);
    expect(result.rules.some(r => r.status === 'fail')).toBe(true);
  });

  // ── Result structure ───────────────────────────────────────────────────────
  test('result always has successCriteriaId and rules array', async () => {
    const page = makePage({ domFindings: [] });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('1.3.4');
    expect(Array.isArray(result.rules)).toBe(true);
  });

  test('does not classify maximum-scale viewport restrictions as orientation issues', () => {
    const src = require('fs').readFileSync(
      require('path').resolve(__dirname, '../../src/custom-checks/orientation.check.js'),
      'utf8'
    );
    expect(src).not.toContain('maximum-scale');
    expect(src).not.toContain('viewport-scale');
  });

  test('all locked orientation values in manifest trigger a fail', async () => {
    const lockedValues = ['portrait', 'landscape', 'portrait-primary', 'portrait-secondary', 'landscape-primary', 'landscape-secondary'];
    for (const val of lockedValues) {
      const page = makePage({
        manifestUrl: 'https://example.com/manifest.json',
        manifestContent: JSON.stringify({ orientation: val }),
        domFindings: [],
      });
      const result = await run(page);
      expect(result.rules.some(r => r.status === 'fail')).toBe(true);
    }
  });
});
