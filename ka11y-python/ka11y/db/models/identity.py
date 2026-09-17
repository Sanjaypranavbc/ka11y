"""
ka11y/db/models/identity.py
===========================
Who is using the product: organizations, users, their OAuth/OIDC identities,
organization membership, and browser sessions.

Authentication is OAuth 2.0 / OpenID Connect, or e-mail + password for
users on the allow-list (``users.password_hash``, scrypt, NULL for
OIDC-only accounts — see ``ka11y/auth/passwords.py``). An external identity
is identified by ``(provider, provider_user_id)``, never by email, so a user
can later link a second provider (Google + Microsoft) to the same account.

Users and organizations are soft-deleted (``deleted_at``); nothing cascades
from them, so audit history survives account removal.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ka11y.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from ka11y.db.models.audit import AuditJob


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    members: Mapped[List["OrganizationMember"]] = relationship(back_populates="organization")


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    profile_image_url: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    locale: Mapped[Optional[str]] = mapped_column(String(20))
    timezone: Mapped[Optional[str]] = mapped_column(String(100))
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # scrypt hash for e-mail + password sign-in; NULL when the account only
    # signs in through an identity provider. Never a plaintext "password".
    password_hash: Mapped[Optional[str]] = mapped_column(Text)

    identities: Mapped[List["OAuthIdentity"]] = relationship(back_populates="user")
    memberships: Mapped[List["OrganizationMember"]] = relationship(back_populates="user")
    sessions: Mapped[List["UserSession"]] = relationship(back_populates="user")
    audit_jobs: Mapped[List["AuditJob"]] = relationship(back_populates="user")


class OAuthIdentity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "oauth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_oauth_identities_provider_subject"),
        Index("ix_oauth_identities_user_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(320))

    user: Mapped["User"] = relationship(back_populates="identities")


class OrganizationMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_organization_members_org_user"),
        Index("ix_organization_members_user_id", "user_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="member")

    organization: Mapped["Organization"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="memberships")


class UserSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A browser session. Holds no OAuth tokens — the cookie carries a signed
    session id and this row is the authority on whether it is still live."""

    __tablename__ = "user_sessions"
    __table_args__ = (Index("ix_user_sessions_user_id", "user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[Optional[str]] = mapped_column(INET)
    user_agent: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped["User"] = relationship(back_populates="sessions")
