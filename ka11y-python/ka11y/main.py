#!/usr/bin/env python3

import asyncio
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse

from ka11y.api.router import router
from ka11y.api.v1.combined import _evict_old_jobs
from ka11y.config.logger import setup_logger
from ka11y.utils.config_loader import load_config

load_dotenv()


def _load_api_keys() -> set[str]:
    """Read the comma-separated ``KA11Y_API_KEYS`` env var into a set.

    Empty / unset → empty set → middleware runs in soft mode (allow all).
    Whitespace and blank tokens are dropped so trailing commas are forgiven.
    """
    raw = os.environ.get("KA11Y_API_KEYS", "")
    return {tok.strip() for tok in raw.split(",") if tok.strip()}


class _AuthMiddleware(BaseHTTPMiddleware):
    """
    Sprint 4 / step 26. ``X-API-Key``-header authentication for the
    audit API.

    Soft rollout: if ``KA11Y_API_KEYS`` is unset or empty, the middleware
    is a no-op (every request is allowed) — flip a single env var to
    turn auth on without redeploying. When keys ARE configured, any
    request that fails to present a matching ``X-API-Key`` is rejected
    with HTTP 401 before any downstream work runs.

    The middleware also sets ``request.state.rate_limit_id`` to the key
    (when authenticated) or the client IP (in soft mode / public health
    checks) so :class:`_RateLimitMiddleware` can throttle per-identity
    rather than per-IP — addresses the review's
    ``X-Forwarded-For``-spoofing concern by attributing usage to the
    presented API key.
    """

    # OPTIONS preflight + the unauthenticated health endpoint should not be
    # forced through auth — otherwise a CORS preflight from a browser fails
    # without exposing the API to abuse.
    _OPEN_PATHS: set[str] = {"/", "/health", "/docs", "/openapi.json", "/redoc"}

    def __init__(self, app):
        super().__init__(app)
        self._keys = _load_api_keys()

    async def dispatch(self, request: StarletteRequest, call_next):
        # OPTIONS preflight is handled by the CORS middleware; pass through.
        if request.method == "OPTIONS":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        presented = request.headers.get("x-api-key") or request.headers.get("X-API-Key")

        if not self._keys:
            # Soft mode: no keys configured. Identity is the client IP.
            request.state.rate_limit_id = f"ip:{client_ip}"
            return await call_next(request)

        if request.url.path in self._OPEN_PATHS:
            request.state.rate_limit_id = f"ip:{client_ip}"
            return await call_next(request)

        if not presented or presented not in self._keys:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid API key."},
                headers={"WWW-Authenticate": "ApiKey"},
            )

        request.state.rate_limit_id = f"key:{presented}"
        return await call_next(request)


class _RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding-window rate limiter: max 30 POST requests per identity per 60
    seconds. Identity is set by :class:`_AuthMiddleware` (API key in
    auth mode, client IP in soft mode), so attribution is to the
    presented credential rather than a forge-able ``X-Forwarded-For``
    header. Only POST endpoints (the expensive audit jobs) are throttled.
    Returns HTTP 429 with a Retry-After header when the limit is exceeded.
    """

    _MAX_REQUESTS: int = 30
    _WINDOW_SECONDS: int = 60

    def __init__(self, app):
        super().__init__(app)
        self._timestamps: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: StarletteRequest, call_next):
        if request.method != "POST":
            return await call_next(request)

        identity = getattr(request.state, "rate_limit_id", None)
        if not identity:
            # Fallback if _AuthMiddleware did not run (e.g. test client that
            # bypasses the chain). Keep prior per-IP semantics.
            ip = request.client.host if request.client else "unknown"
            identity = f"ip:{ip}"

        now = time.monotonic()
        window_start = now - self._WINDOW_SECONDS

        # Evict timestamps outside the sliding window
        self._timestamps[identity] = [
            t for t in self._timestamps[identity] if t > window_start
        ]

        if len(self._timestamps[identity]) >= self._MAX_REQUESTS:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please slow down."},
                headers={"Retry-After": str(self._WINDOW_SECONDS)},
            )

        self._timestamps[identity].append(now)
        return await call_next(request)


class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add defensive HTTP security headers to every response."""

    async def dispatch(self, request: StarletteRequest, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        response.headers.setdefault("X-XSS-Protection", "1; mode=block")
        return response


logger = setup_logger(name="KAC", tag="main")
logger.info("Logger initialized")
config = load_config()
logger.info("Configuration loaded successfully")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ka11y API starting up")
    eviction_task = asyncio.create_task(_evict_old_jobs())
    try:
        yield
    finally:
        eviction_task.cancel()
        # Sprint-2 (#9): tear down the shared Chromium pool on shutdown so
        # the host doesn't leak browser processes between reloads.
        try:
            from ka11y.crawler.browser_pool import shutdown_pool

            await shutdown_pool()
        except Exception:  # noqa: BLE001
            logger.exception("browser pool shutdown failed during lifespan teardown")
        logger.info("ka11y API shutting down")


app = FastAPI(
    title="ka11y",
    description="AI Based Web Accessibility Checker",
    version="0.0.1",
    lifespan=lifespan,
)

app.add_middleware(_RateLimitMiddleware)
app.add_middleware(_SecurityHeadersMiddleware)
# Add last so it wraps everything else — auth runs before rate limit so
# unauthenticated requests don't pollute the counter, and request.state
# gets populated before the rate limiter reads it.
app.add_middleware(_AuthMiddleware)

# CORS — allow all origins in development.

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # must be False when allow_origins="*"
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
