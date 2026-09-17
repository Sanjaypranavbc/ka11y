"""
ka11y/auth/config.py
====================
Everything the auth layer reads from the environment, in one place.

OIDC provider (Google by default; any OpenID Connect issuer works):
  KA11Y_OIDC_ISSUER            https://accounts.google.com
  KA11Y_OIDC_CLIENT_ID         from the provider's console
  KA11Y_OIDC_CLIENT_SECRET
  KA11Y_OIDC_REDIRECT_URI      the *browser-facing* callback, e.g.
                               https://a11y.bluecaffeine.in/api/v1/auth/callback
                               (Next.js rewrites /api/v1/auth/* to this service)
  KA11Y_OIDC_PROVIDER_NAME     label stored in oauth_identities.provider ("google")
  KA11Y_OIDC_SCOPES            "openid email profile"
  KA11Y_OIDC_AUTHORIZATION_ENDPOINT / _TOKEN_ENDPOINT / _USERINFO_ENDPOINT
                               optional overrides that skip discovery (tests, dev)

Sessions (cookie is a signed session id; no tokens stored anywhere):
  KA11Y_SESSION_SECRET         long random string; REQUIRED
  KA11Y_SESSION_IDLE_HOURS     12   — idle timeout for a normal login
  KA11Y_SESSION_REMEMBER_DAYS  30   — idle timeout when "keep me signed in"
  KA11Y_SESSION_MAX_DAYS       30   — absolute lifetime, always enforced
  KA11Y_COOKIE_SECURE          "1"/"0"; default: 1 when the redirect URI is https

Who may sign in (both empty → anyone the provider authenticates):
  KA11Y_ALLOWED_EMAILS         comma-separated, case-insensitive
  KA11Y_ALLOWED_EMAIL_DOMAINS  comma-separated ("bluecaffeine.com,kao.com")
  The same lists gate e-mail + password registration and login.
  KA11Y_ADMIN_EMAILS           comma-separated; only these may open the admin
                               console (/admin) and admin API routes. Empty →
                               nobody is an admin.

E-mail + password sign-in (alternative to OIDC; both can be on at once):
  KA11Y_PASSWORD_LOGIN         "1" (default) / "0" — the login form
  KA11Y_PASSWORD_REGISTRATION  "1" (default) / "0" — self-service "create
                               account" for allow-listed e-mails; with "0"
                               passwords are set by scripts/set_password.py

Redirect targets (relative to the UI origin):
  KA11Y_POST_LOGIN_URL         /dashboard
  KA11Y_LOGIN_PAGE_URL         /login

  KA11Y_AUTH_DISABLED=1        dev/tests only: every protected route runs as
                               an anonymous caller. Never set in production.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import FrozenSet, Optional


def _csv(name: str) -> FrozenSet[str]:
    raw = os.getenv(name, "")
    return frozenset(p.strip().lower() for p in raw.split(",") if p.strip())


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    return v.strip() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class AuthSettings:
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str
    provider_name: str
    scopes: str
    authorization_endpoint: Optional[str]
    token_endpoint: Optional[str]
    userinfo_endpoint: Optional[str]

    session_secret: str
    session_idle_hours: int
    session_remember_days: int
    session_max_days: int
    cookie_secure: bool

    allowed_emails: FrozenSet[str] = field(default_factory=frozenset)
    allowed_domains: FrozenSet[str] = field(default_factory=frozenset)
    admin_emails: FrozenSet[str] = field(default_factory=frozenset)

    post_login_url: str = "/dashboard"
    login_page_url: str = "/login"
    disabled: bool = False
    link_by_verified_email: bool = True
    password_login: bool = True
    password_registration: bool = True

    session_cookie: str = "ka11y_session"
    oidc_cookie: str = "ka11y_oidc"

    @property
    def oidc_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri and self.issuer)

    @property
    def configured(self) -> bool:
        """At least one sign-in method is usable and sessions can be signed."""
        return bool(self.session_secret) and (self.oidc_configured or self.password_login)


def settings() -> AuthSettings:
    """Read the environment every call — cheap, and tests mutate os.environ."""
    redirect = os.getenv("KA11Y_OIDC_REDIRECT_URI", "").strip()
    return AuthSettings(
        issuer=os.getenv("KA11Y_OIDC_ISSUER", "https://accounts.google.com").strip().rstrip("/"),
        client_id=os.getenv("KA11Y_OIDC_CLIENT_ID", "").strip(),
        client_secret=os.getenv("KA11Y_OIDC_CLIENT_SECRET", "").strip(),
        redirect_uri=redirect,
        provider_name=os.getenv("KA11Y_OIDC_PROVIDER_NAME", "google").strip().lower(),
        scopes=os.getenv("KA11Y_OIDC_SCOPES", "openid email profile").strip(),
        authorization_endpoint=os.getenv("KA11Y_OIDC_AUTHORIZATION_ENDPOINT") or None,
        token_endpoint=os.getenv("KA11Y_OIDC_TOKEN_ENDPOINT") or None,
        userinfo_endpoint=os.getenv("KA11Y_OIDC_USERINFO_ENDPOINT") or None,
        session_secret=os.getenv("KA11Y_SESSION_SECRET", "").strip(),
        session_idle_hours=int(os.getenv("KA11Y_SESSION_IDLE_HOURS", "12")),
        session_remember_days=int(os.getenv("KA11Y_SESSION_REMEMBER_DAYS", "30")),
        session_max_days=int(os.getenv("KA11Y_SESSION_MAX_DAYS", "30")),
        cookie_secure=_bool("KA11Y_COOKIE_SECURE", redirect.lower().startswith("https://")),
        allowed_emails=_csv("KA11Y_ALLOWED_EMAILS"),
        allowed_domains=_csv("KA11Y_ALLOWED_EMAIL_DOMAINS"),
        admin_emails=_csv("KA11Y_ADMIN_EMAILS"),
        post_login_url=os.getenv("KA11Y_POST_LOGIN_URL", "/dashboard").strip() or "/dashboard",
        login_page_url=os.getenv("KA11Y_LOGIN_PAGE_URL", "/login").strip() or "/login",
        disabled=_bool("KA11Y_AUTH_DISABLED", False),
        link_by_verified_email=_bool("KA11Y_LINK_BY_VERIFIED_EMAIL", True),
        password_login=_bool("KA11Y_PASSWORD_LOGIN", True),
        password_registration=_bool("KA11Y_PASSWORD_REGISTRATION", True),
    )
