"""Tests for the end-to-end instrumentation built on ka11y/observability.

test_tracing.py covers the tracing module itself (configuration, exporters,
the span helpers). This file covers the *wiring*: that an HTTP request, a
crawled page, a timed stage, a rule engine and an audit job each produce the
span they are supposed to, with the attributes a dashboard filters on.

Everything runs against an in-memory exporter; nothing talks to Arize.
"""

from __future__ import annotations

import asyncio

import pytest

from ka11y.observability import attributes as attrs
from ka11y.observability import spans as obs_spans
from ka11y.observability import tracing


@pytest.fixture(autouse=True)
def _reset_tracing_state(monkeypatch):
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
        "KA11Y_TRACING_MAX_ATTR_CHARS",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(tracing, "load_dotenv", lambda *a, **k: False)
    tracing.shutdown_tracing()
    yield
    tracing.shutdown_tracing()


@pytest.fixture
def exporter(monkeypatch):
    """Wire the tracing module to an SDK provider that exports into memory."""
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    provider = TracerProvider()
    exp = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exp))

    monkeypatch.setenv("ARIZE_SPACE_ID", "space")
    monkeypatch.setenv("ARIZE_API_KEY", "key")
    monkeypatch.setattr(tracing, "_register_arize", lambda *a, **k: provider)
    monkeypatch.setattr(tracing, "_instrument_google_genai", lambda _p: True)
    assert tracing.init_tracing(force=True) is True
    return exp


def _by_name(exporter, name):
    return [s for s in exporter.get_finished_spans() if s.name == name]


def _one(exporter, name):
    found = _by_name(exporter, name)
    assert len(found) == 1, f"expected exactly one {name!r}, got {len(found)}"
    return found[0]


# ── attribute hygiene ───────────────────────────────────────────────────────
def test_long_attributes_are_truncated(exporter, monkeypatch):
    """A page snapshot or a batch of violations can be megabytes. An oversized
    attribute doesn't fail on its own — it blows the collector's message limit
    and takes the whole batch of spans with it, so it must be clipped here."""
    monkeypatch.setenv("KA11Y_TRACING_MAX_ATTR_CHARS", "128")

    with tracing.traced_span("t") as span:
        tracing.set_span_input(span, "x" * 10_000)
        tracing.set_span_attributes(span, {"ka11y.big": "y" * 10_000})

    finished = _one(exporter, "t")
    assert len(finished.attributes[tracing.INPUT_VALUE]) == 128
    assert finished.attributes[tracing.INPUT_VALUE].endswith("[truncated]")
    assert len(finished.attributes["ka11y.big"]) == 128


def test_setting_attributes_never_raises(exporter):
    """Instrumentation must not be able to fail an audit. A value OTel rejects
    is dropped with a debug log, not propagated."""

    class _Explosive:
        def __repr__(self):
            raise RuntimeError("nope")

    with tracing.traced_span("t") as span:
        tracing.set_span_attributes(span, {"ka11y.bad": _Explosive(), "ka11y.ok": 1})

    assert _one(exporter, "t").attributes["ka11y.ok"] == 1


# ── deferred work: root span + link ─────────────────────────────────────────
def test_deferred_work_starts_its_own_trace_and_links_back(exporter):
    """The audit is submitted by a fast request and runs for minutes after it.
    Nesting would give the trace a root that ends before its children, so the
    job is a root span of its own that *links* to the request instead."""
    with tracing.traced_span("http.request") as request_span:
        link = tracing.capture_context()
        request_trace_id = request_span.get_span_context().trace_id

    with tracing.traced_span("audit.job", root=True, link_to=link):
        with tracing.traced_span("audit.python_stages"):
            pass

    job = _one(exporter, "audit.job")
    stages = _one(exporter, "audit.python_stages")

    assert job.parent is None
    assert job.context.trace_id != request_trace_id
    # ...but the request is still one click away.
    assert [link.context.trace_id for link in job.links] == [request_trace_id]
    # And work inside the job is genuinely nested under it.
    assert stages.parent.span_id == job.context.span_id
    assert stages.context.trace_id == job.context.trace_id


