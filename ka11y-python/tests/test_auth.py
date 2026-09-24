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
    "KA11Y_SESSION_SECRET": "unit-test-secret-do-not-use-anywhere-else-0123456789",
    "KA11Y_ALLOWED_EMAILS": "meghana@bluecaffeine.com,watanabe.kanae2@kao.com",
    "KA11Y_ALLOWED_EMAIL_DOMAINS": "",
    "KA11Y_DB_AUTO_MIGRATE": "1",
    # Pin the password-login knobs: ka11y.main calls load_dotenv(), which would
    # otherwise pull the developer's real ka11y-python/.env values (e.g. a
    # bootstrap password or registration turned off) into the test process.
    "KA11Y_PASSWORD_LOGIN": "1",
    "KA11Y_PASSWORD_REGISTRATION": "1",
    "KA11Y_BOOTSTRAP_PASSWORD": "",
    "KA11Y_ADMIN_EMAILS": "",
}


@pytest.fixture(scope="module")
def client():
    saved = {k: os.environ.get(k) for k in _ENV}
    os.environ.update(_ENV)
    from ka11y.main import _RateLimitMiddleware, app

    # The global 30-POSTs-per-minute brake (ka11y.main) would trip inside this
    # module's ~40 sign-in POSTs; the auth-specific brake is tested on its own.
    saved_limit = _RateLimitMiddleware._MAX_REQUESTS
    saved_auth_limit = _RateLimitMiddleware._MAX_AUTH_REQUESTS
    _RateLimitMiddleware._MAX_REQUESTS = 10_000
    _RateLimitMiddleware._MAX_AUTH_REQUESTS = 10_000
    with TestClient(app) as c:
        yield c
    _RateLimitMiddleware._MAX_REQUESTS = saved_limit
    _RateLimitMiddleware._MAX_AUTH_REQUESTS = saved_auth_limit
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
        import subprocess
        import sys

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


class TestPasswordHashing:
    """Pure functions — no database needed (module-level skip still applies)."""

    def test_roundtrip_and_format(self):
        from ka11y.auth.passwords import hash_password, needs_rehash, verify_password

        h = hash_password("correct horse battery staple")
        assert h.startswith("scrypt$") and h.count("$") == 5
        assert verify_password("correct horse battery staple", h)
        assert not verify_password("Correct horse battery staple", h)
        assert not verify_password("anything", None)
        assert not verify_password("anything", "garbage")
        assert not needs_rehash(h)
        assert needs_rehash("scrypt$1024$8$1$c2FsdA$aGFzaA")  # weaker params → upgrade

    def test_policy(self):
        from ka11y.auth.passwords import password_policy_error

        assert password_policy_error("short") == "weak_password"
        assert password_policy_error(" padded-password") == "weak_password"
        assert password_policy_error("x" * 129) == "weak_password"
        assert password_policy_error("long enough") is None


