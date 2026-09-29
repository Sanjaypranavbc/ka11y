"""
Sprint-1 fix #8: API error responses must never leak exception types,
messages, file paths, or tracebacks. Clients get an opaque error_id +
a generic message; operators correlate via the server log.
"""
import re

import pytest
from fastapi.testclient import TestClient

from ka11y.main import app
from ka11y.api.v1.combined import store as combined_store


SENSITIVE_TOKENS = re.compile(
    r"Traceback|File \"|line \d+|/home/|/usr/|/opt/|ValueError|TypeError|"
    r"RuntimeError|AttributeError|KeyError"
)


@pytest.fixture()
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


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
        assert not SENSITIVE_TOKENS.findall(str(body))
    finally:
        combined_store._jobs.pop(job_id, None)