def test_capture_context_is_none_without_a_span():
    """A job started by the durable queue has no request to link to."""
    assert tracing.init_tracing(force=True) is False
    assert tracing.capture_context() is None


# ── stage / rule execution via stage_timing ─────────────────────────────────
def test_time_stage_emits_a_rule_span(exporter):
    from ka11y.utils import stage_timing

    with stage_timing.time_stage(
        "job-1",
        "image_audit",
        sub_stage="ocr_converter",
        rule="1.4.3",
        page_url="https://example.com/a",
        extra={"input_count": 7},
    ):
        pass

    span = _one(exporter, "rule.1.4.3")
    assert span.attributes[attrs.STAGE] == "image_audit"
    assert span.attributes[attrs.SUB_STAGE] == "ocr_converter"
    assert span.attributes[attrs.RULE] == "1.4.3"
    assert span.attributes[attrs.PAGE_URL] == "https://example.com/a"
    assert span.attributes["ka11y.extra.input_count"] == 7
    assert span.attributes[attrs.STATUS] == "ok"
    assert span.attributes[attrs.DURATION_MS] >= 0


def test_time_stage_without_a_rule_is_named_for_the_stage(exporter):
    from ka11y.utils import stage_timing

    with stage_timing.time_stage("job-1", "image_audit", sub_stage="ocr_scan"):
        pass

    _one(exporter, "stage.image_audit.ocr_scan")


@pytest.mark.asyncio
async def test_time_stage_async_records_a_failure(exporter):
    from opentelemetry.trace import StatusCode

    from ka11y.utils import stage_timing

    with pytest.raises(ValueError):
        async with stage_timing.time_stage_async("job-1", "media_audit"):
            raise ValueError("boom")

    span = _one(exporter, "stage.media_audit")
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes[attrs.STATUS] == "error"


def test_stage_timing_still_writes_its_row_when_tracing_is_off(tmp_path, monkeypatch):
    """The span is an addition to the JSONL/SQLite timing sinks, never a
    replacement — an unconfigured deployment must lose nothing."""
    from ka11y.utils import stage_timing

    monkeypatch.setenv("KA11Y_STAGE_TIMING_DIR", str(tmp_path))
    assert tracing.init_tracing(force=True) is False

    with stage_timing.time_stage("job-off", "image_audit", rule="1.1.1"):
        pass

    rows = (tmp_path / "job-off.jsonl").read_text().strip().splitlines()
    assert len(rows) == 1
    assert '"rule": "1.1.1"' in rows[0]


# ── crawler + page processing ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_time_crawler_emits_a_crawler_span(exporter, tmp_path):
    from ka11y.utils.crawler_timing import time_crawler

    async with time_crawler(
        tmp_path, "image", "https://example.com", pages_getter=lambda: 4
    ):
        pass

    span = _one(exporter, "crawler.image")
    assert span.attributes[attrs.CRAWLER_NAME] == "image"
    assert span.attributes[attrs.PAGE_URL] == "https://example.com"
    assert span.attributes[attrs.CRAWLER_PAGES_CRAWLED] == 4


@pytest.mark.asyncio
async def test_page_spans_nest_under_the_crawler_span(exporter, tmp_path):
    from ka11y.utils.crawler_timing import time_crawler

    async with time_crawler(tmp_path, "universal", "https://example.com"):
        with obs_spans.page_span("https://example.com/a", 0, crawler="universal"):
            obs_spans.stamp_page_outcome(status="captured", links_found=12)

    page = _one(exporter, attrs.SPAN_CRAWLER_PAGE)
    crawl = _one(exporter, "crawler.universal")
    assert page.parent.span_id == crawl.context.span_id
    assert page.attributes[attrs.PAGE_DEPTH] == 0
    assert page.attributes[attrs.PAGE_LINKS_FOUND] == 12
    assert page.attributes[attrs.STATUS] == "captured"


