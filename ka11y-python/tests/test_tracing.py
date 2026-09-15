"""Tests for ka11y/observability/tracing.py — the Arize/OpenInference tracing
module.

Nothing here talks to Arize: the export path is exercised against an in-memory
span exporter, and the "not configured" tests assert that spans stay harmless
no-ops so an unconfigured deployment behaves exactly as it did before.
"""

from __future__ import annotations

import pytest

from ka11y.observability import attributes, tracing


@pytest.fixture(autouse=True)
def _reset_tracing_state(monkeypatch):
    """Every test starts from an uninitialised module and a clean environment,
    so a developer's real ARIZE_* keys never leak into a test run."""
    for var in (
        "ARIZE_SPACE_ID",
        "ARIZE_API_KEY",
        "ARIZE_PROJECT_NAME",
        "ARIZE_COLLECTOR_ENDPOINT",
        "ARIZE_TRANSPORT",
        "PHOENIX_COLLECTOR_ENDPOINT",
        "KA11Y_TRACING_BACKEND",
        "KA11Y_TRACING_ENABLED",
        "KA11Y_TRACING_CONSOLE",
    ):
        monkeypatch.delenv(var, raising=False)
    # init_tracing() calls load_dotenv(), which would repopulate those from a
    # local .env — stub it out.
    monkeypatch.setattr(tracing, "load_dotenv", lambda *a, **k: False)
    tracing.shutdown_tracing()
    yield
    tracing.shutdown_tracing()


# ── configuration gating ────────────────────────────────────────────────────
def test_tracing_stays_off_when_unconfigured():
    assert tracing.init_tracing(force=True) is False
    assert tracing.is_tracing_enabled() is False


def test_explicit_disable_wins_over_credentials(monkeypatch):
    monkeypatch.setenv("ARIZE_SPACE_ID", "space")
    monkeypatch.setenv("ARIZE_API_KEY", "key")
    monkeypatch.setenv("KA11Y_TRACING_ENABLED", "0")
    assert tracing.init_tracing(force=True) is False


def test_enabled_without_credentials_does_not_raise(monkeypatch):
    """A half-configured deployment logs and carries on untraced rather than
    taking the API down at startup."""
    monkeypatch.setenv("KA11Y_TRACING_ENABLED", "1")
    assert tracing.init_tracing(force=True) is False


def test_registration_failure_is_swallowed(monkeypatch):
    monkeypatch.setenv("ARIZE_SPACE_ID", "space")
    monkeypatch.setenv("ARIZE_API_KEY", "key")

    def _boom(*_args, **_kwargs):
        raise RuntimeError("collector unreachable")

    monkeypatch.setattr(tracing, "_register_arize", _boom)
    assert tracing.init_tracing(force=True) is False
    assert tracing.is_tracing_enabled() is False


def test_init_is_idempotent(monkeypatch):
    calls = []
    monkeypatch.setenv("ARIZE_SPACE_ID", "space")
    monkeypatch.setenv("ARIZE_API_KEY", "key")
    monkeypatch.setattr(tracing, "_register_arize", lambda *a, **k: calls.append(1) or _provider())
    monkeypatch.setattr(tracing, "_instrument_google_genai", lambda _p: True)

    assert tracing.init_tracing(force=True) is True
    assert tracing.init_tracing() is True
    assert len(calls) == 1


# ── backend selection: Arize AX vs local Phoenix ────────────────────────────
def _record_backend(monkeypatch):
    """Capture which registration path init_tracing() takes, and with what."""
    picked: dict = {}

    def _arize(space_id, api_key, project, endpoint, transport):
        picked.update(backend="arize", endpoint=endpoint, transport=transport, project=project)
        return _provider()

    def _collector(endpoint, project, transport):
        picked.update(backend="collector", endpoint=endpoint, transport=transport, project=project)
        return _provider()

    monkeypatch.setattr(tracing, "_register_arize", _arize)
    monkeypatch.setattr(tracing, "_register_collector", _collector)
    monkeypatch.setattr(tracing, "_instrument_google_genai", lambda _p: True)
    return picked


