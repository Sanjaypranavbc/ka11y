"""Cookie sealing (AES-256-GCM) and the session-token layout on top of it."""

from __future__ import annotations

import base64
import os
import uuid

import pytest

SECRET = "unit-test-secret-do-not-use-anywhere-else-0123456789"


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("KA11Y_SESSION_SECRET", SECRET)
    monkeypatch.setenv("KA11Y_OIDC_REDIRECT_URI", "https://a11y.example/api/v1/auth/callback")
    # A developer .env (loaded by ka11y.main in other test modules) commonly
    # carries KA11Y_COOKIE_SECURE=0; pin the https posture explicitly.
    monkeypatch.setenv("KA11Y_COOKIE_SECURE", "1")
    monkeypatch.delenv("KA11Y_COOKIE_HOST_PREFIX", raising=False)
    monkeypatch.delenv("KA11Y_FORCE_HTTPS", raising=False)
    yield


def test_round_trip_is_opaque_and_versioned():
    from ka11y.auth.signing import sign, unsign

    token = sign("hello.world")
    assert token.startswith("v2.")
    assert "hello" not in token
    assert unsign(token) == "hello.world"


def test_every_seal_differs_but_opens_to_the_same_payload():
    from ka11y.auth.signing import sign, unsign

    a, b = sign("same"), sign("same")
    assert a != b
    assert unsign(a) == unsign(b) == "same"


def test_tamper_forge_and_legacy_are_refused():
    from ka11y.auth.signing import sign, unsign

    token = sign("payload")
    version, body = token.split(".", 1)
    raw = bytearray(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    raw[-1] ^= 0x01  # flip a bit in the GCM tag
    tampered = version + "." + base64.urlsafe_b64encode(bytes(raw)).decode().rstrip("=")
    assert unsign(tampered) is None
    assert unsign("payload.deadbeef") is None  # old HMAC layout
    assert unsign("v2.") is None
    assert unsign("v2.not-base64!!") is None
    assert unsign("") is None
    assert unsign(None) is None


def test_other_secret_cannot_open(monkeypatch):
    from ka11y.auth.signing import sign, unsign

    token = sign("payload")
    monkeypatch.setenv("KA11Y_SESSION_SECRET", "a-different-secret-that-is-also-long-enough-xyz")
    assert unsign(token) is None


def test_short_secret_is_refused(monkeypatch):
    from ka11y.auth.signing import sign

    monkeypatch.setenv("KA11Y_SESSION_SECRET", "short")
    with pytest.raises(RuntimeError):
        sign("x")


def test_json_helpers():
    from ka11y.auth.signing import sign_json, unsign_json

    assert unsign_json(sign_json({"s": "st", "n": 1})) == {"s": "st", "n": 1}
    assert unsign_json("garbage") is None


def test_session_cookie_layout_and_token_hash():
    from ka11y.auth import sessions

    sid = uuid.uuid4()
    token = sessions.new_token()
    cookie = sessions.cookie_value(sid, token, True)
    assert sessions.parse_cookie(cookie) == (sid, token, True)
    assert sessions.parse_cookie(cookie[:-3]) is None
    assert token not in cookie
    assert sessions.token_hash(token) != token
    assert len(sessions.token_hash(token)) == 64


def test_host_prefix_follows_secure(monkeypatch):
    from ka11y.auth.config import settings

    assert settings().session_cookie == "__Host-ka11y_session"
    assert settings().cookie_secure and settings().force_https
    monkeypatch.setenv("KA11Y_COOKIE_SECURE", "0")
    cfg = settings()
    assert cfg.session_cookie == "ka11y_session" and not cfg.force_https