def test_a_failed_page_marks_its_span_in_error(exporter):
    """Page failures are swallowed so one bad child can't sink the snapshot —
    which is precisely why the span has to carry the error, or a crawl that
    reached nothing looks identical to a clean one."""
    from opentelemetry.trace import StatusCode

    with obs_spans.page_span("https://example.com/gone", 1):
        obs_spans.stamp_page_outcome(status="failed", error="nav_timeout")

    span = _one(exporter, attrs.SPAN_CRAWLER_PAGE)
    assert span.status.status_code is StatusCode.ERROR
    assert "nav_timeout" in span.status.description


# ── rule engines ────────────────────────────────────────────────────────────
def test_traced_auditor_reports_input_and_record_counts(exporter):
    @obs_spans.traced_auditor("alt_text", rules=("1.1.1", "4.1.2"), input_arg="images")
    def generate(images, ocr):
        return [{"row": i} for i in images]

    assert generate(["a", "b", "c"], []) == [{"row": "a"}, {"row": "b"}, {"row": "c"}]

    span = _one(exporter, "rules.alt_text")
    assert span.attributes[attrs.AUDITOR] == "alt_text"
    assert span.attributes[attrs.RULES] == "1.1.1,4.1.2"
    assert span.attributes[attrs.INPUT_COUNT] == 3
    assert span.attributes[attrs.RECORD_COUNT] == 3


def test_traced_auditor_reads_input_passed_positionally_or_by_keyword(exporter):
    """The real auditors are called both ways — positionally by the media
    stage, by keyword by the image stage — so binding must handle both."""

    @obs_spans.traced_auditor("media", input_arg="items")
    def generate(self, items, run=True):
        return list(items)

    generate(object(), ["x", "y"])
    generate(object(), items=["x", "y", "z"])

    counts = [s.attributes[attrs.INPUT_COUNT] for s in _by_name(exporter, "rules.media")]
    assert sorted(counts) == [2, 3]


@pytest.mark.asyncio
async def test_auditor_span_nests_under_the_stage_across_a_thread_hop(exporter):
    """Auditors run via asyncio.to_thread. That copies the caller's context,
    so the span still lands under the stage — this test is what guarantees the
    trace doesn't fragment if that ever changes."""

    @obs_spans.traced_auditor("alt_text", input_arg="images")
    def generate(images):
        return []

    with tracing.traced_span(attrs.stage_span_name("image_audit")):
        await asyncio.to_thread(generate, ["a"])

    stage = _one(exporter, "stage.image_audit")
    auditor = _one(exporter, "rules.alt_text")
    assert auditor.parent.span_id == stage.context.span_id


# ── HTTP requests ───────────────────────────────────────────────────────────
def _client(**middleware_kwargs):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ka11y.observability.middleware import TracingMiddleware

    app = FastAPI()
    app.add_middleware(TracingMiddleware, **middleware_kwargs)

    @app.get("/api/v1/combined/{job_id}")
    async def get_job(job_id: str):
        return {"job_id": job_id}

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/v1/combined/{job_id}/stream")
    async def stream(job_id: str):
        return {"streaming": job_id}

    @app.get("/api/v1/boom")
    async def boom():
        raise RuntimeError("handler exploded")

    return TestClient(app, raise_server_exceptions=False)


def test_request_span_uses_the_route_template(exporter):
    """The raw path would give every job id its own span name and shatter the
    latency aggregates; OTel wants the template."""
    resp = _client().get("/api/v1/combined/abc-123")
    assert resp.status_code == 200

    span = _one(exporter, "GET /api/v1/combined/{job_id}")
    assert span.attributes[attrs.HTTP_ROUTE] == "/api/v1/combined/{job_id}"
    assert span.attributes[attrs.HTTP_TARGET] == "/api/v1/combined/abc-123"
    assert span.attributes[attrs.HTTP_STATUS_CODE] == 200
    assert span.attributes[attrs.HTTP_METHOD] == "GET"
    assert resp.headers["X-Request-ID"]
    assert resp.headers["X-Trace-ID"] == format(span.context.trace_id, "032x")


