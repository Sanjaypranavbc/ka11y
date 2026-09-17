"""
ka11y/auth/router.py
====================
Browser-facing auth endpoints (mounted at /api/v1/auth; the Next.js app
rewrites /api/v1/auth/* straight to this service so cookies land on the UI
origin).

  GET  /auth/login?remember=1&next=/dashboard  → 302 to the OIDC provider
  GET  /auth/callback?code=&state=             → 302 to `next` with the
                                                 session cookie set, or to
                                                 /login?error=<code>
  POST /auth/logout                            → 204, session ended
  GET  /auth/logout                            → same, then 302 to /login
  GET  /auth/me                                → the signed-in user
  GET  /auth/config                            → {configured, provider} (public)

State, nonce and the PKCE verifier live in a short-lived signed cookie between
the two redirects, so this works with several API replicas and no Redis.
"""

from __future__ import annotations

import secrets
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from ka11y.auth import oidc, sessions
from ka11y.auth.config import settings
from ka11y.auth.dependencies import CurrentUser, require_user
from ka11y.auth.oidc import OIDCError
from ka11y.auth.service import login_identity
from ka11y.auth.signing import sign_json, unsign_json
from ka11y.config.logger import setup_logger
from ka11y.db.engine import is_configured as db_configured

logger = setup_logger(name="KAC", tag="auth")

router = APIRouter(prefix="/auth", tags=["auth"])

_OIDC_COOKIE_TTL = 600  # seconds between /login and /callback


def _safe_next(value: Optional[str]) -> str:
    """Only same-origin relative paths; anything else falls back to the default."""
    cfg = settings()
    if not value or not value.startswith("/") or value.startswith("//") or "\\" in value:
        return cfg.post_login_url
    return value


def _login_error(code: str) -> RedirectResponse:
    cfg = settings()
    resp = RedirectResponse(f"{cfg.login_page_url}?{urlencode({'error': code})}", status_code=302)
    resp.delete_cookie(cfg.oidc_cookie, path="/")
    return resp


def _client_ip(request: Request) -> Optional[str]:
    """First X-Forwarded-For hop, else the socket peer — only if it parses as
    an IP (the column is INET; a proxy can forward anything)."""
    import ipaddress

    xff = request.headers.get("x-forwarded-for", "")
    candidate = xff.split(",")[0].strip() if xff else (request.client.host if request.client else "")
    try:
        return str(ipaddress.ip_address(candidate)) if candidate else None
    except ValueError:
        return None


def _require_configured() -> None:
    cfg = settings()
    if not (cfg.configured and db_configured()):
        raise HTTPException(status_code=503, detail="Authentication is not configured on this server.")


@router.get("/config")
async def auth_config() -> Dict[str, Any]:
    cfg = settings()
    return {
        "configured": bool(cfg.configured and db_configured()),
        "disabled": cfg.disabled,
        "provider": cfg.provider_name,
        "login_url": "/api/v1/auth/login",
    }


@router.get("/login")
async def login(
    request: Request,
    remember: int = Query(0, ge=0, le=1),
    next: Optional[str] = Query(None, max_length=512),
) -> Response:
    _require_configured()
    cfg = settings()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier, challenge = oidc.new_pkce()
    try:
        url = await oidc.authorization_url(state=state, nonce=nonce, code_challenge=challenge)
    except Exception:  # noqa: BLE001
        logger.exception("[auth] OIDC discovery failed")
        return _login_error("provider_unavailable")
    resp = RedirectResponse(url, status_code=302)
    resp.set_cookie(
        cfg.oidc_cookie,
        sign_json(
            {
                "s": state,
                "n": nonce,
                "v": verifier,
                "r": int(bool(remember)),
                "x": _safe_next(next),
                "t": int(time.time()),
            }
        ),
        max_age=_OIDC_COOKIE_TTL,
        httponly=True,
        secure=cfg.cookie_secure,
        samesite="lax",
        path="/",
    )
    return resp


@router.get("/callback")
async def callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
) -> Response:
    _require_configured()
    cfg = settings()
    if error:
        logger.info("[auth] provider returned error=%s", error)
        return _login_error("provider_error")
    pending = unsign_json(request.cookies.get(cfg.oidc_cookie))
    if not pending or not state or pending.get("s") != state:
        return _login_error("state_mismatch")
    if int(time.time()) - int(pending.get("t", 0)) > _OIDC_COOKIE_TTL:
        return _login_error("state_expired")
    if not code:
        return _login_error("provider_error")

    try:
        ext = await oidc.exchange_code(code=code, code_verifier=pending["v"], nonce=pending["n"])
        user = await login_identity(ext)
    except OIDCError as exc:
        logger.info("[auth] sign-in rejected: %s (%s)", exc.code, exc)
        return _login_error(exc.code)
    except Exception:  # noqa: BLE001
        logger.exception("[auth] sign-in failed")
        return _login_error("internal_error")

    remember = bool(pending.get("r"))
    sess = await sessions.create_session(
        user_id=user.id,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    logger.info("[auth] %s signed in (session %s)", user.email, sess.id)

    resp = RedirectResponse(_safe_next(pending.get("x")), status_code=302)
    resp.delete_cookie(cfg.oidc_cookie, path="/")
    resp.set_cookie(
        cfg.session_cookie,
        sessions.cookie_value(sess.id, remember),
        max_age=sessions.cookie_max_age(remember),
        httponly=True,
        secure=cfg.cookie_secure,
        samesite="lax",
        path="/",
    )
    return resp


async def _do_logout(request: Request) -> None:
    parsed = sessions.parse_cookie(request.cookies.get(settings().session_cookie))
    if parsed and db_configured():
        try:
            await sessions.end_session(parsed[0])
        except Exception:  # noqa: BLE001
            logger.warning("[auth] end_session failed", exc_info=True)


@router.post("/logout", status_code=204)
async def logout(request: Request) -> Response:
    await _do_logout(request)
    resp = Response(status_code=204)
    resp.delete_cookie(settings().session_cookie, path="/")
    return resp


@router.get("/logout")
async def logout_redirect(request: Request) -> Response:
    await _do_logout(request)
    resp = RedirectResponse(settings().login_page_url, status_code=302)
    resp.delete_cookie(settings().session_cookie, path="/")
    return resp


@router.get("/me")
async def me(user: CurrentUser = Depends(require_user)) -> JSONResponse:
    return JSONResponse(
        {
            "user_id": str(user.user_id) if user.user_id else None,
            "email": user.email,
            "name": user.name,
            "organization_id": str(user.organization_id) if user.organization_id else None,
            "role": user.role,
            "anonymous": user.is_anonymous,
        }
    )
