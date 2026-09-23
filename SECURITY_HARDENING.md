# ka11y — transport, session and abuse hardening (2026-09-23)

What is enforced in code, what is left to the platform, where it can still go
wrong, and every error the API can answer with. Companion to
`SECURITY_REVIEW_production.md` (application-layer findings) and the Kao
security sheets in `~/Downloads/security_audit_build`.

## 1. What changed on 2026-09-23

| Area | Before | Now |
|---|---|---|
| Cookie contents | HMAC-SHA256 signed, payload readable | AES-256-GCM sealed (`ka11y/auth/signing.py`), key from `KA11Y_SESSION_SECRET` via HKDF-SHA256; tampering, forgery and old-format cookies are refused |
| Session id in the database | The row id in the cookie **was** the credential | Cookie carries row id + random 256-bit bearer token; DB stores only `sha256(token)` (`user_sessions.token_hash`, migration 0003). A dump of the table, even with the session secret, cannot mint a cookie |
| Cookie names | `ka11y_session`, `ka11y_oidc` | `__Host-ka11y_session`, `__Host-ka11y_oidc` on https (browser enforces Secure + Path=/ + no Domain); plain names stay for http localhost |
| Sessions per user | Unlimited | `KA11Y_SESSION_MAX_PER_USER` (default 5); the least recently active is ended |
| HSTS | None | 1 year on every https response from the API and the UI; `KA11Y_HSTS_PRELOAD=1` adds `includeSubDomains; preload` |
| CSP | None | API: `default-src 'none'; frame-ancestors 'none'; …`. UI: `frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'; upgrade-insecure-requests` |
| Other headers | nosniff, DENY, Referrer-Policy | plus Permissions-Policy, COOP, CORP, X-Permitted-Cross-Domain-Policies, `X-Powered-By` removed |
| http → https | None | 308 redirect when `KA11Y_FORCE_HTTPS` (defaults on with an https redirect URI); loopback and `/api/v1/health` exempt |
| Proxy awareness | Uvicorn ignored `X-Forwarded-*` | `--proxy-headers --forwarded-allow-ips *` so scheme, Secure cookies, HSTS and the rate limiter see the real client |
| PostgreSQL TLS | Only if the operator remembered `?sslmode=require` | Any non-local host gets `sslmode=require` automatically; `KA11Y_DB_SSLMODE=verify-full` + `KA11Y_DB_SSLROOTCERT` pins the CA |
| Request flood | 30 POST/min/IP, table grew without bound | POST bucket + auth bucket (`KA11Y_RATE_LIMIT_POST` / `KA11Y_RATE_LIMIT_AUTH`), idle IPs swept, per (IP, e-mail) brute-force brake kept |
| Body size | Unlimited | `KA11Y_MAX_BODY_BYTES` (2 MiB) → 413, declared or chunked |
| Connections | Unlimited | `--limit-concurrency 512 --timeout-keep-alive 5` → 503 past the cap |
| TLS termination | Not in the repo | `docker-compose.tls.yml` + `deploy/tls/Caddyfile`: Let's Encrypt, TLS 1.2+, http→https, edge rate limits, host ports withdrawn from ui/python/node/postgres |

Everything switches on from one setting: an `https://` `KA11Y_OIDC_REDIRECT_URI`
turns on Secure and `__Host-` cookies, HSTS and the https redirect. Rotating
`KA11Y_SESSION_SECRET` (or deploying migration 0003) signs everyone out once.

## 2. Where it can still go wrong

Ordered by how likely each is to bite, with what to do.