class TestPasswordSignIn:
    """E-mail + password registration and login against PostgreSQL."""

    EMAIL = "meghana@bluecaffeine.com"

    def _fresh(self, client):
        client.cookies.clear()

    def test_config_advertises_both_methods(self, client):
        cfg = client.get("/api/v1/auth/config").json()
        assert cfg["password_login"] is True
        assert cfg["registration"] is True
        assert cfg["oidc"] is True

    def test_register_not_on_allow_list_is_rejected(self, client):
        self._fresh(client)
        r = client.post(
            "/api/v1/auth/password/register",
            json={"email": "stranger@example.com", "password": "long enough password"},
        )
        assert r.status_code == 403
        assert r.json()["error"] == "not_allowed"
        assert "ka11y_session" not in client.cookies

    def test_register_weak_password(self, client):
        self._fresh(client)
        r = client.post(
            "/api/v1/auth/password/register",
            json={"email": "watanabe.kanae2@kao.com", "password": "short"},
        )
        assert r.status_code == 400
        assert r.json()["error"] == "weak_password"

    def test_register_then_login_then_protected(self, client, monkeypatch):
        # A brand-new allow-listed address, so the test is independent of the
        # rows the OIDC tests above created (and of test ordering).
        email = f"pw-{uuid.uuid4().hex[:8]}@kao.com"
        monkeypatch.setenv("KA11Y_ALLOWED_EMAILS", f"{_ENV['KA11Y_ALLOWED_EMAILS']},{email}")
        self._fresh(client)

        r = client.post(
            "/api/v1/auth/password/register",
            json={"email": email.upper(), "password": "kanae's first password", "name": "Kanae", "next": "/dashboard/x"},
        )
        assert r.status_code == 201, r.text
        assert r.json()["next"] == "/dashboard/x"
        assert client.cookies.get("ka11y_session")
        me = client.get("/api/v1/auth/me").json()
        assert me["email"] == email and me["name"] == "Kanae"
        assert me["role"] in ("owner", "member") and me["organization_id"]

        # second registration for the same address is refused
        r = client.post(
            "/api/v1/auth/password/register",
            json={"email": email, "password": "another long password"},
        )
        assert r.status_code == 409 and r.json()["error"] == "account_exists"

        # sign out, then sign in with the password
        client.post("/api/v1/auth/logout")
        assert client.get("/api/v1/auth/me").status_code == 401
        r = client.post(
            "/api/v1/auth/password/login",
            json={"email": email, "password": "wrong password here"},
        )
        assert r.status_code == 401 and r.json()["error"] == "invalid_credentials"
        r = client.post(
            "/api/v1/auth/password/login",
            json={"email": email, "password": "kanae's first password", "remember": True},
        )
        assert r.status_code == 200, r.text
        assert r.json()["next"] == "/dashboard/new-audit"  # default landing page
        assert client.get("/api/v1/auth/me").json()["email"] == email

    def test_oidc_only_account_has_no_password(self, client, monkeypatch):
        # A fresh OIDC-created account (unique per run, so a password set by a
        # previous run against the same database cannot leak into this test).
        email = f"oidc-{uuid.uuid4().hex[:8]}@kao.com"
        monkeypatch.setenv("KA11Y_ALLOWED_EMAILS", f"{_ENV['KA11Y_ALLOWED_EMAILS']},{email}")
        self._fresh(client)
        r = _sign_in(client, monkeypatch, email)
        assert r.status_code == 302
        client.post("/api/v1/auth/logout")
        r = client.post(
            "/api/v1/auth/password/login",
            json={"email": email, "password": "whatever password"},
        )
        assert r.status_code == 403 and r.json()["error"] == "no_password"

    def test_set_password_admin_path(self, client):
        import asyncio

        from ka11y.auth.service import set_password

        asyncio.run(set_password(email=self.EMAIL, password="admin assigned pw"))
        self._fresh(client)
        r = client.post(
            "/api/v1/auth/password/login",
            json={"email": self.EMAIL, "password": "admin assigned pw"},
        )
        assert r.status_code == 200, r.text

    def test_brute_force_brake(self, client, monkeypatch):
        from ka11y.auth import router as auth_router

        # Allow-listed but never registered: every attempt is a clean 401.
        email = f"brute-{uuid.uuid4().hex[:8]}@kao.com"
        monkeypatch.setenv("KA11Y_ALLOWED_EMAILS", f"{_ENV['KA11Y_ALLOWED_EMAILS']},{email}")
        auth_router._failures.clear()
        self._fresh(client)
        for _ in range(auth_router._ATTEMPT_LIMIT):
            r = client.post(
                "/api/v1/auth/password/login",
                json={"email": email, "password": "nope nope nope"},
            )
            assert r.status_code == 401, r.text
        r = client.post(
            "/api/v1/auth/password/login",
            json={"email": email, "password": "nope nope nope"},
        )
        assert r.status_code == 429 and r.json()["error"] == "too_many_attempts"
        auth_router._failures.clear()


