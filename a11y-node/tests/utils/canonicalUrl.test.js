'use strict';

const { canonicalizeUrl } = require('../../src/utils/canonicalUrl');

describe('canonicalizeUrl — parity with python a11y/utils/url_canonical.py', () => {
  test('idempotent', () => {
    const c = canonicalizeUrl('HTTPS://Example.com:443/About/#section');
    expect(canonicalizeUrl(c)).toBe(c);
  });

  test('strips fragment', () => {
    expect(canonicalizeUrl('https://example.com/a#section')).toBe('https://example.com/a');
  });

  test('lowercases host only', () => {
    expect(canonicalizeUrl('https://Example.com/About')).toBe('https://example.com/About');
  });

  test('drops default https port', () => {
    expect(canonicalizeUrl('https://example.com:443/x')).toBe('https://example.com/x');
  });

  test('drops default http port', () => {
    expect(canonicalizeUrl('http://example.com:80/x')).toBe('http://example.com/x');
  });

  test('keeps non-default port', () => {
    expect(canonicalizeUrl('https://example.com:8443/x')).toBe('https://example.com:8443/x');
  });

  test('strips trailing slash on non-root', () => {
    expect(canonicalizeUrl('https://example.com/a/')).toBe('https://example.com/a');
  });

  test('keeps trailing slash on root', () => {
    expect(canonicalizeUrl('https://example.com/')).toBe('https://example.com/');
  });

  test('strips /index.html', () => {
    expect(canonicalizeUrl('https://example.com/dir/index.html')).toBe('https://example.com/dir');
  });

  test('strips /index.htm', () => {
    expect(canonicalizeUrl('https://example.com/dir/index.htm')).toBe('https://example.com/dir');
  });

  test('does NOT strip arbitrary .html (parity with python)', () => {
    expect(canonicalizeUrl('https://example.com/about.html')).toBe('https://example.com/about.html');
  });

  test('preserves query string as-is', () => {
    expect(canonicalizeUrl('https://example.com/x?a=1&b=2')).toBe('https://example.com/x?a=1&b=2');
  });

  test('leaves non-http schemes untouched', () => {
    expect(canonicalizeUrl('mailto:x@y.z')).toBe('mailto:x@y.z');
  });

  test('returns input for malformed / empty', () => {
    expect(canonicalizeUrl('')).toBe('');
    expect(canonicalizeUrl(null)).toBe(null);
    expect(canonicalizeUrl(undefined)).toBe(undefined);
  });

  test('kao.com trailing-slash pair unifies', () => {
    expect(canonicalizeUrl('https://www.kao.com/jp/')).toBe(
      canonicalizeUrl('https://www.kao.com/jp'),
    );
  });

  test('kao.com .html vs extensionless stays distinct (documented limitation)', () => {
    // Both engines agree these are different until canonical-tag scraping
    // is added. Keep this test as a guard so a well-meaning refactor that
    // strips .html doesn't sneak in without updating the python test too.
    expect(canonicalizeUrl('https://www.kao.com/global/en/worldwide')).not.toBe(
      canonicalizeUrl('https://www.kao.com/global/en/worldwide.html'),
    );
  });
});
