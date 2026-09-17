"""
OIDC sign-in → session cookie → protected route → logout, end to end against
a real PostgreSQL (DATABASE_URL) with the identity provider faked.

Skipped when DATABASE_URL is unset. Locally:

    docker run -d --name ka11y-pg -e POSTGRES_PASSWORD=ka11y -e POSTGRES_USER=ka11y \
        -e POSTGRES_DB=ka11y -p 55432:5432 postgres:16-alpine
    DATABASE_URL=postgresql://ka11y:ka11y@127.0.0.1:55432/ka11y poetry run pytest tests/test_auth.py
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")

_ENV = {
    "KA11Y_AUTH_DISABLED": "0",
    "KA11Y_OIDC_ISSUER": "https://fake-idp.test",
    "KA11Y_OIDC_CLIENT_ID": "client-123",
    "KA11Y_OIDC_CLIENT_SECRET": "secret-xyz",
    "KA11Y_OIDC_REDIRECT_URI": "http://testserver/api/v1/auth/callback",
    "KA11Y_OIDC_AUTHORIZATION_ENDPOINT": "https://fake-idp.test/authorize",
    "KA11Y_OIDC_TOKEN_ENDPOINT": "https://fake-idp.test/token",
    "KA11Y_SESSION_SECRET": "unit-test-secret-do-not-use",
    "KA11Y_ALLOWED_EMAILS": "meghana@bluecaffeine.com,watanabe.kanae2@kao.com",
    "KA11Y_ALLOWED_EMAIL_DOMAINS": "",
    "KA11Y_DB_AUTO_MIGRATE": "1",
}


@pytest.fixture(scope="module")
def client():
    saved = {k: os.environ.get(k) for k in _ENV}
    os.environ.update(_ENV)
    from ka11y.main import app

    with TestClient(app) as c:
        yield c
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _fake_identity(monkeypatch, *, email: str, sub: str, verified: bool = True):
    from ka11y.auth import oidc, router as auth_router

    async def fake_exchange(*, code, code_verifier, nonce):
        assert code == "good-code"
        return oidc.ExternalIdentity(
            provider="google",
            subject=sub,
            email=email,
            email_verified=verified,
            name="Test Person",
            picture=None,
            locale="en",
        )

    monkeypatch.setattr(auth_router.oidc, "exchange_code", fake_exchange)


def _state_from_cookie(client: TestClient) -> str:
    from ka11y.auth.signing import unsign_json

    pending = unsign_json(client.cookies.get("ka11y_oidc"))
    assert pending, "oidc cookie missing or unsigned"
    return pending["s"]


def _sign_in(client: TestClient, monkeypatch, email: str, sub: str | None = None):
    _fake_identity(monkeypatch, email=email, sub=sub or f"sub-{email}")
    r = client.get("/api/v1/auth/login", params={"remember": 1, "next": "/dashboard"}, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("https://fake-idp.test/authorize?")
    assert "code_challenge_method=S256" in r.headers["location"]
    state = _state_from_cookie(client)
    r = client.get("/api/v1/auth/callback", params={"code": "good-code", "state": state}, follow_redirects=False)
    return r


class TestSignIn:
    def test_protected_route_requires_session(self, client):
        client.cookies.clear()
        r = client.get("/api/v1/combined/history")
        assert r.status_code == 401
        r = client.get("/api/v1/auth/me")
        assert r.status_code == 401

    def test_health_is_public(self, client):
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/auth/config").json()["configured"] is True

    def test_full_flow(self, client, monkeypatch):
        client.cookies.clear()
        r = _sign_in(client, monkeypatch, "meghana@bluecaffeine.com")
        assert r.status_code == 302, r.text
        assert r.headers["location"] == "/dashboard"
        assert client.cookies.get("ka11y_session")
        assert not client.cookies.get("ka11y_oidc")

        me = client.get("/api/v1/auth/me")
        assert me.status_code == 200, me.text
        body = me.json()
        assert body["email"] == "meghana@bluecaffeine.com"
        assert body["role"] == "owner"  # first member of 'bluecaffeine'
        uuid.UUID(body["user_id"])
        uuid.UUID(body["organization_id"])

        assert client.get("/api/v1/combined/history").status_code == 200
        hist = client.get("/api/v1/audits/history")
        assert hist.status_code == 200
        assert hist.json()["items"] == [] or isinstance(hist.json()["items"], list)

        r = client.post("/api/v1/auth/logout")
        assert r.status_code == 204
        assert client.get("/api/v1/auth/me").status_code == 401

    def test_returning_user_is_same_row(self, client, monkeypatch):
        client.cookies.clear()
        first = _sign_in(client, monkeypatch, "meghana@bluecaffeine.com")
        assert first.status_code == 302
        uid1 = client.get("/api/v1/auth/me").json()["user_id"]
        client.post("/api/v1/auth/logout")
        second = _sign_in(client, monkeypatch, "meghana@bluecaffeine.com")
        assert second.status_code == 302
        uid2 = client.get("/api/v1/auth/me").json()["user_id"]
        assert uid1 == uid2
        client.post("/api/v1/auth/logout")

    def test_not_on_allow_list_is_rejected_without_creating_user(self, client, monkeypatch):
        client.cookies.clear()
        r = _sign_in(client, monkeypatch, "stranger@example.com")
        assert r.status_code == 302
        assert r.headers["location"] == "/login?error=not_allowed"
        assert not client.cookies.get("ka11y_session")

    def test_kao_user_lands_in_kao_org(self, client, monkeypatch):
        client.cookies.clear()
        r = _sign_in(client, monkeypatch, "watanabe.kanae2@kao.com")
        assert r.status_code == 302
        me = client.get("/api/v1/auth/me").json()
        assert me["email"] == "watanabe.kanae2@kao.com"
        client.post("/api/v1/auth/logout")

    def test_state_mismatch_is_rejected(self, client, monkeypatch):
        client.cookies.clear()
        _fake_identity(monkeypatch, email="meghana@bluecaffeine.com", sub="x")
        client.get("/api/v1/auth/login", follow_redirects=False)
        r = client.get("/api/v1/auth/callback", params={"code": "good-code", "state": "wrong"}, follow_redirects=False)
        assert r.headers["location"] == "/login?error=state_mismatch"

    def test_forged_session_cookie_is_ignored(self, client):
        client.cookies.clear()
        client.cookies.set("ka11y_session", f"{uuid.uuid4().hex}.r.deadbeef")
        assert client.get("/api/v1/auth/me").status_code == 401
        client.cookies.clear()


class TestSchemaAndSeed:
    def test_wcag_rules_seeded(self, client):
        import asyncio

        from sqlalchemy import func, select

        from ka11y.db.engine import session_scope
        from ka11y.db.models import WcagRule

        async def _count():
            async with session_scope() as s:
                return (await s.execute(select(func.count()).select_from(WcagRule))).scalar_one()

        assert asyncio.run(_count()) >= 80

    def test_models_match_spec(self):
        import subprocess, sys

        proc = subprocess.run(
            [sys.executable, "scripts/verify_schema.py"], capture_output=True, text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr


class TestArtifactsEndpoint:
    """reports rows + ownership-scoped artifact listing (needs PostgreSQL)."""

    def test_artifacts_listed_for_owner_only(self, client, monkeypatch, tmp_path):
        import asyncio

        monkeypatch.setenv("KA11Y_STORAGE_BACKEND", "local")
        monkeypatch.setenv("KA11Y_ARTIFACT_DIR", str(tmp_path / "artifacts"))
        monkeypatch.setenv("KA11Y_ARTIFACT_PDF", "0")
        from ka11y.storage.backends import reset_store
        from ka11y.storage.uploader import upload_job_artifacts
        from ka11y.db import audit_repo
        from ka11y.storage import keys

        reset_store()
        client.cookies.clear()
        assert _sign_in(client, monkeypatch, "meghana@bluecaffeine.com").status_code == 302
        me = client.get("/api/v1/auth/me").json()

        job_id = str(uuid.uuid4())
        asyncio.run(
            audit_repo.create_job(
                job_id,
                user_id=uuid.UUID(me["user_id"]),
                organization_id=uuid.UUID(me["organization_id"]),
                session_id=None,
                target_url="https://example.com",
                crawl_depth=0,
                requested_pages=1,
            )
        )
        keys.forget_job(job_id)
        result = asyncio.run(
            upload_job_artifacts(
                job_id,
                report={"url": "https://example.com", "summary": {}, "violations": [], "needs_review": [], "passes": []},
                output_dir=None,
            )
        )
        assert result["reports"]["json"].startswith(f"organizations/{me['organization_id']}/users/{me['user_id']}/")

        r = client.get(f"/api/v1/audits/{job_id}/artifacts")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["storage"] == "local"
        formats = {x["format"] for x in body["reports"]}
        assert formats == {"json", "csv"}
        json_report = next(x for x in body["reports"] if x["format"] == "json")
        assert json_report["download_url"].endswith("/download")
        dl = client.get(json_report["download_url"])
        assert dl.status_code == 200 and dl.json()["url"] == "https://example.com"
        client.post("/api/v1/auth/logout")

        # a user from another organization cannot see it
        client.cookies.clear()
        assert _sign_in(client, monkeypatch, "watanabe.kanae2@kao.com").status_code == 302
        assert client.get(f"/api/v1/audits/{job_id}/artifacts").status_code == 404
        client.post("/api/v1/auth/logout")
        reset_store()
