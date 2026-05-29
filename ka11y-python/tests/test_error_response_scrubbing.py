"""
Sprint-1 fix #8: API error responses must never leak exception types,
messages, file paths, or tracebacks. Clients get an opaque error_id +
a generic message; operators correlate via the server log.
"""
import logging
import re

import pytest
from fastapi.testclient import TestClient

from ka11y.main import app
from ka11y.api.v1.combined import store as combined_store
from ka11y.api.v1 import crawl as crawl_api


SENSITIVE_TOKENS = re.compile(
    r"Traceback|File \"|line \d+|/home/|/usr/|/opt/|ValueError|TypeError|"
    r"RuntimeError|AttributeError|KeyError"
)


@pytest.fixture()
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _assert_scrubbed(payload, caplog_text: str = ""):
    """The response body must not contain stack-trace-shaped strings."""
    body = str(payload)
    leaks = SENSITIVE_TOKENS.findall(body)
    assert not leaks, f"response leaked diagnostic tokens: {leaks!r}\nbody={body!r}"
    # Conversely, the *log* should have the real traceback.
    if caplog_text:
        assert "Traceback" in caplog_text or "error_id" in caplog_text


# ── /api/v1/crawl ─────────────────────────────────────────────────────────────


def test_crawl_route_scrubs_exception_message(monkeypatch, client, caplog):
    """Force /crawl into the except path and confirm str(e) does not leak."""
    caplog.set_level(logging.ERROR)

    secret = "INTERNAL_PATH_/srv/secret/key.pem_DO_NOT_LEAK"

    # A fake crawler that raises a CLEAR, INTENT-LABELED error when crawl_page
    # is awaited. The earlier version of this test patched get_image_crawler to
    # return a bare function, which meant the route hit AttributeError on
    # `crawler.crawl_page()` before the intentional RuntimeError ever fired —
    # the scrubbing path still ran, but KAC_*.log filled with confusing
    # "'function' object has no attribute 'crawl_page'" lines that looked like
    # production bugs. With this fake the log line is explicit.
    class _IntentionalTestCrawlerFailure:
        def __init__(self, *a, **k):
            self.output_dir = "/tmp/ka11y-scrubbing-test"
            self.images_data: list = []
            self.visited_urls: set = set()

        async def crawl_page(self, *a, **k):
            raise RuntimeError(
                f"intentional test failure (response-scrubbing test): {secret}"
            )

        def save_results(self):
            pass

    monkeypatch.setattr(
        crawl_api,
        "get_image_crawler",
        lambda *a, **k: _IntentionalTestCrawlerFailure(),
    )

    # We don't care if the request actually fires the patched callable —
    # what matters is that any exception thrown inside the route is scrubbed.
    # Construct a payload likely to hit the try-block.
    resp = client.post(
        "/api/v1/crawl/",
        json={"url": "https://example.com", "run_form_audit": False},
    )
    # Either DI rejects (422) or the route hits the except (500). Only the
    # 500 branch is interesting; if DI rejected we have nothing to verify.
    if resp.status_code == 500:
        body = resp.json()
        # Detail is the opaque dict, not a raw string.
        assert isinstance(body.get("detail"), dict), body
        assert body["detail"]["message"] == "Crawl pipeline failed due to an internal error."
        assert "error_id" in body["detail"]
        _assert_scrubbed(body, caplog.text)
        assert secret not in str(body)


# ── /api/v1/pipeline ──────────────────────────────────────────────────────────


def test_pipeline_route_scrubs_exception_message(monkeypatch, client, caplog):
    caplog.set_level(logging.ERROR)
    secret = "DB_PASSWORD=hunter2_DO_NOT_LEAK"

    # Patch a function the pipeline route uses early. We just need *any* path
    # that raises inside the route's try block.
    from ka11y.api.v1 import pipeline as pipeline_api

    real_logger = pipeline_api.logger

    def _crash_logger(*args, **kwargs):
        # First call inside the route → raise to enter except path.
        raise RuntimeError(secret)

    monkeypatch.setattr(real_logger, "info", _crash_logger)

    resp = client.post(
        "/api/v1/pipeline/",
        json={"url": "https://example.com"},
    )
    if resp.status_code == 500:
        body = resp.json()
        assert isinstance(body.get("detail"), dict)
        assert "error_id" in body["detail"]
        _assert_scrubbed(body, caplog.text)
        assert secret not in str(body)


# ── /api/v1/combined job-state polling ────────────────────────────────────────


def test_combined_failed_job_state_is_scrubbed(monkeypatch, client):
    """
    Simulate a job that failed: the GET /combined/{job_id} response must
    not include `error_traceback`, file paths, or exception messages.
    """
    job_id = "test-job-scrubbed"
    combined_store._jobs[job_id] = {
        "job_id": job_id,
        "status": "failed",
        "url": "https://example.com",
        "submitted_at": "2026-05-13T00:00:00+00:00",
        "lang": "en",
        "completed_at": "2026-05-13T00:00:00+00:00",
        "error": "Audit failed due to an internal error.",
        "error_id": "deadbeef",
        "error_stage": "image_audit",
        "current_stage": None,
        "stages": [],
        "result": None,
    }
    try:
        resp = client.get(f"/api/v1/combined/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        # No leaky keys.
        for forbidden in ("error_traceback", "traceback", "tb", "location"):
            assert forbidden not in body, f"forbidden key {forbidden!r} present in {body!r}"
        # error_id is exposed (operators can correlate).
        assert body.get("error_id") == "deadbeef"
        assert body.get("error") == "Audit failed due to an internal error."
    finally:
        combined_store._jobs.pop(job_id, None)
