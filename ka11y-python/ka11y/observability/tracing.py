"""
ka11y/observability/tracing.py
==============================
Arize-backed OpenTelemetry tracing for ka11y's LLM path.

What it gives you
-----------------
* Every Gemini call made through the google-genai SDK — i.e. every
  ``client.models.generate_content`` in enrich_audit.py — is captured as an
  OpenInference LLM span (prompt, response, model, token counts, latency,
  exception) by ``openinference-instrumentation-google-genai``. That part is
  automatic: no call-site changes, no wrapper around the SDK.
* ``traced_span()`` adds the ka11y-shaped parents *around* those LLM spans, so
  a trace reads ``enrichment.run → enrichment.batch → GenerateContent`` instead
  of a flat list of anonymous model calls, and carries our own attributes (job
  id, page language, violation counts, estimated cost).
* Two interchangeable destinations: Arize AX (hosted) or a self-hosted Phoenix
  — the `phoenix` service in docker-compose.yml, UI on http://localhost:6006.

Configuration — environment only
--------------------------------
  ARIZE_SPACE_ID            Arize space id             (required for Arize AX)
  ARIZE_API_KEY             Arize API key              (required for Arize AX)
  ARIZE_PROJECT_NAME        project spans are filed under (default: ka11y)
  ARIZE_COLLECTOR_ENDPOINT  collector override for Arize AX (e.g. the EU
                            region). Set it *alone*, with no space id / api
                            key, and it doubles as a local collector address.
  ARIZE_TRANSPORT           grpc | http | https        (default: grpc)
  PHOENIX_COLLECTOR_ENDPOINT  address of a local Phoenix. Used by the collector
                            backend only — never sent to Arize AX — so it can
                            sit permanently in .env next to real credentials.
                            docker-compose.yml sets http://phoenix:4317; on the
                            host it is http://localhost:4317 (gRPC) or
                            http://localhost:6006/v1/traces (HTTP).
  KA11Y_TRACING_BACKEND     arize | phoenix | auto (default). "auto" picks
                            Arize AX when credentials are present and the local
                            collector otherwise; set it to "phoenix" to send
                            spans to Phoenix *without* deleting real ARIZE_*
                            credentials from .env, and back to "arize" (or
                            unset) to return to Arize AX.
  KA11Y_TRACING_ENABLED     1/0 forces tracing on/off. Unset means "auto": on
                            when credentials (or a collector endpoint) are
                            present, off otherwise — so a machine without keys
                            runs exactly as it does today.
  KA11Y_TRACING_CONSOLE     1 to also print spans to stdout while debugging.

Everything here is best-effort and never raises. A missing key, a missing
optional dependency (arize-otel / openinference-*) or an unreachable collector
degrades to no-op spans, because losing telemetry must never cost us an audit.
"""

from __future__ import annotations

import atexit
import json
import os
import threading
from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Optional

from dotenv import load_dotenv

from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="tracing")

# ── OpenInference semantic conventions ──────────────────────────────────────
# Imported from the package when it is installed; the fallbacks are the same
# wire names, so a tracing-less install still produces well-formed attributes
# if someone points a bare OTel exporter at this module.
try:
    from openinference.semconv.trace import SpanAttributes as _SA

    SPAN_KIND = _SA.OPENINFERENCE_SPAN_KIND
    INPUT_VALUE = _SA.INPUT_VALUE
    INPUT_MIME_TYPE = _SA.INPUT_MIME_TYPE
    OUTPUT_VALUE = _SA.OUTPUT_VALUE
    OUTPUT_MIME_TYPE = _SA.OUTPUT_MIME_TYPE
    METADATA = _SA.METADATA
    SESSION_ID = _SA.SESSION_ID
    LLM_MODEL_NAME = _SA.LLM_MODEL_NAME
    TOKEN_COUNT_PROMPT = _SA.LLM_TOKEN_COUNT_PROMPT
    TOKEN_COUNT_COMPLETION = _SA.LLM_TOKEN_COUNT_COMPLETION
    TOKEN_COUNT_TOTAL = _SA.LLM_TOKEN_COUNT_TOTAL
