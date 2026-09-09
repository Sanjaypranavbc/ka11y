"""
ka11y/observability
===================
Tracing/telemetry for the LLM path, exported to Arize (or any OpenInference
collector, such as a local Phoenix). See tracing.py for configuration.

    from ka11y.observability import init_tracing, traced_span

    init_tracing()                       # once per process, at startup
    with traced_span("my.step") as span: # spans nest around the Gemini calls
        ...
"""

from .tracing import (
    SpanKind,
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
