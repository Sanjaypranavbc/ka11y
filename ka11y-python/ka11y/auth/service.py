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

E-mail + password (``register_local`` / ``login_local`` / ``set_password``)
goes through the same allow-list and the same ``users`` / organization rows;
only the credential differs (``users.password_hash``).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ka11y.auth.config import settings
from ka11y.auth.oidc import ExternalIdentity, OIDCError
from ka11y.auth.passwords import hash_password, needs_rehash, password_policy_error, verify_password
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


# ── e-mail + password ────────────────────────────────────────────────────────


class AuthError(Exception):
    """A password-flow failure; ``code`` is what the UI translates."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code


def _norm_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not email or "@" not in email or len(email) > 320:
        raise AuthError("invalid_credentials", "malformed e-mail")
    return email


async def register_local(*, email: str, password: str, name: Optional[str]) -> User:
    """Create an allow-listed user with a password. Raises AuthError:
    not_allowed, weak_password, account_exists, register_disabled."""
    cfg = settings()
    if not (cfg.password_login and cfg.password_registration):
        raise AuthError("register_disabled")
    email = _norm_email(email)
    if not is_email_allowed(email):
        raise AuthError("not_allowed", f"{email} is not on the allow-list")
    policy = password_policy_error(password)
    if policy:
        raise AuthError(policy)
    now = datetime.now(timezone.utc)
    async with session_scope() as s:
        existing = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if existing is not None:
            # Never let a second person claim an address that already has an
            # account (OIDC or password); the owner uses sign-in or an admin
            # resets the password with scripts/set_password.py.
            raise AuthError("account_exists", f"{email} already registered")
        user = User(
            email=email,
            name=(name or "").strip()[:255] or None,
            status="active",
            password_hash=hash_password(password),
            last_login_at=now,
        )
        s.add(user)
        await s.flush()
        org = await _ensure_organization(s, email)
        await _ensure_membership(s, org, user)
        await s.flush()
        logger.info("[auth] registered user %s (%s) with password", user.id, user.email)
        return user


async def login_local(*, email: str, password: str) -> User:
    """Verify e-mail + password. Raises AuthError: invalid_credentials,
    not_allowed, no_password, account_suspended, login_disabled."""
    cfg = settings()
    if not cfg.password_login:
        raise AuthError("login_disabled")
    email = _norm_email(email)
    # Allow-list first: removing someone from the list locks them out even if
    # their row and password still exist.
    if not is_email_allowed(email):
        raise AuthError("not_allowed", f"{email} is not on the allow-list")
    async with session_scope() as s:
        user = (
            await s.execute(select(User).where(User.email == email, User.deleted_at.is_(None)))
        ).scalar_one_or_none()
        if user is None:
            # Burn the same time as a real check so the response does not
            # reveal whether the address exists.
            verify_password(password, hash_password("timing-equalizer"))
            raise AuthError("invalid_credentials")
        if not user.password_hash:
            raise AuthError("no_password", f"{email} has no password (OIDC-only account)")
        if not verify_password(password, user.password_hash):
            raise AuthError("invalid_credentials")
        if user.status != "active":
            raise AuthError("account_suspended", f"user {email} is {user.status}")
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        user.last_login_at = datetime.now(timezone.utc)
        org = await _ensure_organization(s, email)
        await _ensure_membership(s, org, user)
        await s.flush()
        return user


async def set_password(*, email: str, password: str, create: bool = False) -> User:
    """Admin path (scripts/set_password.py): set or reset a password. With
    ``create`` an allow-listed address that has no account yet is created."""
    email = _norm_email(email)
    policy = password_policy_error(password)
    if policy:
        raise AuthError(policy)
    async with session_scope() as s:
        user = (
            await s.execute(select(User).where(User.email == email, User.deleted_at.is_(None)))
        ).scalar_one_or_none()
        if user is None:
            if not create:
                raise AuthError("no_such_user", f"{email} not found")
            if not is_email_allowed(email):
                raise AuthError("not_allowed", f"{email} is not on the allow-list")
            user = User(email=email, status="active")
            s.add(user)
            await s.flush()
            org = await _ensure_organization(s, email)
            await _ensure_membership(s, org, user)
        user.password_hash = hash_password(password)
        await s.flush()
        return user


async def bootstrap_allow_listed_users(password: str) -> tuple[int, int]:
    """Start-up seeding (KA11Y_BOOTSTRAP_PASSWORD): every address in
    KA11Y_ALLOWED_EMAILS gets an account, and any of them without a password
    gets *password*. Idempotent; never overwrites an existing password, so a
    password changed later with scripts/set_password.py survives restarts.
    Returns (users created, passwords set)."""
    cfg = settings()
    policy = password_policy_error(password)
    if policy:
        raise AuthError(policy, "KA11Y_BOOTSTRAP_PASSWORD does not meet the password rules")
    created = assigned = 0
    for email in sorted(cfg.allowed_emails):
        async with session_scope() as s:
            user = (
                await s.execute(select(User).where(User.email == email, User.deleted_at.is_(None)))
            ).scalar_one_or_none()
            if user is None:
                user = User(email=email, status="active")
                s.add(user)
                await s.flush()
                org = await _ensure_organization(s, email)
                await _ensure_membership(s, org, user)
                created += 1
            if not user.password_hash:
                user.password_hash = hash_password(password)
                assigned += 1
            await s.flush()
    return created, assigned