except ImportError:  # pragma: no cover - exercised only on installs without openinference
    SPAN_KIND = "openinference.span.kind"
    INPUT_VALUE = "input.value"
    INPUT_MIME_TYPE = "input.mime_type"
    OUTPUT_VALUE = "output.value"
    OUTPUT_MIME_TYPE = "output.mime_type"
    METADATA = "metadata"
    SESSION_ID = "session.id"
    LLM_MODEL_NAME = "llm.model_name"
    TOKEN_COUNT_PROMPT = "llm.token_count.prompt"
    TOKEN_COUNT_COMPLETION = "llm.token_count.completion"
    TOKEN_COUNT_TOTAL = "llm.token_count.total"


class SpanKind:
    """OpenInference span kinds used by ka11y (the vocabulary Arize groups on)."""

    CHAIN = "CHAIN"
    LLM = "LLM"
    TOOL = "TOOL"
    AGENT = "AGENT"
    UNKNOWN = "UNKNOWN"


_TRACER_NAME = "ka11y"
_DEFAULT_PROJECT = "ka11y"
# Resource key Phoenix / the OpenInference collectors read the project name
# from. arize.otel sets the same key for us in Arize AX mode.
_PROJECT_RESOURCE_KEY = "openinference.project.name"

_BACKEND_ARIZE = "arize"
_BACKEND_COLLECTOR = "collector"
# Phoenix serves its UI and the OTLP/HTTP collector on 6006, and OTLP/gRPC on
# 4317 — the two protocols are not interchangeable on one port.
_PHOENIX_HTTP_PORT = "6006"
_PHOENIX_GRPC_PORT = "4317"
_OTLP_TRACES_PATH = "/v1/traces"

_init_lock = threading.RLock()
_tracer_provider: Any = None
_enabled: bool = False
_init_attempted: bool = False


# ── env helpers ─────────────────────────────────────────────────────────────
def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _flag(name: str) -> Optional[bool]:
    """Parse a boolean env var. Returns None when unset, so callers can tell
    "explicitly off" apart from "not configured"."""
    raw = _env(name).lower()
    if not raw:
        return None
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    logger.warning("ignoring unrecognised value %r for %s", raw, name)
    return None


def _backend_choice() -> str:
    return _env("KA11Y_TRACING_BACKEND").lower() or "auto"


def _tracing_requested(space_id: str, api_key: str, endpoint: str) -> bool:
    forced = _flag("KA11Y_TRACING_ENABLED")
    if forced is not None:
        return forced
    if _backend_choice() in ("phoenix", "collector", "local"):
        return True
    return bool((space_id and api_key) or endpoint)


def _resolve_backend(space_id: str, api_key: str, endpoint: str) -> str:
    """Pick the exporter: Arize AX or a local OTLP collector (Phoenix).

    Credentials alone can't decide this — a developer running Phoenix locally
    usually still has real ARIZE_SPACE_ID/ARIZE_API_KEY sitting in .env, and
    silently preferring Arize would send their traces to production. So
    KA11Y_TRACING_BACKEND pins the choice, and "auto" only falls back to
    credentials-then-endpoint. Returns "" when nothing is configured."""
    choice = _backend_choice()
    if choice in ("phoenix", "collector", "local"):
        return _BACKEND_COLLECTOR
    if choice == "arize":
        return _BACKEND_ARIZE if (space_id and api_key) else ""
    if choice != "auto":
        logger.warning("ignoring unrecognised KA11Y_TRACING_BACKEND=%r; using auto", choice)
    if space_id and api_key:
        return _BACKEND_ARIZE
    return _BACKEND_COLLECTOR if endpoint else ""


# ── provider construction ───────────────────────────────────────────────────
def _resolve_transport() -> str:
    """OTLP protocol as a plain string, so the collector path doesn't need
    arize-otel just to name a transport."""
    raw = _env("ARIZE_TRANSPORT").lower() or "grpc"
    if raw not in ("grpc", "http", "https"):
        logger.warning(
            "unsupported ARIZE_TRANSPORT=%r (expected grpc/http/https); using grpc", raw
        )
        return "grpc"
    return raw


