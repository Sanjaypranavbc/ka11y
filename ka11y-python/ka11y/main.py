#!/usr/bin/env python3

import asyncio
import json
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse, RedirectResponse

from ka11y.api.router import router
from ka11y.api.v1.combined import _evict_old_jobs
from ka11y.config.logger import setup_logger
from ka11y.utils.config_loader import load_config

load_dotenv()


class _RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding-window request brake, per client IP, in-process.

    Two buckets:
      * POST anywhere (the expensive audit jobs): KA11Y_RATE_LIMIT_POST per
        minute, default 30.
      * The sign-in surface (POST /api/v1/auth/*, GET /api/v1/auth/login):
        KA11Y_RATE_LIMIT_AUTH per minute, default 20 — on top of the per
        (IP, e-mail) brute-force brake inside the auth router.
    Over the limit → 429 with Retry-After. Idle IPs are swept so the table
    cannot be grown without bound by a scanner cycling source addresses.

    This is the last line, not the first: volumetric floods are absorbed at
    the edge (AWS WAF / ALB, or the Caddy rate limiter in
    deploy/tls/Caddyfile) before they reach a Python worker.
    """

    _MAX_REQUESTS: int = int(os.getenv("KA11Y_RATE_LIMIT_POST", "30"))
    _MAX_AUTH_REQUESTS: int = int(os.getenv("KA11Y_RATE_LIMIT_AUTH", "20"))
    _WINDOW_SECONDS: int = 60
    _SWEEP_EVERY: int = 500
    _AUTH_PREFIX = "/api/v1/auth/"

    def __init__(self, app):
        super().__init__(app)
        self._timestamps: dict[str, list[float]] = defaultdict(list)
        self._auth_timestamps: dict[str, list[float]] = defaultdict(list)
        self._since_sweep = 0

    def _sweep(self, now: float) -> None:
        cutoff = now - self._WINDOW_SECONDS
        for table in (self._timestamps, self._auth_timestamps):
            for ip in [ip for ip, ts in table.items() if not ts or ts[-1] <= cutoff]:
                del table[ip]

    def _over(self, table: dict[str, list[float]], ip: str, limit: int, now: float) -> bool:
        window_start = now - self._WINDOW_SECONDS
        stamps = [t for t in table[ip] if t > window_start]
        if len(stamps) >= limit:
            table[ip] = stamps
            return True
        stamps.append(now)
        table[ip] = stamps
        return False

    async def dispatch(self, request: StarletteRequest, call_next):
        path = request.url.path
        is_auth = path.startswith(self._AUTH_PREFIX) and (
            request.method == "POST" or path == self._AUTH_PREFIX + "login"
        )
        if request.method != "POST" and not is_auth:
            return await call_next(request)

        # uvicorn --proxy-headers already swapped in the X-Forwarded-For client.
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        self._since_sweep += 1
        if self._since_sweep >= self._SWEEP_EVERY:
            self._since_sweep = 0
            self._sweep(now)

        limited = (is_auth and self._over(self._auth_timestamps, ip, self._MAX_AUTH_REQUESTS, now)) or (
            request.method == "POST" and self._over(self._timestamps, ip, self._MAX_REQUESTS, now)
        )
        if limited:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please slow down."},
                headers={"Retry-After": str(self._WINDOW_SECONDS)},
            )
        return await call_next(request)


class _BodyLimitMiddleware:
    """Pure-ASGI request body cap (KA11Y_MAX_BODY_BYTES, default 2 MiB).

    A declared Content-Length above the cap is refused with 413 before a
    byte is read; a chunked body is counted as it streams and cut off at the
    same point. Audit requests are a URL plus options, so 2 MiB is generous;
    raise it only for an endpoint that genuinely uploads.
    """

    MAX_BYTES: int = int(os.getenv("KA11Y_MAX_BODY_BYTES", str(2 * 1024 * 1024)))

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        declared = next((v for k, v in scope.get("headers", []) if k == b"content-length"), None)
        if declared is not None:
            try:
                if int(declared) > self.MAX_BYTES:
                    return await self._reject(send)
            except ValueError:
                return await self._reject(send, status=400, detail="Bad Content-Length")

        seen = 0
        limit = self.MAX_BYTES

        async def counted_receive():
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit:
                    raise _BodyTooLarge()
            return message

        try:
            await self.app(scope, counted_receive, send)
        except _BodyTooLarge:
            await self._reject(send)

    @staticmethod
    async def _reject(send, status: int = 413, detail: str = "Request body too large") -> None:
        body = json.dumps({"detail": detail}).encode()
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        })
        await send({"type": "http.response.body", "body": body})


class _BodyTooLarge(Exception):
    pass


def _is_https(request: StarletteRequest) -> bool:
    """TLS is terminated in front of us (ALB / Caddy / nginx). Uvicorn runs with
    --proxy-headers so request.url.scheme already reflects X-Forwarded-Proto
    from a trusted hop; the header is consulted as a fallback for setups that
    forgot the flag."""
    if request.url.scheme == "https":
        return True
    return request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower() == "https"


class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Defensive HTTP security headers on every response.

    * HSTS on https responses (a year, optionally preload) so browsers never
      downgrade a return visit to plain http.
    * A restrictive Content-Security-Policy: this service only ever answers
      with JSON, images, PDFs and CSV, so nothing may execute and nothing
      may frame it. ``frame-ancestors 'none'`` is the CSP-era X-Frame-Options.
    * The rest close off MIME sniffing, referrer leakage, cross-origin window
      access and every powerful browser feature.
    """

    async def dispatch(self, request: StarletteRequest, call_next):
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.url.path not in _DOCS_PATHS:
            # Swagger / ReDoc pull their bundles from a CDN and would be blank
            # under this policy; everything else this API serves is inert.
            h.setdefault(
                "Content-Security-Policy",
                "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            )
        h.setdefault("Permissions-Policy", _PERMISSIONS_POLICY)
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        h.setdefault("Cross-Origin-Resource-Policy", "same-site")
        h.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        if _is_https(request):
            cfg = _auth_settings()
            if cfg.hsts_max_age > 0:
                value = f"max-age={cfg.hsts_max_age}"
                if cfg.hsts_preload:
                    value += "; includeSubDomains; preload"
                h.setdefault("Strict-Transport-Security", value)
        return response


_DOCS_PATHS = {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}

_PERMISSIONS_POLICY = ", ".join(
    f"{feature}=()"
    for feature in (
        "accelerometer", "camera", "geolocation", "gyroscope", "magnetometer",
        "microphone", "payment", "usb", "interest-cohort", "browsing-topics",
    )
)


class _HttpsRedirectMiddleware(BaseHTTPMiddleware):
    """With KA11Y_FORCE_HTTPS on, a request that reached us over plain http
    (its own scheme, or X-Forwarded-Proto from the TLS terminator) is sent
    back as a 308 to the https URL. Loopback is exempt so the compose
    health-check and local curl keep working. Never enabled by default
    unless the cookies are already Secure, i.e. the deployment is https."""

    _LOOPBACK = {"localhost", "127.0.0.1", "::1"}

    async def dispatch(self, request: StarletteRequest, call_next):
        if not _auth_settings().force_https or _is_https(request):
            return await call_next(request)
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
        if host.split(":")[0] in self._LOOPBACK or request.url.path == "/api/v1/health":
            return await call_next(request)
        url = request.url.replace(scheme="https")
        if host:
            url = url.replace(netloc=host)
        return RedirectResponse(str(url), status_code=308)


def _auth_settings():
    from ka11y.auth.config import settings

    return settings()


logger = setup_logger(name="KAC", tag="main")
logger.info("Logger initialized")
config = load_config()
logger.info("Configuration loaded successfully")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ka11y API starting up")

    # Transport / cookie posture. Loud at start-up rather than a 500 on the
    # first login: the cookie sealer refuses a short secret.
    try:
        cfg = _auth_settings()
        if cfg.session_secret and not cfg.session_secret_ok:
            logger.error(
                "KA11Y_SESSION_SECRET is shorter than 32 characters; sign-in will fail. "
                "Generate one with: python3 -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        if cfg.session_secret and not cfg.cookie_secure:
            logger.warning(
                "KA11Y_COOKIE_SECURE is off: session cookies will travel over plain http. "
                "Acceptable for localhost only."
            )
        logger.info(
            "auth transport: cookie_secure=%s host_prefix=%s force_https=%s hsts_max_age=%s",
            cfg.cookie_secure, cfg.cookie_host_prefix, cfg.force_https, cfg.hsts_max_age,
        )
    except Exception:  # noqa: BLE001
        logger.exception("auth transport check failed")

    # Arize tracing. Must come first: it auto-instruments the google-genai SDK,
    # and only calls made after that point produce spans. No-op (and never
    # raises) when ARIZE_SPACE_ID/ARIZE_API_KEY are unset.
    try:
        from ka11y.observability import init_tracing

        init_tracing()
    except Exception:  # noqa: BLE001
        logger.exception("tracing failed to initialise; running untraced")

    # Durable store: open SQLite (WAL) and start the single writer thread before
    # anything that might persist. Degrades to memory-only if it can't start.
    try:
        from ka11y.store import init_db

        init_db()
    except Exception:  # noqa: BLE001
        logger.exception("SQLite store failed to initialise; running memory-only")

    # Production PostgreSQL (users, OIDC identities, sessions, audit ownership
    # and history). Inert when DATABASE_URL is unset; runs Alembic migrations
    # and seeds the WCAG catalogue otherwise. Never blocks startup.
    try:
        from ka11y.db import init_postgres

        await init_postgres()
    except Exception:  # noqa: BLE001
        logger.exception("PostgreSQL layer failed to initialise")

    eviction_task = asyncio.create_task(_evict_old_jobs())

    # Crash recovery + durable queue dispatcher (P4). On boot any run left
    # 'running' is requeued; the dispatcher drains 'queued' rows FIFO, bounded
    # by KA11Y_MAX_CONCURRENT_JOBS. Retention sweep (P1) prunes old runs+assets.
    dispatcher_task = None
    retention_task = None
    try:
        from ka11y.api.v1.combined.dispatcher import run_dispatcher
        from ka11y.store.retention import run_retention_loop

        dispatcher_task = asyncio.create_task(run_dispatcher())
        retention_task = asyncio.create_task(run_retention_loop())
    except Exception:  # noqa: BLE001
        logger.exception("dispatcher/retention failed to start")

    try:
        yield
    finally:
        for _t in (eviction_task, dispatcher_task, retention_task):
            if _t is not None:
                _t.cancel()
        # Sprint-2 (#9): tear down the shared Chromium pool on shutdown so
        # the host doesn't leak browser processes between reloads.
        try:
            from ka11y.crawler.browser_pool import shutdown_pool

            await shutdown_pool()
        except Exception:  # noqa: BLE001
            logger.exception("browser pool shutdown failed during lifespan teardown")
        try:
            from ka11y.db import shutdown_postgres

            await shutdown_postgres()
        except Exception:  # noqa: BLE001
            logger.exception("PostgreSQL dispose failed during lifespan teardown")
        try:
            from ka11y.store.cpu_pool import shutdown_pool as shutdown_cpu_pool

            shutdown_cpu_pool()
        except Exception:  # noqa: BLE001
            logger.exception("CPU pool shutdown failed")
        try:
            from ka11y.store import shutdown_db

            shutdown_db()
        except Exception:  # noqa: BLE001
            logger.exception("SQLite store shutdown failed")
        try:
            from ka11y.observability import shutdown_tracing

            # Flushes whatever the batch processor still holds, so the spans
            # from the last job in flight aren't lost on redeploy.
            shutdown_tracing()
        except Exception:  # noqa: BLE001
            logger.exception("tracing shutdown failed")
        logger.info("ka11y API shutting down")


app = FastAPI(
    title="ka11y",
    description="AI Based Web Accessibility Checker",
    version="0.0.1",
    lifespan=lifespan,
)

app.add_middleware(_RateLimitMiddleware)
app.add_middleware(_SecurityHeadersMiddleware)
app.add_middleware(_HttpsRedirectMiddleware)
# Outermost of the app-level guards: an oversized body is refused before the
# rate limiter or anything else spends time on it.
app.add_middleware(_BodyLimitMiddleware)

# Added after the two above, so Starlette runs it *outside* them: a request
# rejected by the rate limiter still produces a span with its 429, which is
# the case you most want to see on the dashboard. It stays inside CORS, which
# short-circuits preflight OPTIONS we have no interest in tracing.
try:
    from ka11y.observability.middleware import TracingMiddleware

    app.add_middleware(TracingMiddleware)
except Exception:  # noqa: BLE001
    logger.exception("HTTP tracing middleware not installed; requests run untraced")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://ec2-34-228-40-177.compute-1.amazonaws.com:8080",
        "https://a11y.bluecaffeine.in",
        "http://localhost:3001",

    ],
    allow_credentials=True,   # Set to True if using cookies/auth headers; otherwise False is fine
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)