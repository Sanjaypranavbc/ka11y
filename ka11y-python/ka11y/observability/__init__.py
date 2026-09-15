"""
ka11y/observability
===================
End-to-end tracing for the audit engine, exported to Arize AX or any
OpenInference collector (a local Phoenix, say). See tracing.py for the
environment configuration.

What is instrumented
--------------------
=========================  ==================================================
API requests               ``TracingMiddleware`` — one span per HTTP call,
                           with route, status, latency and the job id.
Audit jobs                 ``runner._run_job_body`` — the root span of a
                           job's own trace, linked back to the request that
                           submitted it and grouped by ``session.id = job_id``.
Crawler execution          ``crawler.universal`` / ``crawler.images`` around
                           the BFS and the image crawl, plus per-invocation
                           spans from ``utils.crawler_timing``.
Page processing            ``crawler.page`` — one span per URL visited, with
                           depth, resolved URL, links found and warnings.
Rule execution             ``stage.*`` and ``rule.*`` spans, emitted by
                           ``utils.stage_timing`` at every existing timing
                           call site plus the auditor entry points.
LLM calls                  ``enrichment.run`` → ``enrichment.batch`` →
                           the ``GenerateContent`` spans the
                           openinference google-genai instrumentor emits.
Errors                     Recorded on whichever span was open, including
                           the ones ka11y deliberately swallows.
Latency                    Every span, plus an explicit ``ka11y.duration_ms``
                           where a caller already measured it.
Token usage                ``llm.token_count.*`` on the batch and run spans,
                           and an estimated cost on the run.
=========================  ==================================================

Typical use::

    from ka11y.observability import init_tracing, traced_span

    init_tracing()                       # once per process, at startup
    with traced_span("my.step") as span: # spans nest around the work
        ...

Every entry point here is best-effort: a missing key, a missing optional
dependency or an unreachable collector degrades to no-op spans, because losing
telemetry must never cost us an audit.
"""

from . import attributes
from .tracing import (
    SpanKind,
    add_span_event,
    capture_context,
    current_span,
    flush_tracing,
    get_tracer,
    init_tracing,
    is_tracing_enabled,
    record_span_error,
    set_span_attributes,
    set_span_input,
    set_span_output,
    set_token_counts,
    shutdown_tracing,
    traced_span,
)

__all__ = [
    "SpanKind",
    "add_span_event",
    "attributes",
    "capture_context",
    "current_span",
    "flush_tracing",
    "get_tracer",
    "init_tracing",
    "is_tracing_enabled",
    "record_span_error",
    "set_span_attributes",
    "set_span_input",
    "set_span_output",
    "set_token_counts",
    "shutdown_tracing",
    "traced_span",
]