def _normalize_collector_endpoint(endpoint: str, transport: str) -> str:
    """Accept either OTLP endpoint shape and hand the exporter the one it
    needs. gRPC wants a bare host:port (Phoenix: 4317); HTTP wants the full
    .../v1/traces URL (Phoenix: 6006). Getting this wrong fails silently —
    spans simply never arrive — so normalise rather than trusting the value."""
    endpoint = endpoint.rstrip("/")
    if transport == "grpc":
        if endpoint.endswith(_OTLP_TRACES_PATH):
            endpoint = endpoint[: -len(_OTLP_TRACES_PATH)]
        # A Phoenix base URL (…:6006) is the HTTP/UI port; gRPC lives on 4317.
        if endpoint.endswith(f":{_PHOENIX_HTTP_PORT}"):
            endpoint = endpoint[: -len(_PHOENIX_HTTP_PORT)] + _PHOENIX_GRPC_PORT
            logger.info("collector endpoint is a Phoenix HTTP port; using gRPC port instead: %s", endpoint)
        return endpoint
    if not endpoint.endswith(_OTLP_TRACES_PATH):
        endpoint += _OTLP_TRACES_PATH
    return endpoint


def _default_collector_endpoint(transport: str) -> str:
    """Where a local Phoenix listens when no endpoint was configured."""
    port = _PHOENIX_GRPC_PORT if transport == "grpc" else _PHOENIX_HTTP_PORT
    return f"http://localhost:{port}"


def _register_arize(space_id: str, api_key: str, project: str, endpoint: str, transport: str) -> Any:
    """Arize AX mode — space id + API key, spans exported to otlp.arize.com."""
    from arize.otel import Transport, register

    kwargs: dict[str, Any] = {
        "space_id": space_id,
        "api_key": api_key,
        "project_name": project,
        "transport": Transport(transport),
        "batch": True,
        "set_global_tracer_provider": True,
        # register() prints a config banner to stdout by default; ours goes
        # through the ka11y logger instead so it lands in the log files too.
        "verbose": False,
        "log_to_console": bool(_flag("KA11Y_TRACING_CONSOLE")),
    }
    if endpoint:
        kwargs["endpoint"] = endpoint
    return register(**kwargs)


