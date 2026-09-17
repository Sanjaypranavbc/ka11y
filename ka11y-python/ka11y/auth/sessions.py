"""
ka11y/auth/sessions.py
======================
Browser sessions backed by ``user_sessions``.

The cookie value is ``<session uuid>.<r|n>.<hmac>`` — the session id plus a
"remember me" flag, signed with KA11Y_SESSION_SECRET. Nothing secret is stored
in the row, so the DB holds no token that could be replayed if it leaked; a
forged cookie fails the HMAC, a stolen one dies with ``ended_at`` on logout.

Lifetime rules (all enforced server-side, the cookie max-age is a hint):
  * absolute: ``started_at + KA11Y_SESSION_MAX_DAYS``
  * idle:     ``last_activity_at + idle`` where idle is
              KA11Y_SESSION_IDLE_HOURS, or KA11Y_SESSION_REMEMBER_DAYS with the
              remember flag
``last_activity_at`` is bumped at most every 5 minutes to keep writes low.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy import select

from ka11y.auth.config import settings
from ka11y.auth.signing import sign, unsign
from ka11y.db.engine import session_scope
from ka11y.db.models import User, UserSession

_ACTIVITY_BUMP = timedelta(minutes=5)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def cookie_value(session_id: uuid.UUID, remember: bool) -> str:
    return sign(f"{session_id.hex}.{'r' if remember else 'n'}")


def cookie_max_age(remember: bool) -> int:
    cfg = settings()
    days = min(cfg.session_remember_days, cfg.session_max_days)
    return days * 86400 if remember else cfg.session_idle_hours * 3600


def parse_cookie(value: Optional[str]) -> Optional[Tuple[uuid.UUID, bool]]:
    payload = unsign(value)
    if not payload or "." not in payload:
        return None
    sid_hex, _, flag = payload.partition(".")
    try:
        return uuid.UUID(hex=sid_hex), flag == "r"
    except ValueError:
        return None


async def create_session(
    *, user_id: uuid.UUID, ip_address: Optional[str], user_agent: Optional[str]
) -> UserSession:
    now = _now()
    row = UserSession(
        user_id=user_id,
        started_at=now,
        last_activity_at=now,
        ip_address=ip_address or None,
        user_agent=(user_agent or "")[:1000] or None,
    )
    async with session_scope() as s:
        s.add(row)
        await s.flush()
    return row


async def resolve(cookie: Optional[str]) -> Optional[Tuple[UserSession, User]]:
    """Cookie → (session, user) if the session is live, else None."""
    parsed = parse_cookie(cookie)
    if parsed is None:
        return None
    sid, remember = parsed
    cfg = settings()
    now = _now()
    idle = timedelta(days=cfg.session_remember_days) if remember else timedelta(hours=cfg.session_idle_hours)
    absolute = timedelta(days=cfg.session_max_days)

    async with session_scope() as s:
        row = await s.get(UserSession, sid)
        if row is None or row.ended_at is not None:
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