### Transport
1. **TLS terminated at an ALB but the target group speaks http to the container.** Fine, provided the ALB forwards `X-Forwarded-Proto: https`; Uvicorn now trusts it. If the flag is dropped from the Dockerfile CMD, every response loses HSTS and the Secure cookie logic thinks it is on http.
2. **`--forwarded-allow-ips *` with port 8000 published to the internet.** Anyone can then spoof their IP to the rate limiter and their scheme to the https redirect. The TLS overlay withdraws the port; on ECS keep the task in a private subnet. Narrow the flag to the proxy CIDR when in doubt.
3. **HSTS preload is one-way.** Do not set `KA11Y_HSTS_PRELOAD=1` until every sub-domain of the apex is https forever.
4. **CORS origins are hard-coded in `ka11y/main.py`** and still include the plain-http EC2 hostname. Remove it once the edge is live; anything served over http will be redirected anyway.
5. **Node (axe) ↔ Python and Python ↔ PostgreSQL inside compose are plain http/tcp** on the private bridge network. Acceptable on one host; across hosts (ECS/RDS) use the `sslmode` default and a TLS-enabled Node listener or a service mesh.
6. **Postgres `sslmode=require` does not verify the server certificate.** Use `verify-full` with the RDS CA bundle for production.

### Sessions and cookies
7. **`KA11Y_SESSION_SECRET` is the root of trust.** Short (<32 chars) → sign-in fails closed with a startup error. Leaked → attacker still needs a live row's token pre-image, but can forge OIDC state cookies; rotate immediately. Store it in AWS Secrets Manager / SSM, never in an image.
8. **Logout ends one session; password change should end all.** `sessions.end_all_for_user` exists; wire it to the (still missing) password-change screen.
9. **No CSRF token.** Mitigated by `SameSite=Lax` and `form-action 'self'`, which blocks cross-site POST from top-level navigations in modern browsers. A double-submit token is still on the Kao gap list.
10. **In-memory brute-force brake and rate limiter are per process.** With two API replicas the effective limit doubles. Move to Redis or rely on WAF before scaling out.
11. **Session rows keep IP and user-agent** (needed for the admin console and forensics). They are personal data under GDPR/APPI: covered by the 30-day retention only if a purge job runs; add one or document the retention.