def test_supplied_request_id_is_preserved(exporter):
    resp = _client().get(
        "/api/v1/combined/abc-123", headers={"X-Request-ID": "caller-supplied"}
    )
    assert resp.headers["X-Request-ID"] == "caller-supplied"
    span = _one(exporter, "GET /api/v1/combined/{job_id}")
    assert span.attributes[attrs.HTTP_REQUEST_ID] == "caller-supplied"


def test_health_and_stream_endpoints_produce_no_spans(exporter):
    client = _client()
    client.get("/api/v1/health")
    client.get("/api/v1/combined/abc-123/stream")
    # Health checks would dominate span volume; the SSE stream stays open for
    # the whole audit and would swamp every latency percentile.
    assert exporter.get_finished_spans() == ()


def test_a_failing_handler_marks_the_request_span(exporter):
    from opentelemetry.trace import StatusCode

    resp = _client().get("/api/v1/boom")
    assert resp.status_code == 500

    span = _one(exporter, "GET /api/v1/boom")
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes[attrs.HTTP_STATUS_CODE] == 500


def test_no_request_spans_when_tracing_is_off():
    assert tracing.init_tracing(force=True) is False
    resp = _client().get("/api/v1/combined/abc-123")
    assert resp.status_code == 200
    assert resp.json() == {"job_id": "abc-123"}


# ── the audit job's root span ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_audit_job_span_is_a_linked_root_carrying_the_outcome(exporter):
    """The whole design of the audit trace in one test: a job opens its own
    trace (not a child of the request that submitted it), links back to that
    request, groups its spans by session id, and reports the terminal status
    the job recorded rather than an exception — because _run_job_body_inner
    swallows its own failures."""
    from opentelemetry.trace import StatusCode

    from ka11y.api.v1.combined import runner
    from ka11y.api.v1.combined.store import _jobs

    job_id = "obs-test-job"
    _jobs[job_id] = {
        "job_id": job_id,
        "status": "failed",
        "error_id": "deadbeef",
        "error_stage": "image_audit",
        "result": {"summary": {"violations": 3, "needs_review": 1, "passes": 10}},
    }

    class _Payload:
        url = "https://example.com"
        lang = "ja"
        wcag_level = "AA"
        max_depth = 1
        max_pages = 20

    async def _fake_inner(*_args, **_kwargs):
        return None

    try:
        with tracing.traced_span("http.request POST /api/v1/combined/"):
            request_trace_id = tracing.current_span().get_span_context().trace_id
            monkey = runner._run_job_body_inner
            runner._run_job_body_inner = _fake_inner
            try:
                await runner._run_job_body(job_id, _Payload(), filter_rule="1.1.1")
            finally:
                runner._run_job_body_inner = monkey
    finally:
        _jobs.pop(job_id, None)

    span = _one(exporter, attrs.SPAN_AUDIT_JOB)
    assert span.parent is None
    assert span.context.trace_id != request_trace_id
    assert [l.context.trace_id for l in span.links] == [request_trace_id]

    assert span.attributes[tracing.SESSION_ID] == job_id
    assert span.attributes[attrs.JOB_ID] == job_id
    assert span.attributes[attrs.JOB_URL] == "https://example.com"
    assert span.attributes[attrs.JOB_LANG] == "ja"
    assert span.attributes[attrs.JOB_FILTER_RULE] == "1.1.1"

    # Outcome, read back off the job state rather than from a raised exception.
    assert span.attributes[attrs.JOB_STATUS] == "failed"
    assert span.attributes[attrs.VIOLATION_COUNT] == 3
    assert span.attributes[attrs.FINDING_COUNT] == 14
    assert span.status.status_code is StatusCode.ERROR
    # The user-facing error text is deliberately generic; error_id is the
    # thread back to the traceback in the application log.
    assert "deadbeef" in span.status.description