def test_credentials_alone_still_go_to_arize(monkeypatch):
    """The pre-Phoenix behaviour: credentials set, nothing else configured."""
    picked = _record_backend(monkeypatch)
    monkeypatch.setenv("ARIZE_SPACE_ID", "space")
    monkeypatch.setenv("ARIZE_API_KEY", "key")
    # A Phoenix address is present (compose always sets it) and must NOT
    # divert traces away from Arize AX on its own.
    monkeypatch.setenv("PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:4317")

    assert tracing.init_tracing(force=True) is True
    assert picked["backend"] == "arize"
    assert picked["endpoint"] == ""  # the SDK's own otlp.arize.com default


def test_backend_phoenix_overrides_arize_credentials(monkeypatch):
    """Switching to the local UI must not require deleting real credentials."""
    picked = _record_backend(monkeypatch)
    monkeypatch.setenv("ARIZE_SPACE_ID", "space")
    monkeypatch.setenv("ARIZE_API_KEY", "key")
    monkeypatch.setenv("KA11Y_TRACING_BACKEND", "phoenix")
    monkeypatch.setenv("PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:4317")

    assert tracing.init_tracing(force=True) is True
    assert picked["backend"] == "collector"
    assert picked["endpoint"] == "http://phoenix:4317"
    assert picked["transport"] == "grpc"


def test_backend_phoenix_without_endpoint_falls_back_to_localhost(monkeypatch):
    picked = _record_backend(monkeypatch)
    monkeypatch.setenv("KA11Y_TRACING_BACKEND", "phoenix")

    assert tracing.init_tracing(force=True) is True
    assert picked["endpoint"] == "http://localhost:4317"


def test_backend_arize_without_credentials_stays_off(monkeypatch):
    _record_backend(monkeypatch)
    monkeypatch.setenv("KA11Y_TRACING_BACKEND", "arize")
    monkeypatch.setenv("PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:4317")

    assert tracing.init_tracing(force=True) is False


def test_arize_collector_endpoint_is_reserved_for_arize(monkeypatch):
    """ARIZE_COLLECTOR_ENDPOINT keeps its old meaning — an Arize AX override."""
    picked = _record_backend(monkeypatch)
    monkeypatch.setenv("ARIZE_SPACE_ID", "space")
    monkeypatch.setenv("ARIZE_API_KEY", "key")
    monkeypatch.setenv("ARIZE_COLLECTOR_ENDPOINT", "https://otlp.eu-west-1a.arize.com/v1")

    assert tracing.init_tracing(force=True) is True
    assert picked["backend"] == "arize"
    assert picked["endpoint"] == "https://otlp.eu-west-1a.arize.com/v1"


@pytest.mark.parametrize(
    "endpoint, transport, expected",
    [
        # gRPC wants host:port — a Phoenix UI/HTTP address is corrected to 4317.
        ("http://phoenix:4317", "grpc", "http://phoenix:4317"),
        ("http://phoenix:6006", "grpc", "http://phoenix:4317"),
        ("http://phoenix:6006/v1/traces", "grpc", "http://phoenix:4317"),
        ("http://phoenix:4317/", "grpc", "http://phoenix:4317"),
        # HTTP wants the full traces path.
        ("http://phoenix:6006", "http", "http://phoenix:6006/v1/traces"),
        ("http://phoenix:6006/v1/traces", "http", "http://phoenix:6006/v1/traces"),
    ],
)
def test_collector_endpoint_normalisation(endpoint, transport, expected):
    assert tracing._normalize_collector_endpoint(endpoint, transport) == expected


def test_transport_falls_back_to_grpc_on_a_bad_value(monkeypatch):
    monkeypatch.setenv("ARIZE_TRANSPORT", "carrier-pigeon")
    assert tracing._resolve_transport() == "grpc"
    monkeypatch.setenv("ARIZE_TRANSPORT", "http")
    assert tracing._resolve_transport() == "http"


def test_collector_uses_the_grpc_exporter_for_grpc(monkeypatch):
    """The exporter must follow ARIZE_TRANSPORT: an HTTP exporter aimed at
    Phoenix's gRPC port drops every span silently."""
    from opentelemetry import trace

    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter as GrpcExporter,
    )
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter as HttpExporter,
    )

    # _register_collector() installs the provider globally, which is what we
    # want in production and process-wide (unsettable) pollution in a test.
    monkeypatch.setattr(trace, "set_tracer_provider", lambda _p: None)

    def _exporters(provider):
        return [
            type(p.span_exporter)
            for p in provider._active_span_processor._span_processors
        ]

    grpc_provider = tracing._register_collector("http://phoenix:4317", "ka11y", "grpc")
    http_provider = tracing._register_collector(
        "http://phoenix:6006/v1/traces", "ka11y", "http"
    )
    try:
        assert GrpcExporter in _exporters(grpc_provider)
        assert HttpExporter in _exporters(http_provider)
    finally:
        grpc_provider.shutdown()
        http_provider.shutdown()