### Data at rest
12. **PostgreSQL disk encryption is a platform setting** (RDS: KMS on; compose: the host's LUKS/EBS encryption). The app cannot encrypt the volume itself. Password hashes are scrypt; OAuth rows hold no tokens; session rows hold only token hashes.
13. **SQLite run store and artifacts** live on volumes; S3 uploads are SSE when `KA11Y_S3_SSE` is set. Keep the bucket policy `aws:SecureTransport` only.
14. **Backups** of the DB are as sensitive as the DB. Encrypt snapshots and restrict who can restore.

### Abuse / availability
15. **Audit jobs are the real cost.** One POST can pin a Chromium for minutes. The POST bucket (30/min/IP) is generous for a pilot; lower it, and use the durable queue's `KA11Y_MAX_CONCURRENT_JOBS` as the hard cap.
16. **SSRF guard** blocks private targets for audits; keep `--allow-private-hosts` off outside the CLI.
17. **Admin SSE streams hold a connection each**; `--limit-concurrency 512` covers a pilot, not a public launch.
18. **Volumetric DDoS is not solvable in the app.** Use AWS Shield Standard (free with ALB/CloudFront) + WAF rate rules, or the Caddy edge limits when self-hosting.

### Process
19. **The GitHub repo was public on 2026-09-18.** Re-check before the LEON assessment.
20. **Secrets in `.env` on the EC2 host** are readable by anyone with shell access. Prefer SSM Parameter Store injected at start.
21. **Dependency drift**: `cryptography` is now pinned in `pyproject.toml`; run `poetry lock` and rebuild after any change.

## 3. Every error the API can answer with

### HTTP status codes

| Status | Where | Meaning |
|---|---|---|
| 200 | everywhere | OK |
| 201 | `POST /api/v1/auth/password/register` | Account created and signed in |
| 202 | `POST /api/v1/combined`, pipeline, crawl | Job accepted, poll for status |
| 204 | `POST /api/v1/auth/logout` | Signed out, cookies cleared |
| 302 | `/api/v1/auth/login`, `/callback`, `GET /logout` | Redirect to the identity provider, the app, or `/login?error=…` |
| 308 | any plain-http request when `KA11Y_FORCE_HTTPS` | Permanent redirect to the https URL |
| 400 | audit routes, `/audits` | Bad URL / hostname / options; not a member of an organisation; bad `Content-Length` |
| 401 | any protected route | No cookie, forged or expired session, wrong password (`{"error": "invalid_credentials"}`) |
| 403 | auth, admin | Not allow-listed, suspended, registration/login disabled, admin only |
| 404 | jobs, assets, reports, admin | Unknown job / asset / report / image |
| 409 | register | `account_exists` |
| 413 | any request | Body over `KA11Y_MAX_BODY_BYTES` |
| 422 | any JSON body | FastAPI validation failure (field list in `detail`) |
| 429 | POST anywhere, auth surface, password login | Rate limit or brute-force brake; `Retry-After` header set |
| 500 | audit, rule evaluator | Node service error, unexpected failure |
| 503 | auth, admin, history, assets, uvicorn | Not configured (OIDC / password / PostgreSQL), store unavailable, or connection cap hit |

### Auth error codes (JSON `error` on password routes, `?error=` on the login page)

| Code | Status | Cause |
|---|---|---|
| `invalid_credentials` | 401 | Wrong e-mail or password (never says which) |
| `no_password` | 403 | OIDC-only account tried the password form |
| `not_allowed` | 403 | E-mail not on the allow-list / domain list |
| `account_suspended` | 403 | `users.status != active` |
| `login_disabled` | 403 | `KA11Y_PASSWORD_LOGIN=0` |
| `register_disabled` | 403 | `KA11Y_PASSWORD_REGISTRATION=0` |
| `weak_password` | 400 | Fails `password_policy_error` |
| `account_exists` | 409 | Registration for an existing address |
| `too_many_attempts` | 429 | >10 failures per (IP, e-mail) in 15 min |
| `internal_error` | 500 | Unexpected exception; logged with traceback |
| `state_mismatch` | 302 → `/login` | OIDC state/nonce cookie missing, tampered, or from another browser |
| `state_expired` | 302 → `/login` | More than 10 min between `/login` and `/callback` |
| `provider_error` | 302 → `/login` | Provider returned `error=` or no `code` |
| `provider_unavailable` | 302 → `/login` | OIDC discovery failed |
| `exchange_failed` | 302 → `/login` | Token endpoint rejected the code / PKCE verifier |
| `invalid_id_token` | 302 → `/login` | ID token signature, issuer, audience or nonce wrong |
| `no_email` | 302 → `/login` | Provider returned no (verified) e-mail |
| `session_expired` | UI only | API answered 401 on a page; UI ends the session and shows the login form |

### Start-up errors (logged, never served)

| Message | Fix |
|---|---|
| `KA11Y_SESSION_SECRET is not set` / `must be at least 32 characters` | `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` into `ka11y-python/.env` |
| `KA11Y_COOKIE_SECURE is off` (warning) | Expected on localhost only |
| `DATABASE_URL is not set` | Auth reports "not configured" (503) until set |

## 4. Running it

```bash
# Local (plain http, cookies not Secure):
docker compose up --build

# Self-hosted TLS (EC2): needs DNS for KA11Y_PUBLIC_HOST → this box, ports 80/443 open
export KA11Y_PUBLIC_HOST=a11y.bluecaffeine.in KA11Y_ACME_EMAIL=ops@bluecaffeine.com
docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d --build

# Verify
curl -sI https://a11y.bluecaffeine.in/ | grep -iE "strict-transport|content-security|set-cookie"
curl -sI http://a11y.bluecaffeine.in/api/v1/auth/config   # → 308 to https

# Tests (no DB needed for the first two files)
cd ka11y-python
poetry run pytest tests/test_signing.py tests/test_transport.py
DATABASE_URL=postgresql://ka11y:ka11y@127.0.0.1:55432/ka11y poetry run pytest tests/test_auth.py
```
