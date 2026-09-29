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

    async def _spy(hostname):
        called["resolved"] = True
        return ["127.0.0.1"]

    original = routes._resolve_all_ips
    routes._resolve_all_ips = _spy
    try:
        try:
            await routes.assert_public_url("http://localhost-alias.test/")
        except Exception:
            pass
    finally:
        routes._resolve_all_ips = original

    assert called["resolved"], (
        "_resolve_all_ips never called — the DNS branch is unreachable"
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

    async def _internal(hostname):
        return ["10.4.2.17", "192.168.5.9"]

    original = routes._resolve_all_ips
    routes._resolve_all_ips = _internal
    try:
        with pytest.raises(HTTPException) as exc:
            await routes.assert_public_url("http://db.internal.test/")
    finally:
        routes._resolve_all_ips = original

    detail = str(exc.value.detail)
    leaked = re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", detail)
    assert not leaked, f"rejection leaked resolved address(es): {leaked} in {detail!r}"


async def test_unresolvable_and_blocked_hosts_are_indistinguishable():
    """
    A different message for "does not resolve" and "resolves internally" is a
    DNS oracle: it confirms whether an internal hostname exists.
    """
    import socket

    from fastapi import HTTPException

    from ka11y.api.v1.combined import routes

    async def _internal(hostname):
        return ["10.4.2.17"]

    async def _nxdomain(hostname):
        raise socket.gaierror("nope")

    messages = []
    original = routes._resolve_all_ips
    try:
        for fake in (_internal, _nxdomain):
            routes._resolve_all_ips = fake
            with pytest.raises(HTTPException) as exc:
                await routes.assert_public_url("http://probe.internal.test/")
            messages.append(str(exc.value.detail))
    finally:
        routes._resolve_all_ips = original

    assert messages[0] == messages[1], (
        f"the two rejections differ and can be told apart: {messages!r}"
    )
