#!/usr/bin/env python3

import asyncio
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from ka11y.config.logger import setup_logger
from ka11y.utils.config_loader import load_config
from ka11y.api.router import router
from ka11y.api.v1.combined import _evict_old_jobs


class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add defensive HTTP security headers to every response."""

    async def dispatch(self, request: StarletteRequest, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
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
    yield
    eviction_task.cancel()
    logger.info("ka11y API shutting down")


app = FastAPI(
    title="ka11y",
    description="AI Based Web Accessibility Checker",
    version="0.0.1",
    lifespan=lifespan,
)

app.add_middleware(_SecurityHeadersMiddleware)
app.include_router(router)
