#!/usr/bin/env python3

import asyncio
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


class _RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding-window rate limiter: max 30 POST requests per IP per 60 seconds.
    Only POST endpoints (the expensive audit jobs) are throttled.
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

        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window_start = now - self._WINDOW_SECONDS

        # Evict timestamps outside the sliding window
        self._timestamps[ip] = [t for t in self._timestamps[ip] if t > window_start]

        if len(self._timestamps[ip]) >= self._MAX_REQUESTS:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please slow down."},
                headers={"Retry-After": str(self._WINDOW_SECONDS)},
            )

        self._timestamps[ip].append(now)
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

    # Durable store: open SQLite (WAL) and start the single writer thread before
    # anything that might persist. Degrades to memory-only if it can't start.
    try:
        from ka11y.store import init_db

        init_db()
    except Exception:  # noqa: BLE001
        logger.exception("SQLite store failed to initialise; running memory-only")

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
            from ka11y.store.cpu_pool import shutdown_pool as shutdown_cpu_pool

            shutdown_cpu_pool()
        except Exception:  # noqa: BLE001
            logger.exception("CPU pool shutdown failed")
        try:
            from ka11y.store import shutdown_db

            shutdown_db()
        except Exception:  # noqa: BLE001
            logger.exception("SQLite store shutdown failed")
        logger.info("ka11y API shutting down")


app = FastAPI(
    title="ka11y",
    description="AI Based Web Accessibility Checker",
    version="0.0.1",
    lifespan=lifespan,
)

app.add_middleware(_RateLimitMiddleware)
app.add_middleware(_SecurityHeadersMiddleware)

# CORS — allow all origins in development.

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # must be False when allow_origins="*"
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
