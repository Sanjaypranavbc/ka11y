"""Transport hardening: security headers, HSTS, https redirect, body cap,
rate-limit buckets and the PostgreSQL TLS default. No DB needed."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    saved = {k: os.environ.get(k) for k in ("KA11Y_AUTH_DISABLED", "KA11Y_OIDC_REDIRECT_URI", "KA11Y_COOKIE_SECURE", "KA11Y_FORCE_HTTPS")}
    os.environ["KA11Y_AUTH_DISABLED"] = "1"
    os.environ["KA11Y_OIDC_REDIRECT_URI"] = "https://a11y.example/api/v1/auth/callback"
    # Explicit: ka11y.main calls load_dotenv(), and a developer .env commonly
    # carries KA11Y_COOKIE_SECURE=0 for plain-http local use.
    os.environ["KA11Y_COOKIE_SECURE"] = "1"
    os.environ["KA11Y_FORCE_HTTPS"] = "1"
    from ka11y.main import app

    with TestClient(app, base_url="https://a11y.example") as c:
        yield c
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_security_headers_on_https(client):
    r = client.get("/api/v1/auth/config")
    h = r.headers
    assert h["Strict-Transport-Security"].startswith("max-age=31536000")
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"]
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"
    assert h["Cross-Origin-Opener-Policy"] == "same-origin"
    assert "camera=()" in h["Permissions-Policy"]
    assert "Server" not in h or "uvicorn" not in h.get("Server", "")


def test_docs_page_is_exempt_from_csp_only(client):
    r = client.get("/docs")
    assert "Content-Security-Policy" not in r.headers
    assert r.headers["X-Frame-Options"] == "DENY"


def test_plain_http_is_redirected(client):
    r = client.get("http://a11y.example/api/v1/auth/config", follow_redirects=False)
    assert r.status_code == 308
    assert r.headers["location"] == "https://a11y.example/api/v1/auth/config"
    assert "Strict-Transport-Security" not in r.headers


def test_loopback_and_health_are_not_redirected(client):
    assert client.get("http://localhost/api/v1/auth/config", follow_redirects=False).status_code == 200


def test_body_cap(client):
    from ka11y.main import _BodyLimitMiddleware

    big = b"x" * (_BodyLimitMiddleware.MAX_BYTES + 1)
    r = client.post("/api/v1/auth/password/login", content=big, headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    r = client.post(
        "/api/v1/auth/password/login",
        content=big,
        headers={"Content-Type": "application/json", "Transfer-Encoding": "chunked"},
    )
    assert r.status_code == 413


def test_auth_rate_bucket(client):
    from ka11y.main import _RateLimitMiddleware

    saved = _RateLimitMiddleware._MAX_AUTH_REQUESTS
    _RateLimitMiddleware._MAX_AUTH_REQUESTS = 3
    try:
        codes = [client.get("/api/v1/auth/login", follow_redirects=False).status_code for _ in range(5)]
    finally:
        _RateLimitMiddleware._MAX_AUTH_REQUESTS = saved
    assert 429 in codes
    assert codes[-1] == 429
    assert client.get("/api/v1/auth/config").status_code == 200  # GET config is not in the bucket


@pytest.mark.parametrize(
    "url, override, expected",
    [
        ("postgresql://u:p@db.example.com:5432/ka11y", "", "sslmode=require"),
        ("postgresql://u:p@postgres:5432/ka11y", "", ""),
        ("postgresql://u:p@127.0.0.1:55432/ka11y", "", ""),
        ("postgresql://u:p@db.example.com/ka11y?sslmode=disable", "", "sslmode=disable"),
        ("postgresql://u:p@postgres/ka11y", "verify-full", "sslmode=verify-full"),
    ],
)
def test_db_url_tls_default(monkeypatch, url, override, expected):
    from ka11y.db.engine import apply_tls_default, normalize_url

    monkeypatch.setenv("KA11Y_DB_SSLMODE", override)
    monkeypatch.delenv("KA11Y_DB_SSLROOTCERT", raising=False)
    out = apply_tls_default(normalize_url(url))
    assert out.startswith("postgresql+psycopg://")
    if expected:
        assert expected in out
    else:
        assert "sslmode" not in out


def test_db_url_rootcert(monkeypatch):
    from ka11y.db.engine import apply_tls_default

    monkeypatch.setenv("KA11Y_DB_SSLMODE", "verify-full")
    monkeypatch.setenv("KA11Y_DB_SSLROOTCERT", "/certs/rds.pem")
    out = apply_tls_default("postgresql+psycopg://u:p@db.example.com/ka11y")
    assert "sslmode=verify-full" in out and "sslrootcert=%2Fcerts%2Frds.pem" in out
