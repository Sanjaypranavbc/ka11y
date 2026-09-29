"""
S2-03 error handling — the API surface.

Skipped until the venv carries the dependencies history-and-auth added
(``poetry install``). Offline: no browser, no network.
"""
import pytest

pytest.importorskip(
    "sqlalchemy",
    reason="venv predates history-and-auth; run `poetry install`",
)

from fastapi.testclient import TestClient  # noqa: E402

from ka11y.main import app  # noqa: E402
from ka11y.api.v1.combined import store as combined_store  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ── Input validation (leaves 1.1–1.5) ────────────────────────────────────────

BAD_URLS = [
    ("", "url_empty"),
    ("notaurl", "url_malformed"),
    ("example.com", "url_missing_scheme"),
    ("ftp://example.com", "url_unsupported_scheme"),
    ("http://example.com:99999", "url_invalid_port"),
]


@pytest.mark.parametrize("bad_url,expected_code", BAD_URLS)
def test_json_endpoint_returns_specific_validation_code(client, bad_url, expected_code):
    """Each bad URL gets its own code, not FastAPI's raw 422 body."""
    resp = client.post("/api/v1/combined/python-audit", json={"url": bad_url})
    assert resp.status_code == 422, f"got {resp.status_code}: {resp.text[:200]}"
    assert resp.json().get("error_code") == expected_code, resp.json()


@pytest.mark.parametrize("bad_url,_code", BAD_URLS)
def test_query_endpoint_returns_422_not_500(client, bad_url, _code):
    """
    /combined-audit builds CombinedRequest inside the handler, so a bad URL
    raises pydantic.ValidationError rather than RequestValidationError — an
    unhandled exception producing 500 instead of 422.
    """
    resp = client.post(f"/api/v1/combined/combined-audit?url={bad_url}")
    assert resp.status_code == 422, (
        f"expected 422 for {bad_url!r}, got {resp.status_code}"
    )


# ── The failed-job payload ───────────────────────────────────────────────────

def test_failed_job_exposes_error_code(client):
    """error_code is new; error keeps its English text for older UI builds."""
    job_id = "test-job-error-code"
    combined_store._jobs[job_id] = {
        "job_id": job_id,
        "status": "failed",
        "url": "https://example.com",
        "submitted_at": "2026-09-25T00:00:00+00:00",
        "lang": "en",
        "completed_at": "2026-09-25T00:00:00+00:00",
        "error": "Audit failed due to an internal error.",
        "error_code": "dns_resolution_failed",
        "error_id": "deadbeef",
        "error_stage": "universal_page",
        "current_stage": None,
        "stages": [],
        "result": None,
    }
    try:
        body = client.get(f"/api/v1/combined/{job_id}").json()
        assert body.get("error_code") == "dns_resolution_failed", body
        assert body.get("error") == "Audit failed due to an internal error.", (
            "the English fallback must survive for older UI builds"
        )
    finally:
        combined_store._jobs.pop(job_id, None)


# ── SSRF admission gate (leaf 5.1) ───────────────────────────────────────────

async def test_ssrf_gate_resolves_dns_before_admitting():
    """
    assert_public_url must reach its DNS-resolution branch for a hostname.
    Today _is_non_public_ip swallows the ValueError for a non-IP string, so
    the function returns before resolving anything.
    """
    from ka11y.api.v1.combined import routes

    called = {"resolved": False}

    def _spy(hostname):
        called["resolved"] = True
        return ("127.0.0.1",)

    original = routes._resolve_hostname
    routes._resolve_hostname = _spy
    try:
        try:
            await routes.assert_public_url("http://localhost-alias.test/")
        except Exception:
            pass
    finally:
        routes._resolve_hostname = original

    assert called["resolved"], (
        "_resolve_hostname never called — the DNS branch is unreachable"
    )


# ── Item A: the crawl failure carries the reason (leaves 2.1–2.4, 4.4) ───────

