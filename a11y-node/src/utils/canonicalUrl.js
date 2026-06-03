/**
 * src/utils/canonicalUrl.js
 * =========================
 * JS port of a11y-python's `a11y/utils/url_canonical.py`. The two engines
 * must agree on a single canonical form for page_url, otherwise the page-wise
 * report UI groups findings under different tabs for what the user considers
 * the same page (e.g. trailing-slash vs not).
 *
 * Keep these rules in lock-step with the Python version. If you change one,
 * change both — there is a test (test_url_canonical.py + canonicalUrl.test.js)
 * exercising the same input set in each.
 *
 * Rules applied:
 *   - lowercase scheme + host
 *   - drop default ports (:80 for http, :443 for https)
 *   - strip fragment
 *   - strip trailing "/" on non-root paths
 *   - strip "/index.html" / "/index.htm" from path tail
 *
 * Not applied (matches Python):
 *   - stripping arbitrary ".html" extensions (the kao.com /worldwide vs
 *     /worldwide.html collision needs canonical-tag scraping; deferred)
 *   - query parameter ordering
 *   - percent-encoding normalisation
 *
 * Safety: never throws. A malformed URL is returned unchanged so callers can
 * keep using it as an opaque key.
 */

'use strict';

const DEFAULT_PORTS = { 'http:': '80', 'https:': '443' };
const INDEX_SUFFIXES = ['/index.html', '/index.htm'];

function canonicalizeUrl(url) {
  if (typeof url !== 'string' || url.length === 0) {
    return url;
  }
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return url;
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    // Leave mailto:, tel:, data:, etc. alone — they have their own grammars.
    return url;
  }

  // Hostname: WHATWG URL already lowercases it, but be explicit.
  const hostname = parsed.hostname.toLowerCase();
  if (!hostname) {
    return url;
  }

  // Drop default port.
  let port = parsed.port;
  if (port && DEFAULT_PORTS[parsed.protocol] === port) {
    port = '';
  }

  // Path: strip /index.html or /index.htm; strip trailing slash on non-root.
  let path = parsed.pathname || '/';
  const lowerPath = path.toLowerCase();
  for (const suffix of INDEX_SUFFIXES) {
    if (lowerPath.endsWith(suffix)) {
      path = path.slice(0, -suffix.length) || '/';
      break;
    }
  }
  if (path.length > 1 && path.endsWith('/')) {
    path = path.slice(0, -1);
  }

  // userinfo is rare in crawled URLs; keep it intact if present.
  let userinfo = '';
  if (parsed.username) {
    userinfo = parsed.username;
    if (parsed.password) {
      userinfo += `:${parsed.password}`;
    }
    userinfo += '@';
  }

  const portPart = port ? `:${port}` : '';
  const query = parsed.search || '';

  return `${parsed.protocol}//${userinfo}${hostname}${portPart}${path}${query}`;
}

module.exports = { canonicalizeUrl };