# ── span emission ───────────────────────────────────────────────────────────
def _provider():
    from opentelemetry.sdk.trace import TracerProvider

    return TracerProvider()


def _traced_provider(monkeypatch):
    """Wire the module to a real SDK provider exporting into memory."""
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    provider = _provider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    monkeypatch.setenv("ARIZE_SPACE_ID", "space")
    monkeypatch.setenv("ARIZE_API_KEY", "key")
    monkeypatch.setattr(tracing, "_register_arize", lambda *a, **k: provider)
    monkeypatch.setattr(tracing, "_instrument_google_genai", lambda _p: True)
    assert tracing.init_tracing(force=True) is True
    return exporter


def test_traced_span_records_openinference_attributes(monkeypatch):
    exporter = _traced_provider(monkeypatch)

    with tracing.traced_span(
        "enrichment.run",
        attributes={"enrichment.violation_count": 3},
        input_value={"batch": 1},
        session_id="job-123",
        metadata={"report_file": "combined_report.json"},
    ) as span:
        tracing.set_token_counts(span, prompt=100, completion=40, total=140)
        tracing.set_span_output(span, {"enriched": 3})

    (finished,) = exporter.get_finished_spans()
    attrs = finished.attributes
    assert finished.name == "enrichment.run"
    assert attrs[tracing.SPAN_KIND] == tracing.SpanKind.CHAIN
    assert attrs[tracing.SESSION_ID] == "job-123"
    assert attrs["enrichment.violation_count"] == 3
    assert attrs[tracing.TOKEN_COUNT_PROMPT] == 100
    assert attrs[tracing.TOKEN_COUNT_COMPLETION] == 40
    assert attrs[tracing.TOKEN_COUNT_TOTAL] == 140
    # Dicts are JSON-encoded, since OTel attributes only carry primitives.
    assert attrs[tracing.INPUT_MIME_TYPE] == "application/json"
    assert '"enriched": 3' in attrs[tracing.OUTPUT_VALUE]
    assert "combined_report.json" in attrs[tracing.METADATA]


def test_nested_spans_share_a_trace(monkeypatch):
    """The batch spans must hang off the run span — that nesting is what makes
    a trace readable in Arize (run → batch → Gemini call)."""
    exporter = _traced_provider(monkeypatch)

    with tracing.traced_span("enrichment.run"):
        with tracing.traced_span("enrichment.batch"):
            pass

    batch, run = exporter.get_finished_spans()  # children finish first
    assert batch.parent.span_id == run.context.span_id
    assert batch.context.trace_id == run.context.trace_id


def test_record_span_error_marks_a_swallowed_failure(monkeypatch):
    from opentelemetry.trace import StatusCode

    exporter = _traced_provider(monkeypatch)

    with tracing.traced_span("enrichment.batch") as span:
        try:
            raise RuntimeError("gemini timed out")
        except RuntimeError as exc:  # what enrich_violations does per batch
            tracing.record_span_error(span, exc)

    (finished,) = exporter.get_finished_spans()
    assert finished.status.status_code is StatusCode.ERROR
    assert "gemini timed out" in finished.status.description
    assert finished.events[0].name == "exception"


def test_spans_are_harmless_when_tracing_is_off():
    assert tracing.init_tracing(force=True) is False
    with tracing.traced_span("enrichment.run", attributes={"a": 1}) as span:
        tracing.set_token_counts(span, prompt=1, completion=2, total=3)
        tracing.set_span_output(span, {"ok": True})
        assert span.is_recording() is False