async def test_zero_pages_failure_carries_the_collected_code(tmp_path, monkeypatch):
    """
    The crawler records why each page failed. When every page fails the run
    ends with "0 pages extracted" — and today that discards the reason, so
    the user is told only that something went wrong.
    """
    from ka11y.api.v1.combined import stages
    from ka11y.crawler.snapshot_normalizer import (
        NormalizedPageSnapshot,
        SnapshotNormalizer,
    )

    failed = NormalizedPageSnapshot(
        page_url="https://x.test",
        pages_crawled=0,
        warnings=[
            {
                "code": "dns_resolution_failed",
                "page_url": "https://x.test",
                "message": "dns_resolution_failed host=x.test",
            }
        ],
    )

    async def _fake_load(**kwargs):
        return failed

    monkeypatch.setattr(stages.UniversalPageLoader, "load", staticmethod(_fake_load))
    monkeypatch.setattr(
        stages.UniversalPageLoader, "save_snapshot", staticmethod(lambda *a, **k: None)
    )
    monkeypatch.setattr(
        SnapshotNormalizer, "normalize", classmethod(lambda cls, snap, **k: failed)
    )
    stages._jobs["item-a-job"] = {"warnings": []}

    try:
        with pytest.raises(Exception) as exc:
            await stages._load_universal_snapshot(
                url="https://x.test",
                output_dir=tmp_path,
                max_depth=0,
                job_id="item-a-job",
                step_logger=None,
            )
    finally:
        stages._jobs.pop("item-a-job", None)

    assert getattr(exc.value, "code", None) == "dns_resolution_failed", (
        f"the crawl failure lost the reason; raised {exc.value!r} "
        f"with code={getattr(exc.value, 'code', None)!r}"
    )


# ── The admission gate must not describe the internal network ────────────────

async def test_blocked_host_response_names_no_ip_address():
    """
    assert_public_url's DNS branch was unreachable until the Stage 1 fix. Now
    that it runs, its message must not report the resolved address: a caller
    who can submit audits would otherwise be able to look up internal DNS by
    reading the rejection.
    """
    import re

    from fastapi import HTTPException

    from ka11y.api.v1.combined import routes

    def _internal(hostname):
        return ("10.4.2.17", "192.168.5.9")

    original = routes._resolve_hostname
    routes._resolve_hostname = _internal
    try:
        with pytest.raises(HTTPException) as exc:
            await routes.assert_public_url("http://db.internal.test/")
    finally:
        routes._resolve_hostname = original

    detail = str(exc.value.detail)
    leaked = re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", detail)
    assert not leaked, f"rejection leaked resolved address(es): {leaked} in {detail!r}"


async def test_unresolvable_and_blocked_hosts_are_indistinguishable():
    """
    A different message for "does not resolve" and "resolves internally" is a
    DNS oracle: it confirms whether an internal hostname exists.
    """
    from fastapi import HTTPException

    from ka11y.api.v1.combined import routes

    def _internal(hostname):
        return ("10.4.2.17",)

    def _nxdomain(hostname):
        return ()  # _resolve_hostname's answer when the name does not resolve

    messages = []
    original = routes._resolve_hostname
    try:
        for fake in (_internal, _nxdomain):
            routes._resolve_hostname = fake
            with pytest.raises(HTTPException) as exc:
                await routes.assert_public_url("http://probe.internal.test/")
            messages.append(str(exc.value.detail))
    finally:
        routes._resolve_hostname = original

    assert messages[0] == messages[1], (
        f"the two rejections differ and can be told apart: {messages!r}"
    )


# ── Step 2 gaps: crashes and leaked internals (2b, 2d, 2e, 2f) ───────────────

async def test_stage_failure_reaches_the_client_without_exception_text(monkeypatch):
    """
    2b. A failed stage copied str(exc) into warnings, stages[].error, the SSE
    stage_error event and the /timings row. The failure itself must still be
    recorded; only the internal text must stay server-side.
    """
    import json

    from ka11y.api.v1.combined import stage_events

    broadcasts, timings = [], []
    monkeypatch.setattr(
        stage_events, "_fire_broadcast", lambda job_id, event, data: broadcasts.append(data)
    )
    monkeypatch.setattr(
        stage_events, "_emit_stage_timing", lambda **kwargs: timings.append(kwargs)
    )

    job_id = "test-stage-error-text"
    combined_store._jobs[job_id] = {
        "job_id": job_id,
        "stages": [{"name": "image_audit", "status": "running", "started_at": "2026-09-29T00:00:00+00:00"}],
        "warnings": [],
    }
    try:
        stage_events._stage_error_and_warn(
            job_id,
            "image_audit",
            FileNotFoundError("[Errno 2] No such file or directory: '/app/crawled_images/x.png'"),
        )
        job = combined_store._jobs[job_id]
        assert job["stages"][0]["status"] == "error", "the failure must still be recorded"
        assert job["warnings"] == [
            "image_audit: internal_error; OCR and image-audit checks were skipped."
        ], job["warnings"]

        visible = json.dumps([job["warnings"], job["stages"], broadcasts, timings])
        for leaked in ("/app/", "Errno", "crawled_images"):
            assert leaked not in visible, f"exception text reached the client: {visible}"
    finally:
        combined_store._jobs.pop(job_id, None)


