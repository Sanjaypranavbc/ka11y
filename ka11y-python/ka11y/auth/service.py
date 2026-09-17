"""
ka11y/auth/service.py
=====================
Turn a verified external identity into an application user (spec §23/§24).

    identity (provider, sub) known?  → that user
    else verified email matches a live user (link policy on) → link identity
    else                              → new user + identity
    then: organization from the email domain (created on first sight),
          membership (first member = owner, later = member), last_login_at.

Allow-listing (KA11Y_ALLOWED_EMAILS / _DOMAINS) is checked *before* any row
is written, so an unwanted sign-in leaves no trace in ``users``.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ka11y.auth.config import settings
from ka11y.auth.oidc import ExternalIdentity, OIDCError
from ka11y.config.logger import setup_logger
from ka11y.db.engine import session_scope
from ka11y.db.models import OAuthIdentity, Organization, OrganizationMember, User

logger = setup_logger(name="KAC", tag="auth")


def is_email_allowed(email: str) -> bool:
    cfg = settings()
    email = email.strip().lower()
    if not cfg.allowed_emails and not cfg.allowed_domains:
        return True
    if email in cfg.allowed_emails:
        return True
    domain = email.rpartition("@")[2]
    return domain in cfg.allowed_domains


def org_slug_for_email(email: str) -> str:
    """'someone@kao.com' → 'kao'; 'x@mail.example.co.jp' → 'mail-example-co-jp'."""
    domain = email.rpartition("@")[2].lower()
    parts = domain.split(".")
    slug = parts[0] if len(parts) <= 2 else "-".join(parts)
    slug = re.sub(r"[^a-z0-9-]+", "-", slug).strip("-")
    return slug or "default"


async def _ensure_organization(s: AsyncSession, email: str) -> Organization:
    slug = org_slug_for_email(email)
    org = (await s.execute(select(Organization).where(Organization.slug == slug))).scalar_one_or_none()
    if org is None:
        org = Organization(name=email.rpartition("@")[2].lower(), slug=slug, status="active")
        s.add(org)
        await s.flush()
    return org


async def _ensure_membership(s: AsyncSession, org: Organization, user: User) -> OrganizationMember:
    member = (
        await s.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org.id,
                OrganizationMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if member is None:
        count = (
            await s.execute(
                select(func.count()).select_from(OrganizationMember).where(
                    OrganizationMember.organization_id == org.id
                )
            )
        ).scalar_one()
        member = OrganizationMember(
            organization_id=org.id, user_id=user.id, role="owner" if count == 0 else "member"
        )
        s.add(member)
        await s.flush()
    return member


async def login_identity(ext: ExternalIdentity) -> User:
    """Resolve/create the user for *ext*. Raises OIDCError on policy failures."""
    if not is_email_allowed(ext.email):
        raise OIDCError("not_allowed", f"{ext.email} is not on the allow-list")
    cfg = settings()
    now = datetime.now(timezone.utc)

    async with session_scope() as s:
        ident = (
            await s.execute(
                select(OAuthIdentity).where(
                    OAuthIdentity.provider == ext.provider,
                    OAuthIdentity.provider_user_id == ext.subject,
                )
            )
        ).scalar_one_or_none()

        user: Optional[User] = None
        if ident is not None:
            user = await s.get(User, ident.user_id)
        elif cfg.link_by_verified_email and ext.email_verified:
            user = (
                await s.execute(select(User).where(User.email == ext.email, User.deleted_at.is_(None)))
            ).scalar_one_or_none()

        if user is None:
            if not ext.email_verified:
                raise OIDCError("email_unverified", "provider did not verify the email")
            user = User(
                email=ext.email,
                name=ext.name,
                profile_image_url=ext.picture,
                status="active",
                locale=ext.locale,
            )
            s.add(user)
            await s.flush()
            logger.info("[auth] created user %s (%s)", user.id, user.email)

        if user.deleted_at is not None or user.status != "active":
            raise OIDCError("account_suspended", f"user {user.email} is {user.status}")

        if ident is None:
            s.add(
                OAuthIdentity(
                    user_id=user.id,
                    provider=ext.provider,
                    provider_user_id=ext.subject,
                    email=ext.email,
                )
            )
        else:
            ident.email = ext.email

        # Keep the profile fresh; never blank a field the provider stopped sending.
        user.name = ext.name or user.name
        user.profile_image_url = ext.picture or user.profile_image_url
        user.last_login_at = now

        org = await _ensure_organization(s, ext.email)
        await _ensure_membership(s, org, user)
        await s.flush()
        return user


async def primary_membership(user_id) -> Optional[OrganizationMember]:
    async with session_scope() as s:
        return (
            await s.execute(
                select(OrganizationMember)
                .where(OrganizationMember.user_id == user_id)
                .order_by(OrganizationMember.created_at)
                .limit(1)
            )
        ).scalar_one_or_none()