class TestBootstrapUsers:
    def test_allow_list_gets_accounts_and_shared_password(self, client, monkeypatch):
        import asyncio

        from ka11y.auth.service import bootstrap_allow_listed_users

        a = f"boot-a-{uuid.uuid4().hex[:6]}@kao.com"
        b = f"boot-b-{uuid.uuid4().hex[:6]}@bluecaffeine.com"
        monkeypatch.setenv("KA11Y_ALLOWED_EMAILS", f"{a},{b}")
        created, assigned = asyncio.run(bootstrap_allow_listed_users("shared pilot password"))
        assert (created, assigned) == (2, 2)
        # second run is a no-op
        assert asyncio.run(bootstrap_allow_listed_users("some other password")) == (0, 0)

        client.cookies.clear()
        r = client.post("/api/v1/auth/password/login", json={"email": b, "password": "shared pilot password"})
        assert r.status_code == 200, r.text
        assert client.get("/api/v1/auth/me").json()["email"] == b
        # the later run did not overwrite the password
        client.post("/api/v1/auth/logout")
        r = client.post("/api/v1/auth/password/login", json={"email": a, "password": "some other password"})
        assert r.status_code == 401

    def test_registration_off_hides_and_refuses(self, client, monkeypatch):
        from ka11y.auth import router as auth_router

        auth_router._failures.clear()  # earlier rejected registrations count per IP
        monkeypatch.setenv("KA11Y_PASSWORD_REGISTRATION", "0")
        assert client.get("/api/v1/auth/config").json()["registration"] is False
        r = client.post(
            "/api/v1/auth/password/register",
            json={"email": "watanabe.kanae2@kao.com", "password": "long enough password"},
        )
        assert r.status_code == 403 and r.json()["error"] == "register_disabled"


class TestAdminFlag:
    def test_me_reports_admin_from_env_list(self, client, monkeypatch):
        from fastapi import Depends

        from ka11y.auth.dependencies import CurrentUser, require_admin
        from ka11y.main import app

        if not any(getattr(r, "path", "") == "/__admin_probe" for r in app.routes):
            @app.get("/__admin_probe")
            async def _probe(user: CurrentUser = Depends(require_admin)):
                return {"email": user.email}

        email = f"adm-{uuid.uuid4().hex[:8]}@kao.com"
        monkeypatch.setenv("KA11Y_ALLOWED_EMAILS", f"{_ENV['KA11Y_ALLOWED_EMAILS']},{email}")
        client.cookies.clear()
        assert _sign_in(client, monkeypatch, email).status_code == 302

        monkeypatch.setenv("KA11Y_ADMIN_EMAILS", "")
        assert client.get("/api/v1/auth/me").json()["is_admin"] is False
        assert client.get("/__admin_probe").status_code == 403

        monkeypatch.setenv("KA11Y_ADMIN_EMAILS", f"Other@kao.com, {email.upper()}")
        assert client.get("/api/v1/auth/me").json()["is_admin"] is True
        assert client.get("/__admin_probe").status_code == 200

        client.cookies.clear()
        assert client.get("/__admin_probe").status_code == 401


