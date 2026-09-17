"""
ka11y/auth/dependencies.py
==========================
FastAPI dependencies that resolve the caller.

    @router.get("/thing")
    async def thing(user: CurrentUser = Depends(require_user)): ...

``require_user`` accepts the session cookie (what the browser sends through
the Next.js proxy) or ``Authorization: Bearer <cookie value>`` (curl, tests).

Outcomes:
  * KA11Y_AUTH_DISABLED=1 → an anonymous CurrentUser (tests / local dev only)
  * PG or OIDC not configured → 503 so a misconfigured deploy fails closed
  * no/invalid/expired session → 401
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, Request

from ka11y.auth.config import settings
from ka11y.db.engine import is_configured as db_configured


@dataclass(frozen=True)
class CurrentUser:
    user_id: Optional[uuid.UUID]
    email: Optional[str]
    name: Optional[str]
    session_id: Optional[uuid.UUID]
    organization_id: Optional[uuid.UUID] = None
    role: Optional[str] = None

    @property
    def is_anonymous(self) -> bool:
        return self.user_id is None


ANONYMOUS = CurrentUser(user_id=None, email=None, name=None, session_id=None)


def _token_from(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(settings().session_cookie)


async def optional_user(request: Request) -> CurrentUser:
    cfg = settings()
    if cfg.disabled:
        return ANONYMOUS
    if not (cfg.configured and db_configured()):
        return ANONYMOUS
    token = _token_from(request)
    if not token:
        return ANONYMOUS
    from ka11y.auth.sessions import resolve
    from ka11y.auth.service import primary_membership

    found = await resolve(token)
    if found is None:
        return ANONYMOUS
    sess, user = found
    member = await primary_membership(user.id)
    return CurrentUser(
        user_id=user.id,
        email=user.email,
        name=user.name,
        session_id=sess.id,
        organization_id=member.organization_id if member else None,
        role=member.role if member else None,
    )


async def require_user(request: Request) -> CurrentUser:
    cfg = settings()
    if cfg.disabled:
        return ANONYMOUS
    if not (cfg.configured and db_configured()):
        raise HTTPException(status_code=503, detail="Authentication is not configured on this server.")
    user = await optional_user(request)
    if user.is_anonymous:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
