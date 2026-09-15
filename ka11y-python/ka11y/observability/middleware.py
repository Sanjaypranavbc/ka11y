"""
ka11y/observability/middleware.py
=================================
The HTTP entry point of the trace: one span per API request.

Why hand-rolled instead of opentelemetry-instrumentation-fastapi
----------------------------------------------------------------
That package isn't in the lock file, and adding it would pull the whole
``opentelemetry-instrumentation`` auto-instrumentation machinery for a job that
is forty lines here. Hand-rolling also lets us do the three ka11y-specific
things a generic instrumentor can't:

* skip the SSE stream endpoint, whose connection stays open for the entire
  audit — a generic instrumentor would emit a half-hour "HTTP request" span
  that swamps every latency percentile on the dashboard;
* skip health checks, which otherwise dominate span volume (and cost) on a
  load-balanced deployment without saying anything;
* hand handlers a request id they can echo back, so a client-reported
  slow call resolves to one span.

The job id ties a submit request to the audit it starts, but the *handler*
stamps that (``routes._admit_run``) — the id only exists after admission, and
reading it here would mean parsing a response body the client still has to
consume.

The audit itself is deliberately *not* inside this span — see
``runner._run_job_body``, which opens its own root trace and links back here.
"""

from __future__ import annotations

import time
import uuid
from typing import Iterable, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ka11y.config.logger import setup_logger

from . import attributes as attrs
from .tracing import (
    SpanKind,
    is_tracing_enabled,
    record_span_error,
    set_span_attributes,
    traced_span,
)

logger = setup_logger(name="KAC", tag="tracing")

# Paths that must not produce a span. Suffix-matched against the request path
# so the router prefix (/api/v1/...) doesn't have to be repeated here.
_DEFAULT_SKIP_SUFFIXES: tuple[str, ...] = (
    "/health",
    "/system/health",
    "/stream",          # SSE: open for the lifetime of the audit
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
)

# Response headers a client can correlate against. The request id is generated
# here when the caller didn't supply one, so a support ticket ("my audit at
# 14:03 hung") can be resolved to a single trace.
_REQUEST_ID_HEADER = "X-Request-ID"
_TRACE_ID_HEADER = "X-Trace-ID"


class TracingMiddleware(BaseHTTPMiddleware):
    """Emit one OpenInference span per HTTP request.

    Costs nothing measurable when tracing is off: ``traced_span`` yields a
    non-recording span whose setters are no-ops, and the only work left is a
    ``perf_counter`` pair and a suffix check.
    """

    def __init__(self, app, *, skip_suffixes: Optional[Iterable[str]] = None) -> None:
        super().__init__(app)
        self._skip = tuple(skip_suffixes) if skip_suffixes else _DEFAULT_SKIP_SUFFIXES

    def _should_skip(self, path: str) -> bool:
        return path.endswith(self._skip)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not is_tracing_enabled() or self._should_skip(path):
            return await call_next(request)

        request_id = request.headers.get(_REQUEST_ID_HEADER) or uuid.uuid4().hex
        # Stash it on the request so downstream handlers (and the job they
        # launch) can carry the same id into their own spans and logs.
        request.state.request_id = request_id

        started = time.perf_counter()
        with traced_span(
            attrs.http_span_name(request.method, path),
            kind=SpanKind.CHAIN,
            attributes={
                attrs.HTTP_METHOD: request.method,
                attrs.HTTP_TARGET: path,
                attrs.HTTP_REQUEST_ID: request_id,
                attrs.HTTP_CLIENT_IP: request.client.host if request.client else None,
                attrs.HTTP_USER_AGENT: request.headers.get("user-agent"),
            },
        ) as span:
            try:
                response: Response = await call_next(request)
            except Exception as exc:  # noqa: BLE001 - re-raised immediately
                # Starlette turns this into a 500 further out; the span would
                # otherwise be reported as UNSET with no error attached.
                record_span_error(span, exc)
                set_span_attributes(
                    span,
                    {
                        attrs.HTTP_STATUS_CODE: 500,
                        attrs.DURATION_MS: (time.perf_counter() - started) * 1000.0,
                    },
                )
                raise

            # The matched route is only on the scope once routing has run, so
            # the span opens with the raw path and is renamed to the template
            # here: "GET /api/v1/combined/{job_id}", not one name per job id.
            route = getattr(request.scope.get("route", None), "path", None)
            if route:
                try:
                    span.update_name(attrs.http_span_name(request.method, route))
                except Exception:  # noqa: BLE001
                    pass

            set_span_attributes(
                span,
                {
                    attrs.HTTP_ROUTE: route,
                    attrs.HTTP_STATUS_CODE: response.status_code,
                    attrs.DURATION_MS: (time.perf_counter() - started) * 1000.0,
                },
            )
            if response.status_code >= 500:
                _mark_server_error(span, response.status_code)

            response.headers.setdefault(_REQUEST_ID_HEADER, request_id)
            trace_id = _trace_id_hex(span)
            if trace_id:
                response.headers.setdefault(_TRACE_ID_HEADER, trace_id)
            return response


def _mark_server_error(span, status_code: int) -> None:
    """A 5xx handled inside FastAPI never raises past the middleware, so the
    span has to be failed explicitly or the error rate reads as zero."""
    try:
        from opentelemetry.trace import Status, StatusCode

        span.set_status(Status(StatusCode.ERROR, f"HTTP {status_code}"))
    except Exception:  # noqa: BLE001
        pass


def _trace_id_hex(span) -> Optional[str]:
    try:
        ctx = span.get_span_context()
        if not getattr(ctx, "is_valid", False):
            return None
        return format(ctx.trace_id, "032x")
    except Exception:  # noqa: BLE001
        return None


__all__ = ["TracingMiddleware"]
