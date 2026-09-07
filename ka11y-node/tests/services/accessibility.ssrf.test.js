'use strict';

/**
 * Security regression tests for Vuln 2 (SECURITY_REVIEW_production.md):
 * SSRF via redirect / DNS-rebinding in the Puppeteer request interceptor.
 *
 * accessibility.service._installSsrfInterceptor() is the ONLY guard that runs
 * on redirect hops (the DNS-resolving _assertPublicUrl() runs only once, on the
 * caller-supplied root URL). The interceptor:
 *
 *     const { hostname } = new URL(request.url());
 *     if (_PRIVATE_IP_RE.some((re) => re.test(hostname))) { request.abort(...) }
 *     request.continue();
 *
 * only string-matches the hostname against a list of *literal* private IPs and
 * never resolves DNS. So:
 *   (a) a redirect to http://<internal-hostname>/ passes straight through, and
 *   (b) DNS rebinding (public A record at check time, private A record when
 *       Chromium connects) defeats the one-time root check.
 *
 * The Python crawler closes exactly this gap in ka11y/crawler/_ssrf_guard.py
 * by resolving every non-literal host inside the route handler.
 *
 * These tests are EXPECTED TO FAIL against the current implementation. They
 * pass once the interceptor resolves the hostname and aborts on a
 * private/reserved/link-local result.
 */

const dns = require('dns');
const { installSsrfInterceptor } = require('../../src/services/accessibility.service');

// Minimal fake Puppeteer page — captures the 'request' handler.
function fakePage() {
  let handler = null;
  return {
    on(evt, fn) { if (evt === 'request') handler = fn; },
    async fire(req) { return handler(req); },
  };
}

function fakeRequest(url) {
  return {
    url: () => url,
    aborted: null,
    continued: false,
    abort(reason) { this.aborted = reason || 'aborted'; },
    continue() { this.continued = true; },
  };
}

// Make every DNS form the fix might use resolve to `ip`.
function stubDnsResolveTo(ip) {
  const record = [{ address: ip, family: ip.includes(':') ? 6 : 4 }];
  jest.spyOn(dns, 'lookup').mockImplementation((host, opts, cb) => {
    const done = typeof opts === 'function' ? opts : cb;
    done(null, record);
  });
  jest.spyOn(dns.promises, 'lookup').mockResolvedValue(record);
}

afterEach(() => jest.restoreAllMocks());

describe('accessibility.service SSRF interceptor (Vuln 2)', () => {
  test('control: a literal private IP in the redirect URL is blocked today', async () => {
    const page = fakePage();
    installSsrfInterceptor(page);
    const req = fakeRequest('http://169.254.169.254/latest/meta-data/');
    await page.fire(req);
    expect(req.aborted).toBeTruthy(); // passes today — the existing guard catches IP literals
  });

  test('redirect to an internal DNS name resolving to a link-local IP is blocked', async () => {
    stubDnsResolveTo('169.254.169.254'); // cloud metadata endpoint
    const page = fakePage();
    installSsrfInterceptor(page);
    const req = fakeRequest('http://metadata.internal.corp/latest/meta-data/iam/security-credentials/');
    await page.fire(req);
    expect(req.aborted).toBeTruthy();   // FAILS today — hostname is not an IP literal, passes through
    expect(req.continued).toBe(false);
  });

  test('DNS-rebound hostname now pointing at an RFC-1918 address is blocked', async () => {
    stubDnsResolveTo('10.1.2.3');
    const page = fakePage();
    installSsrfInterceptor(page);
    const req = fakeRequest('http://rebind.attacker.example/');
    await page.fire(req);
    expect(req.aborted).toBeTruthy();   // FAILS today
  });

  test('control: hex-encoded loopback is normalised by URL() and blocked today', async () => {
    // new URL('http://0x7f000001/').hostname === '127.0.0.1', so the existing
    // literal-IP regex catches this one. Kept as a passing control.
    stubDnsResolveTo('127.0.0.1');
    const page = fakePage();
    installSsrfInterceptor(page);
    const req = fakeRequest('http://0x7f000001/');
    await page.fire(req);
    expect(req.aborted).toBeTruthy();
  });

  test('control: a genuine public host is still allowed', async () => {
    stubDnsResolveTo('93.184.216.34');
    const page = fakePage();
    installSsrfInterceptor(page);
    const req = fakeRequest('https://example.com/');
    await page.fire(req);
    expect(req.continued).toBe(true);
    expect(req.aborted).toBeFalsy();
  });
});
