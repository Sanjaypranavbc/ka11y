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
  GET  /auth/config                            → {configured, provider, oidc,
                                                 password_login, registration}
  POST /auth/password/login    {email, password, remember?, next?}
                                               → 200 {next} + session cookie,
                                                 or 4xx {error: <code>}
  POST /auth/password/register {email, password, name?, remember?, next?}
                                               → 201 {next} + session cookie
                                                 (allow-listed e-mails only)

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
from pydantic import BaseModel, Field

from ka11y.auth import oidc, sessions
from ka11y.auth.config import settings
from ka11y.auth.dependencies import CurrentUser, require_user
from ka11y.auth.oidc import OIDCError
from ka11y.auth.service import AuthError, login_identity, login_local, register_local
from ka11y.auth.signing import sign_json, unsign_json
from ka11y.config.logger import setup_logger
from ka11y.db.engine import is_configured as db_configured

logger = setup_logger(name="KAC", tag="auth")

router = APIRouter(prefix="/auth", tags=["auth"])

_OIDC_COOKIE_TTL = 600  # seconds between /login and /callback

# Password brute-force brake: failures per (client IP, e-mail) inside a
# sliding window. In-process only, which is enough for a pilot behind one API
# replica; a shared store is needed once several replicas run.
_ATTEMPT_WINDOW = 15 * 60
_ATTEMPT_LIMIT = 10
_failures: Dict[str, list] = {}


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
    """OIDC routes: the provider, the session secret and the DB must all be set."""
    cfg = settings()
    if not (cfg.oidc_configured and cfg.session_secret and db_configured()):
        raise HTTPException(status_code=503, detail="OIDC sign-in is not configured on this server.")


def _require_password_login() -> None:
    cfg = settings()
    if not (cfg.password_login and cfg.session_secret and db_configured()):
        raise HTTPException(status_code=503, detail="Password sign-in is not configured on this server.")


def _set_session_cookie(resp: Response, session_id, remember: bool) -> None:
    cfg = settings()
    resp.set_cookie(
        cfg.session_cookie,
        sessions.cookie_value(session_id, remember),
        max_age=sessions.cookie_max_age(remember),
        httponly=True,
        secure=cfg.cookie_secure,
        samesite="lax",
        path="/",
    )


def _attempt_key(request: Request, email: str) -> str:
    return f"{_client_ip(request) or '?'}|{(email or '').strip().lower()}"


def _too_many_failures(key: str) -> bool:
    cutoff = time.time() - _ATTEMPT_WINDOW
    stamps = [t for t in _failures.get(key, []) if t > cutoff]
    if stamps:
        _failures[key] = stamps
    else:
        _failures.pop(key, None)
    return len(stamps) >= _ATTEMPT_LIMIT


def _record_failure(key: str) -> None:
    _failures.setdefault(key, []).append(time.time())


_ERROR_STATUS = {
    "invalid_credentials": 401,
    "no_password": 403,
    "not_allowed": 403,
    "account_suspended": 403,
    "login_disabled": 403,
    "register_disabled": 403,
    "weak_password": 400,
    "account_exists": 409,
    "too_many_attempts": 429,
    "internal_error": 500,
}


def _auth_error(code: str) -> JSONResponse:
    return JSONResponse({"error": code}, status_code=_ERROR_STATUS.get(code, 400))


class PasswordLoginBody(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=256)
    remember: bool = False
    next: Optional[str] = Field(None, max_length=512)


class PasswordRegisterBody(PasswordLoginBody):
    name: Optional[str] = Field(None, max_length=255)


@router.get("/config")
async def auth_config() -> Dict[str, Any]:
    cfg = settings()
    ready = bool(cfg.session_secret and db_configured())
    return {
        "configured": bool(cfg.configured and db_configured()),
        "disabled": cfg.disabled,
        "provider": cfg.provider_name,
        "login_url": "/api/v1/auth/login",
        "oidc": bool(ready and cfg.oidc_configured),
        "password_login": bool(ready and cfg.password_login),
        "registration": bool(ready and cfg.password_login and cfg.password_registration),
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
    _set_session_cookie(resp, sess.id, remember)
    return resp


@router.post("/password/login")
async def password_login(request: Request, body: PasswordLoginBody) -> Response:
    _require_password_login()
    key = _attempt_key(request, body.email)
    if _too_many_failures(key):
        return _auth_error("too_many_attempts")
    try:
        user = await login_local(email=body.email, password=body.password)
    except AuthError as exc:
        if exc.code in ("invalid_credentials", "no_password"):
            _record_failure(key)
        logger.info("[auth] password sign-in rejected: %s (%s)", exc.code, exc)
        return _auth_error(exc.code)
    except Exception:  # noqa: BLE001
        logger.exception("[auth] password sign-in failed")
        return _auth_error("internal_error")
    _failures.pop(key, None)
    sess = await sessions.create_session(
        user_id=user.id, ip_address=_client_ip(request), user_agent=request.headers.get("user-agent")
    )
    logger.info("[auth] %s signed in with password (session %s)", user.email, sess.id)
    resp = JSONResponse({"next": _safe_next(body.next)})
    _set_session_cookie(resp, sess.id, body.remember)
    return resp


@router.post("/password/register", status_code=201)
async def password_register(request: Request, body: PasswordRegisterBody) -> Response:
    _require_password_login()
    key = _attempt_key(request, "")  # per-IP: slows down allow-list probing
    if _too_many_failures(key):
        return _auth_error("too_many_attempts")
    try:
        user = await register_local(email=body.email, password=body.password, name=body.name)
    except AuthError as exc:
        _record_failure(key)
        logger.info("[auth] registration rejected: %s (%s)", exc.code, exc)
        return _auth_error(exc.code)
    except Exception:  # noqa: BLE001
        logger.exception("[auth] registration failed")
        return _auth_error("internal_error")
    sess = await sessions.create_session(
        user_id=user.id, ip_address=_client_ip(request), user_agent=request.headers.get("user-agent")
    )
    logger.info("[auth] %s registered and signed in (session %s)", user.email, sess.id)
    resp = JSONResponse({"next": _safe_next(body.next)}, status_code=201)
    _set_session_cookie(resp, sess.id, body.remember)
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
            "is_admin": user.is_admin,
        }
    )