# ── enrichment wiring ───────────────────────────────────────────────────────
def test_enrichment_run_emits_nested_spans(monkeypatch, tmp_path):
    """End-to-end check of the wiring in enrich_audit.py: one run span, one
    span per batch beneath it, a batch whose Gemini call blew up marked ERROR
    even though the run carries on, and the token/cost roll-up on both."""
    import sys
    from pathlib import Path

    from opentelemetry.trace import StatusCode

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import enrich_audit

    exporter = _traced_provider(monkeypatch)

    class _Item:
        def __init__(self, fid):
            self.finding_id = fid
            self.dynamic_reason = "dynamic reason"
            self.dynamic_suggested_fix = "dynamic fix"
            self.user_impact = ""
            self.confidence = "high"

    class _Usage:
        prompt_token_count = 120
        candidates_token_count = 60
        thoughts_token_count = 10
        cached_content_token_count = 0
        tool_use_prompt_token_count = 0
        total_token_count = 190

    calls = {"n": 0}

    def _fake_batch(_client, _model, chunk, _system_instruction, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("gemini exploded")
        return [_Item(entry["finding_id"]) for entry in chunk], _Usage(), 0

    monkeypatch.setattr(enrich_audit, "call_gemini_batch", _fake_batch)
    monkeypatch.setattr(enrich_audit.genai, "Client", lambda **_kwargs: object())
    monkeypatch.setattr(enrich_audit.time, "sleep", lambda *_a: None)

    report = {
        "violations": [
            {"finding_id": f"f{i}", "wcag_sc": "1.1.1", "element": {"tag": "img"}}
            for i in range(4)
        ]
    }
    enrich_audit.run_enrichment(
        report=report,
        output_dir=tmp_path,
        batch_size=2,
        api_key="fake-key",
        print_table=False,
        session_id="job-abc",
        mutate_in_place=True,
    )

    spans = {s.name: s for s in exporter.get_finished_spans()}
    batches = [s for s in exporter.get_finished_spans() if s.name == "enrichment.batch"]
    run = spans["enrichment.run"]

    assert run.parent is None
    assert len(batches) == 2
    assert all(b.parent.span_id == run.context.span_id for b in batches)
    assert all(b.attributes[tracing.SESSION_ID] == "job-abc" for b in batches)
    assert run.attributes["enrichment.violation_count"] == 4
    assert [b.status.status_code for b in batches] == [StatusCode.UNSET, StatusCode.ERROR]
    # The failed batch is still swallowed — the run finishes and enriches the rest.
    assert report["violations"][0]["dynamic_reason"] == "dynamic reason"
    assert report["violations"][2]["dynamic_enrichment_failed"] is True

    # ── token / cost accounting ──────────────────────────────────────────
    # Only the first batch returned usage (the second raised), so the run
    # totals must equal that one batch — a run that double-counted or that
    # credited the failed batch would still "have tokens", which is why the
    # exact numbers are asserted rather than mere presence.
    ok_batch = batches[0]
    assert ok_batch.attributes[tracing.TOKEN_COUNT_PROMPT] == 120
    # Thought tokens are billed as output, so they belong in the completion
    # count Arize rolls cost up from: 60 candidates + 10 thoughts.
    assert ok_batch.attributes[tracing.TOKEN_COUNT_COMPLETION] == 70
    assert ok_batch.attributes[tracing.TOKEN_COUNT_TOTAL] == 190
    assert ok_batch.attributes[attributes.LLM_TOKEN_COUNT_THOUGHTS] == 10
    # The failed batch never saw a usage object; it must carry no counts at
    # all rather than zeros, so averages aren't dragged down by phantom calls.
    assert not any(
        key.startswith("llm.token_count") for key in batches[1].attributes
    )

    assert run.attributes[tracing.TOKEN_COUNT_PROMPT] == 120
    assert run.attributes[tracing.TOKEN_COUNT_COMPLETION] == 70
    assert run.attributes[tracing.TOKEN_COUNT_TOTAL] == 190
    assert run.attributes[attributes.ENRICH_API_CALLS] == 2
    assert run.attributes[attributes.ENRICH_FAILURES] == 1
    # run_enrichment()'s default prices are USD 1.50 / 7.50 per 1M tokens:
    # (120 * 1.50 + 70 * 7.50) / 1e6.
    assert run.attributes[attributes.ENRICH_COST_USD] == pytest.approx(0.000705)
    assert any(e.name == "enrichment.batches_failed" for e in run.events)

    # token_usage.json is the on-disk mirror of the same numbers — the two
    # sinks are populated from one place and must not drift.
    import json

    usage_file = json.loads((tmp_path / "token_usage.json").read_text())
    assert usage_file["totals"]["total_tokens"] == 190
    assert usage_file["totals"]["estimated_cost_usd"] == pytest.approx(0.000705)
