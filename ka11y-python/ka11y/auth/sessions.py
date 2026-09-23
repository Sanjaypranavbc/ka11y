"""
ka11y/auth/sessions.py
======================
Browser sessions backed by ``user_sessions``.

The cookie value is AES-256-GCM sealed (``ka11y.auth.signing``) around
``<session uuid>.<token>.<r|n>``: the row id, a random 256-bit bearer token
and the "remember me" flag. The row stores only ``sha256(token)``, so

  * a copy of the table cannot be replayed as a cookie, even by someone who
    also holds KA11Y_SESSION_SECRET (they lack the token pre-image);
  * a forged or tampered cookie fails the AEAD tag before any DB work;
  * a stolen cookie dies with ``ended_at`` on logout / password change.

Per-user cap: KA11Y_SESSION_MAX_PER_USER (default 5) live sessions; opening
one more ends the least recently active, so a leaked account cannot fan out
into an unbounded number of long-lived browsers.

Lifetime rules (all enforced server-side, the cookie max-age is a hint):
  * absolute: ``started_at + KA11Y_SESSION_MAX_DAYS``
  * idle:     ``last_activity_at + idle`` where idle is
              KA11Y_SESSION_IDLE_HOURS, or KA11Y_SESSION_REMEMBER_DAYS with the
              remember flag
``last_activity_at`` is bumped at most every 5 minutes to keep writes low.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy import select

from ka11y.auth.config import settings
from ka11y.auth.signing import sign, unsign
from ka11y.db.engine import session_scope
from ka11y.db.models import User, UserSession

_ACTIVITY_BUMP = timedelta(minutes=5)
_TOKEN_BYTES = 32


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _max_per_user() -> int:
    try:
        return max(1, int(os.getenv("KA11Y_SESSION_MAX_PER_USER", "5")))
    except ValueError:
        return 5


def new_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def cookie_value(session_id: uuid.UUID, token: str, remember: bool) -> str:
    return sign(f"{session_id.hex}.{token}.{'r' if remember else 'n'}")


def cookie_max_age(remember: bool) -> int:
    cfg = settings()
    days = min(cfg.session_remember_days, cfg.session_max_days)
    return days * 86400 if remember else cfg.session_idle_hours * 3600


def parse_cookie(value: Optional[str]) -> Optional[Tuple[uuid.UUID, str, bool]]:
    """Cookie → (session id, bearer token, remember) or None if unreadable."""
    payload = unsign(value)
    if not payload:
        return None
    parts = payload.split(".")
    if len(parts) != 3 or not parts[1]:
        return None
    sid_hex, token, flag = parts
    try:
        return uuid.UUID(hex=sid_hex), token, flag == "r"
    except ValueError:
        return None


async def create_session(
    *, user_id: uuid.UUID, ip_address: Optional[str], user_agent: Optional[str]
) -> Tuple[UserSession, str]:
    """Open a session; returns the row and the one-time plaintext token that
    goes into the cookie (never stored, never logged)."""
    now = _now()
    token = new_token()
    row = UserSession(
        user_id=user_id,
        token_hash=token_hash(token),
        started_at=now,
        last_activity_at=now,
        ip_address=ip_address or None,
        user_agent=(user_agent or "")[:1000] or None,
    )
    async with session_scope() as s:
        # Cap live sessions per user: end the least recently active extras.
        live = (
            await s.execute(
                select(UserSession)
                .where(UserSession.user_id == user_id, UserSession.ended_at.is_(None))
                .order_by(UserSession.last_activity_at.desc().nullslast(), UserSession.started_at.desc())
            )
        ).scalars().all()
        for stale in live[_max_per_user() - 1:]:
            stale.ended_at = now
        s.add(row)
        await s.flush()
    return row, token


async def resolve(cookie: Optional[str]) -> Optional[Tuple[UserSession, User]]:
    """Cookie → (session, user) if the session is live, else None."""
    parsed = parse_cookie(cookie)
    if parsed is None:
        return None
    sid, token, remember = parsed
    cfg = settings()
    now = _now()
    idle = timedelta(days=cfg.session_remember_days) if remember else timedelta(hours=cfg.session_idle_hours)
    absolute = timedelta(days=cfg.session_max_days)

    async with session_scope() as s:
        row = await s.get(UserSession, sid)
        if row is None or row.ended_at is not None:
            return None
        if not row.token_hash or not hmac.compare_digest(row.token_hash, token_hash(token)):
            return None
        if row.started_at + absolute < now:
            return None
        last = row.last_activity_at or row.started_at
        if last + idle < now:
            return None
        user = await s.get(User, row.user_id)
        if user is None or user.deleted_at is not None or user.status != "active":
            return None
        if now - last > _ACTIVITY_BUMP:
            row.last_activity_at = now
        return row, user


async def end_session(session_id: uuid.UUID) -> None:
    async with session_scope() as s:
        row = await s.get(UserSession, session_id)
        if row is not None and row.ended_at is None:
            row.ended_at = _now()


async def end_all_for_user(user_id: uuid.UUID) -> int:
    n = 0
    async with session_scope() as s:
        rows = (
            await s.execute(
                select(UserSession).where(UserSession.user_id == user_id, UserSession.ended_at.is_(None))
            )
        ).scalars()
        for row in rows:
            row.ended_at = _now()
            n += 1
    return n