def test_invalid_email_returns_422_not_500(client):
    """
    2d. /combined-audit checked the email format only inside the handler, so a
    bad address raised pydantic.ValidationError: an unhandled 500.
    """
    resp = client.post(
        "/api/v1/combined/combined-audit?url=https://example.com&email=not-an-email"
    )
    assert resp.status_code == 422, f"expected 422, got {resp.status_code}: {resp.text[:200]}"


def test_job_status_does_not_expose_server_paths(client):
    """2e. report_path was the absolute server path of the report file."""
    job_id = "test-job-report-path"
    combined_store._jobs[job_id] = {
        "job_id": job_id,
        "status": "completed",
        "url": "https://example.com",
        "submitted_at": "2026-09-29T00:00:00+00:00",
        "lang": "en",
        "completed_at": "2026-09-29T00:01:00+00:00",
        "report_path": "/app/output/example.com_ab12cd34_combined/combined_report.json",
        "result": {"summary": {}},
        "current_stage": None,
        "stages": [],
    }
    try:
        body = client.get(f"/api/v1/combined/{job_id}").json()
        assert "report_path" not in body, body
        assert "/app/output" not in json_text(body)
    finally:
        combined_store._jobs.pop(job_id, None)


def json_text(obj) -> str:
    import json

    return json.dumps(obj)


async def test_system_health_names_no_internal_address(monkeypatch):
    """
    2f. /api/v1/system/health needs no sign-in and returned the internal Node
    URL, plus the raw connection error when Node was down.
    """
    import httpx

    from ka11y.api import router as api_router

    class _Down:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url):
            raise httpx.ConnectError("All connection attempts failed: node-internal:3000")

    monkeypatch.setenv("NODE_BASE_URL", "http://node-internal:3000")
    monkeypatch.setattr(api_router.httpx, "AsyncClient", _Down)

    body = await api_router.system_health()
    assert body.get("node") == "down", body
    text = json_text(body)
    for leaked in ("node-internal", "3000", "connection attempts"):
        assert leaked not in text, f"health check leaked {leaked!r}: {body}"


def test_timings_from_the_store_carry_no_exception_text(client, monkeypatch):
    """
    Last Step 2 item. Once a job has left memory, /timings is rebuilt from the
    stage_timings table, whose error column holds repr(exc) of the failed
    step. The row must still say the step failed; the text stays server-side.
    """
    from ka11y.store import repo

    async def _owner(job_id):
        return None

    async def _run(job_id):
        return {"url": "https://example.com", "status": "completed",
                "queue_wait_ms": 0, "wall_ms": 1000}

    async def _timings(job_id):
        return [{"page_url": "https://example.com", "depth": 0, "stage": "media_audit",
                 "sub_stage": "video_analysis", "rule": None, "duration_ms": 12.0,
                 "item_count": None, "status": "error",
                 "error": "ConnectError('All connection attempts failed: node:3000')",
                 "ts": "2026-09-29T00:00:00+00:00"}]

    monkeypatch.setattr(repo, "get_owner", _owner)
    monkeypatch.setattr(repo, "get_run", _run)
    monkeypatch.setattr(repo, "get_timings", _timings)

    resp = client.get("/api/v1/combined/test-job-timings-store/timings")
    assert resp.status_code == 200, resp.text[:200]
    steps = resp.json()["steps"]
    assert steps[0]["status"] == "error", "the step must still be reported as failed"
    for leaked in ("node:3000", "ConnectError", "connection attempts"):
        assert leaked not in resp.text, f"/timings leaked {leaked!r}: {steps}"