def _register_collector(endpoint: str, project: str, transport: str) -> Any:
    """Collector mode — an OTLP endpoint with no Arize credentials, for the
    local Phoenix service in docker-compose.yml (`phoenix` on the ka11y-net
    network) or any other OpenInference-aware collector. Built on the plain
    OTel SDK, so this path does not need arize-otel at all.

    Both OTLP protocols are supported and the exporter follows
    ARIZE_TRANSPORT: gRPC (the default, Phoenix port 4317) or HTTP
    (Phoenix port 6006)."""
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    if transport == "grpc":
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    else:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    provider = TracerProvider(
        resource=Resource.create(
            {_PROJECT_RESOURCE_KEY: project, "service.name": project}
        )
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    if _flag("KA11Y_TRACING_CONSOLE"):
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    return provider


def _instrument_google_genai(provider: Any) -> bool:
    """Auto-instrument the google-genai SDK so each generate_content() call
    becomes an LLM span under whatever ka11y span is current."""
    try:
        from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor
    except ImportError:
        logger.warning(
            "openinference-instrumentation-google-genai is not installed — "
            "ka11y spans will export, but Gemini calls won't be captured"
        )
        return False

    instrumentor = GoogleGenAIInstrumentor()
    if instrumentor.is_instrumented_by_opentelemetry:
        return True
    instrumentor.instrument(tracer_provider=provider)
    return True


# ── public API ──────────────────────────────────────────────────────────────
def init_tracing(project_name: Optional[str] = None, *, force: bool = False) -> bool:
    """Initialise tracing for this process and return True when spans are
    actually being exported.

    Idempotent and thread-safe: repeat calls return the first result without
    re-registering, so it is safe to call from the API's lifespan startup, the
    enrich_audit CLI and a worker thread alike. Pass force=True to re-run
    initialisation after changing the environment (used by the tests).

    Never raises — a failure to reach Arize is logged and leaves the process
    running untraced."""
    global _tracer_provider, _enabled, _init_attempted

    with _init_lock:
        if _init_attempted and not force:
            return _enabled

        _init_attempted = True
        _enabled = False
        _tracer_provider = None

        # CLI callers (enrich_audit.py) get their keys from ka11y-python/.env
        # the same way the Gemini key is loaded; the API already called this
        # at import time, and load_dotenv() never overrides a real env var.
        load_dotenv()

        space_id = _env("ARIZE_SPACE_ID")
        api_key = _env("ARIZE_API_KEY")
        arize_endpoint = _env("ARIZE_COLLECTOR_ENDPOINT")
        # PHOENIX_COLLECTOR_ENDPOINT is the name Phoenix's own docs use; it
        # applies to the collector path only, never to Arize AX.
        collector_endpoint = arize_endpoint or _env("PHOENIX_COLLECTOR_ENDPOINT")
        project = project_name or _env("ARIZE_PROJECT_NAME") or _DEFAULT_PROJECT
        transport = _resolve_transport()

        if not _tracing_requested(space_id, api_key, collector_endpoint):
            logger.debug("tracing not configured (no ARIZE_SPACE_ID/ARIZE_API_KEY) — skipping")
            return False

        backend = _resolve_backend(space_id, api_key, collector_endpoint)
        try:
            if backend == _BACKEND_ARIZE:
                provider = _register_arize(space_id, api_key, project, arize_endpoint, transport)
                mode = f"arize:{arize_endpoint or 'otlp.arize.com'}"
            elif backend == _BACKEND_COLLECTOR:
                target = _normalize_collector_endpoint(
                    collector_endpoint or _default_collector_endpoint(transport), transport
                )
                provider = _register_collector(target, project, transport)
                mode = f"collector:{target}"
            else:
                logger.warning(
                    "tracing is switched on but no backend is configured — set "
                    "ARIZE_SPACE_ID/ARIZE_API_KEY for Arize AX, or "
                    "ARIZE_COLLECTOR_ENDPOINT for a local Phoenix — tracing stays off"
                )
                return False
        except Exception:  # noqa: BLE001
            logger.warning("tracing failed to initialise; continuing untraced", exc_info=True)
            return False

        _tracer_provider = provider
        _enabled = True
        instrumented = _instrument_google_genai(provider)
        atexit.register(shutdown_tracing)
        logger.info(
            "tracing enabled — project=%s mode=%s transport=%s gemini_spans=%s",
            project, mode, transport, "on" if instrumented else "off",
        )
        return True


def is_tracing_enabled() -> bool:
    return _enabled


def get_tracer(name: str = _TRACER_NAME) -> Any:
    """Tracer bound to ka11y's provider, or the global (no-op) tracer when
    tracing is off. Returns None only if OpenTelemetry itself is missing."""
    try:
        from opentelemetry import trace
    except ImportError:  # pragma: no cover - opentelemetry is a hard dep of arize-otel
        return None

    if _tracer_provider is not None:
        return _tracer_provider.get_tracer(name)
    return trace.get_tracer(name)


class _NoopSpan:
    """Stand-in yielded by traced_span() when OpenTelemetry is unavailable, so
    call sites can use the span API unconditionally."""

    def set_attribute(self, *_args, **_kwargs) -> None: ...
    def set_attributes(self, *_args, **_kwargs) -> None: ...
    def add_event(self, *_args, **_kwargs) -> None: ...
    def record_exception(self, *_args, **_kwargs) -> None: ...
    def set_status(self, *_args, **_kwargs) -> None: ...
    def is_recording(self) -> bool:
        return False


_NOOP_SPAN = _NoopSpan()


def _serialize(value: Any) -> tuple[str, str]:
    """Return (text, mime_type) for an input/output payload."""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, default=str), "application/json"
    return str(value), "text/plain"


def set_span_attributes(span: Any, attributes: Mapping[str, Any]) -> None:
    """Set attributes, skipping Nones and JSON-encoding anything OTel can't
    carry natively (dicts, lists, model objects)."""
    for key, value in attributes.items():
        if value is None:
            continue
        if isinstance(value, (str, bool, int, float)):
            span.set_attribute(key, value)
        else:
            span.set_attribute(key, _serialize(value)[0])