class TestAdminApi:
    """Admin console API: 403 for non-admins, real aggregates for admins."""

    def _admin(self, client, monkeypatch, email):
        monkeypatch.setenv("KA11Y_ALLOWED_EMAILS", f"{_ENV['KA11Y_ALLOWED_EMAILS']},{email}")
        monkeypatch.setenv("KA11Y_ADMIN_EMAILS", email)
        client.cookies.clear()
        assert _sign_in(client, monkeypatch, email).status_code == 302

    def test_non_admin_gets_403_and_anonymous_401(self, client, monkeypatch):
        email = f"plain-{uuid.uuid4().hex[:8]}@kao.com"
        monkeypatch.setenv("KA11Y_ALLOWED_EMAILS", f"{_ENV['KA11Y_ALLOWED_EMAILS']},{email}")
        monkeypatch.setenv("KA11Y_ADMIN_EMAILS", "")
        client.cookies.clear()
        assert _sign_in(client, monkeypatch, email).status_code == 302
        assert client.get("/api/v1/admin/overview").status_code == 403
        client.cookies.clear()
        assert client.get("/api/v1/admin/overview").status_code == 401

    def test_overview_reflects_a_real_job(self, client, monkeypatch):
        import asyncio

        from ka11y.db import audit_repo

        email = f"admin-{uuid.uuid4().hex[:8]}@kao.com"
        self._admin(client, monkeypatch, email)
        me = client.get("/api/v1/auth/me").json()
        assert me["is_admin"] is True
        job_id = str(uuid.uuid4())

        async def _make():
            await audit_repo.create_job(
                job_id, user_id=uuid.UUID(me["user_id"]), organization_id=uuid.UUID(me["organization_id"]),
                session_id=None, target_url="https://www.kao.com/global/en/", crawl_depth=1, requested_pages=5,
            )
            await audit_repo.mark_running(job_id)
            await audit_repo.mark_completed(
                job_id,
                summary={"page_count": 3, "violations": 7, "passes": 40, "needs_review": 2,
                         "by_severity": {"critical": 2, "serious": 3, "moderate": 1, "minor": 1}, "score": 81},
            )

        asyncio.run(_make())

        ov = client.get("/api/v1/admin/overview")
        assert ov.status_code == 200, ov.text
        data = ov.json()
        assert data["stats"]["totalAudits"] >= 1 and data["stats"]["totalUsers"] >= 1
        assert data["currentUser"]["email"] == email and data["currentUser"]["role"] == "Admin"
        assert {s["status"] for s in data["auditStatus"]} == {"completed", "running", "failed", "cancelled"}
        per_day = data["pagesPerDay"]
        assert len(per_day) == 30 and per_day[-1]["pages"] >= 3  # today's job, 3 pages
        assert all(set(pt) == {"date", "pages"} for pt in per_day)
        assert per_day == sorted(per_day, key=lambda pt: pt["date"])
        job = next(j for j in data["recentAudits"] if j["id"] == job_id)
        assert job["status"] == "completed" and job["pages"] == 3 and job["fails"] == 7
        assert job["severity"] == {"critical": 2, "serious": 3, "moderate": 1, "minor": 1}
        assert job["user"] == email and job["targetHost"] == "www.kao.com"
        assert any(e["code"] == "JOB_COMPLETED" for e in job["events"])
        kinds = {a["kind"] for a in data["activity"]}
        assert "auditCompleted" in kinds and "userLogin" in kinds

        detail = client.get(f"/api/v1/admin/audits/{job_id}")
        assert detail.status_code == 200
        d = detail.json()
        assert d["id"] == job_id and isinstance(d["pageList"], list) and isinstance(d["failList"], list)
        assert client.get(f"/api/v1/admin/audits/{uuid.uuid4()}").status_code == 404

        # Export: format is validated, unknown jobs 404, and a job with no
        # stored report JSON has nothing to build from (404, not a crash).
        assert client.get(f"/api/v1/admin/audits/{job_id}/export", params={"format": "docx"}).status_code == 422
        assert client.get(f"/api/v1/admin/audits/{uuid.uuid4()}/export", params={"format": "csv"}).status_code == 404
        assert client.get(f"/api/v1/admin/audits/{job_id}/export", params={"format": "csv"}).status_code == 404
        assert any(n["href"] != "/admin/system-events" for n in data["notifications"]) or not data["notifications"]

        listing = client.get("/api/v1/admin/audits", params={"q": "kao.com", "limit": 5}).json()
        assert any(j["id"] == job_id for j in listing["jobs"])

        users = client.get("/api/v1/admin/users").json()
        row = next(u for u in users["users"] if u["email"] == email)
        assert row["isAdmin"] is True and row["audits"] >= 1 and "google" in row["signInMethods"]

        assert client.get("/api/v1/admin/fails").status_code == 200
        assert client.get("/api/v1/admin/reports").status_code == 200
        ev = client.get("/api/v1/admin/system-events").json()["events"]
        assert any(e["jobId"] == job_id and e["code"] == "JOB_COMPLETED" for e in ev)
        st = client.get("/api/v1/admin/settings").json()
        auth_items = next(s for s in st["sections"] if s["key"] == "auth")["items"]
        assert any(email in i["value"] for i in auth_items if i["label"] == "Admin e-mails")
