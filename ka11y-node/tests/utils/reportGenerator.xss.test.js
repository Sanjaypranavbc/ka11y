'use strict';

/**
 * Security regression tests for Vuln 1 (SECURITY_REVIEW_production.md):
 * XSS via the inline <script> block in the generated HTML report.
 *
 * reportGenerator.generateReport() interpolates JSON.stringify(findings)
 * straight into a live <script> element:
 *
 *     <script>
 *     const V=${violationsJson};
 *
 * JSON.stringify does NOT escape "<", ">" or "/", so any "</script>" sequence
 * inside attacker-influenced fields — element.html and reason are sourced
 * verbatim from the audited page's raw outerHTML (axeResultMapper.buildElement,
 * ~line 463) — terminates the report's <script> early and everything after it
 * is parsed as live HTML/JS in the ka11y-node origin.
 *
 * The report is returned as text/html with no CSP from the unauthenticated
 * route POST /api/v1/analyse-url/report.
 *
 * These tests are EXPECTED TO FAIL against the current implementation. They
 * pass once the payload is unicode-escaped (< / > / &) before being embedded,
 * or moved into a <script type="application/json"> block read with JSON.parse.
 */

const { generateReport } = require('../../src/utils/reportGenerator');

// A classic script-context breakout: close the data script, run our own.
const BREAKOUT = '</script><script>window.__pwned=1;</script>';

function findingWith(overrides = {}) {
  return {
    rule_id: 'image-alt',
    status: 'fail',
    wcag_sc: '1.1.1',
    criterion_name: 'Non-text Content',
    reason: 'Image missing alt text',
    element: { html: '<img src=x>', selector: 'img', bounding_box: null, screenshot: null },
    ...overrides,
  };
}

function report(findings) {
  return generateReport({ url: 'https://victim.example/', findings, pageScreenshot: null });
}

// Count <script ...> opening tags (not counting </script>).
const scriptOpenCount = (html) => (html.match(/<script(?:\s|>)/gi) || []).length;

describe('reportGenerator — inline <script> XSS (Vuln 1)', () => {
  test('baseline: a clean report has exactly one <script> element', () => {
    expect(scriptOpenCount(report([findingWith()]))).toBe(1);
  });

  test('breakout payload in element.html must not open a second <script>', () => {
    const html = report([findingWith({ element: { html: `<img alt="${BREAKOUT}">` } })]);
    expect(scriptOpenCount(html)).toBe(1);
    // The attacker's executable tag must not survive verbatim in the response.
    expect(html).not.toContain('<script>window.__pwned=1;</script>');
  });

  test('breakout payload in reason must not open a second <script>', () => {
    // reason is HTML-escaped in the sidebar copy, but embedded raw in the JSON block.
    const html = report([findingWith({ reason: `alt missing ${BREAKOUT}` })]);
    expect(scriptOpenCount(html)).toBe(1);
    expect(html).not.toContain('<script>window.__pwned=1;</script>');
  });

  test('a "</script>" from audited markup must not appear unescaped anywhere in the report', () => {
    const html = report([findingWith({ element: { html: BREAKOUT } })]);
    // The report has exactly one legitimate </script> (its own closing tag).
    expect((html.match(/<\/script\s*>/gi) || []).length).toBe(1);
    expect(html).not.toContain('</script><script>');
  });

  test('raw "<" from audited markup is neutralised (escaped) in the data block', () => {
    const html = report([findingWith({ element: { html: '<svg onload=alert(1)>' } })]);
    const open = html.indexOf('<script>');
    const close = html.indexOf('</script>', open);
    const block = html.slice(open + '<script>'.length, close);
    // A safe encoding emits <svg... ; the vulnerable version emits <svg... verbatim.
    expect(block).not.toContain('<svg onload=alert(1)>');
  });
});