def set_span_input(span: Any, value: Any) -> None:
    text, mime = _serialize(value)
    span.set_attribute(INPUT_VALUE, text)
    span.set_attribute(INPUT_MIME_TYPE, mime)


def set_span_output(span: Any, value: Any) -> None:
    text, mime = _serialize(value)
    span.set_attribute(OUTPUT_VALUE, text)
    span.set_attribute(OUTPUT_MIME_TYPE, mime)


def set_token_counts(
    span: Any,
    *,
    prompt: int = 0,
    completion: int = 0,
    total: int = 0,
) -> None:
    """Attach token counts to a non-LLM (chain) span — Arize sums these for
    cost/usage roll-ups over a whole enrichment run."""
    for key, count in (
        (TOKEN_COUNT_PROMPT, prompt),
        (TOKEN_COUNT_COMPLETION, completion),
        (TOKEN_COUNT_TOTAL, total),
    ):
        if count:
            span.set_attribute(key, int(count))


def record_span_error(span: Any, exc: BaseException) -> None:
    """Mark a span as failed. Used where the caller swallows the exception
    (enrich_audit keeps a failed batch from killing the run), since OTel only
    marks a span failed when the exception propagates out of it."""
    try:
        from opentelemetry.trace import Status, StatusCode
    except ImportError:  # pragma: no cover - opentelemetry is a hard dep of arize-otel
        return
    span.record_exception(exc)
    span.set_status(Status(StatusCode.ERROR, str(exc)))


@contextmanager
def traced_span(
    name: str,
    *,
    kind: str = SpanKind.CHAIN,
    attributes: Optional[Mapping[str, Any]] = None,
    input_value: Any = None,
    session_id: Optional[str] = None,
    metadata: Optional[Mapping[str, Any]] = None,
    tracer_name: str = _TRACER_NAME,
) -> Iterator[Any]:
    """Open a span around a block of work and yield it, so the caller can stamp
    results on the way out (see enrich_audit.py's batch loop).

    Cheap and safe when tracing is off: the yielded span is then a
    non-recording one whose setters do nothing. Exceptions are recorded and
    re-raised — OTel's start_as_current_span() handles that for us.

        with traced_span("enrichment", attributes={"violations": 12}) as span:
            ...
            set_token_counts(span, total=usage.total_token_count)

    session_id groups every span of one audit job into an Arize session."""
    tracer = get_tracer(tracer_name)
    if tracer is None:
        yield _NOOP_SPAN
        return

    with tracer.start_as_current_span(name) as span:
        span.set_attribute(SPAN_KIND, kind)
        if session_id:
            span.set_attribute(SESSION_ID, session_id)
        if metadata:
            span.set_attribute(METADATA, _serialize(dict(metadata))[0])
        if attributes:
            set_span_attributes(span, attributes)
        if input_value is not None:
            set_span_input(span, input_value)
        yield span


def flush_tracing(timeout_ms: int = 10_000) -> None:
    """Block until queued spans are exported. Batched export means a
    short-lived process (the enrich_audit CLI, a one-shot script) would
    otherwise exit with its spans still sitting in the queue."""
    provider = _tracer_provider
    if provider is None:
        return
    try:
        provider.force_flush(timeout_ms)
    except Exception:  # noqa: BLE001
        logger.debug("span flush failed", exc_info=True)


def shutdown_tracing(timeout_ms: int = 10_000) -> None:
    """Flush and tear down the provider. Registered with atexit on init and
    also called from the API's lifespan teardown; safe to call twice."""
    global _tracer_provider, _enabled, _init_attempted

    with _init_lock:
        provider = _tracer_provider
        if provider is None:
            return
        flush_tracing(timeout_ms)
        try:
            provider.shutdown()
        except Exception:  # noqa: BLE001
            logger.debug("tracer provider shutdown failed", exc_info=True)
        _tracer_provider = None
        _enabled = False
        _init_attempted = False
