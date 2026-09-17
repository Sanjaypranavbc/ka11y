"""
ka11y/db/base.py
================
Declarative base + the two mixins every production table shares.

* ``UUIDPrimaryKeyMixin`` — ``id UUID PK`` generated in the application
  (``uuid4``) so a row has its id before the INSERT round-trips, and so ids
  are never sequential / guessable for externally visible resources.
* ``TimestampMixin`` — ``created_at`` / ``updated_at`` as TIMESTAMPTZ, always
  UTC. Both are stamped by the application *and* have a ``server_default`` so
  rows written by hand (psql, a migration backfill) get the same treatment.

Nothing here is PostgreSQL-specific; the dialect-specific column types
(INET, JSONB) live in the model modules that need them.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
    )
