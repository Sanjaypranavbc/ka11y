"""
ka11y/auth/oidc.py
==================
OpenID Connect authorization-code flow with PKCE, against any issuer that
publishes ``/.well-known/openid-configuration`` (Google by default).

Only ``httpx`` is needed. The ID token is obtained directly from the token
endpoint over TLS, so per OIDC Core §3.1.3.7 its signature does not have to be
re-verified; ``iss``, ``aud``, ``exp`` and ``nonce`` are checked here. Tokens
are used once, in this module, and never stored.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx

from ka11y.auth.config import AuthSettings, settings
from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="auth.oidc")

_discovery_cache: Dict[str, Dict[str, Any]] = {}


class OIDCError(Exception):
    """A failure the callback maps to ?error=<code> on the login page."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code


@dataclass(frozen=True)
class ExternalIdentity:
    provider: str
    subject: str
    email: str
    email_verified: bool
    name: Optional[str]
    picture: Optional[str]
    locale: Optional[str]


# ── discovery ────────────────────────────────────────────────────────────────


async def endpoints(cfg: Optional[AuthSettings] = None) -> Dict[str, str]:
    cfg = cfg or settings()
    if cfg.authorization_endpoint and cfg.token_endpoint:
        return {
            "authorization_endpoint": cfg.authorization_endpoint,
            "token_endpoint": cfg.token_endpoint,
            "userinfo_endpoint": cfg.userinfo_endpoint or "",
            "issuer": cfg.issuer,
        }
    cached = _discovery_cache.get(cfg.issuer)
    if cached:
        return cached
    url = f"{cfg.issuer}/.well-known/openid-configuration"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        doc = resp.json()
    out = {
        "authorization_endpoint": doc["authorization_endpoint"],
        "token_endpoint": doc["token_endpoint"],
        "userinfo_endpoint": doc.get("userinfo_endpoint", ""),
        "issuer": doc.get("issuer", cfg.issuer),
    }
    _discovery_cache[cfg.issuer] = out
    return out


# ── authorization request ────────────────────────────────────────────────────


def new_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


async def authorization_url(*, state: str, nonce: str, code_challenge: str) -> str:
    cfg = settings()
    ep = await endpoints(cfg)
    params = {
        "response_type": "code",
        "client_id": cfg.client_id,
        "redirect_uri": cfg.redirect_uri,
        "scope": cfg.scopes,
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    return f"{ep['authorization_endpoint']}?{urlencode(params)}"


# ── code exchange ────────────────────────────────────────────────────────────


def _decode_jwt_payload(token: str) -> Dict[str, Any]:
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        return json.loads(base64.urlsafe_b64decode(part.encode("ascii")))
    except Exception as exc:  # noqa: BLE001
        raise OIDCError("invalid_id_token", f"cannot decode id_token: {exc}") from exc


def _issuer_matches(claimed: str, expected: str) -> bool:
    norm = lambda s: s.rstrip("/").removeprefix("https://").removeprefix("http://")  # noqa: E731
    return norm(claimed or "") == norm(expected)


async def exchange_code(*, code: str, code_verifier: str, nonce: str) -> ExternalIdentity:
    cfg = settings()
    ep = await endpoints(cfg)
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": cfg.redirect_uri,
        "client_id": cfg.client_id,
        "client_secret": cfg.client_secret,
        "code_verifier": code_verifier,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(ep["token_endpoint"], data=data)
        except httpx.HTTPError as exc:
            raise OIDCError("exchange_failed", str(exc)) from exc
        if resp.status_code != 200:
            logger.warning("[auth] token endpoint returned %s: %s", resp.status_code, resp.text[:300])
            raise OIDCError("exchange_failed", f"token endpoint {resp.status_code}")
        tokens = resp.json()

        id_token = tokens.get("id_token")
        if not id_token:
            raise OIDCError("invalid_id_token", "no id_token in token response")
        claims = _decode_jwt_payload(id_token)

        if not _issuer_matches(str(claims.get("iss", "")), ep["issuer"]):
            raise OIDCError("invalid_id_token", f"issuer mismatch: {claims.get('iss')}")
        aud = claims.get("aud")
        if not (aud == cfg.client_id or (isinstance(aud, list) and cfg.client_id in aud)):
            raise OIDCError("invalid_id_token", "audience mismatch")
        if int(claims.get("exp", 0)) < int(time.time()) - 60:
            raise OIDCError("invalid_id_token", "id_token expired")
        if claims.get("nonce") != nonce:
            raise OIDCError("state_mismatch", "nonce mismatch")

        # Fill in profile fields from userinfo when the id_token is minimal.
        if (not claims.get("email") or not claims.get("name")) and ep.get("userinfo_endpoint"):
            access = tokens.get("access_token")
            if access:
                try:
                    ui = await client.get(
                        ep["userinfo_endpoint"], headers={"Authorization": f"Bearer {access}"}
                    )
                    if ui.status_code == 200:
                        for k, v in ui.json().items():
                            claims.setdefault(k, v)
                except httpx.HTTPError:
                    logger.debug("[auth] userinfo fetch failed", exc_info=True)

    email = str(claims.get("email") or "").strip().lower()
    if not email:
        raise OIDCError("no_email", "provider returned no email")
    verified = claims.get("email_verified")
    if isinstance(verified, str):
        verified = verified.lower() == "true"
    return ExternalIdentity(
        provider=cfg.provider_name,
        subject=str(claims["sub"]),
        email=email,
        email_verified=bool(verified) if verified is not None else False,
        name=claims.get("name"),
        picture=claims.get("picture"),
        locale=claims.get("locale"),
    )
