"""All ORM models. Import this module (not the submodules) wherever
``Base.metadata`` must be complete — Alembic's env.py, the seeders, tests."""

from ka11y.db.base import Base
from ka11y.db.models.audit import (
    AuditFail,
    AuditJob,
    AuditLog,
    AuditPage,
    AuditSummary,
    CrashReport,
    Report,
)
from ka11y.db.models.catalog import WcagRule
from ka11y.db.models.feedback import Feedback
from ka11y.db.models.identity import (
    OAuthIdentity,
    Organization,
    OrganizationMember,
    User,
    UserSession,
)

__all__ = [
    "Base",
    "Organization",
    "User",
    "OAuthIdentity",
    "OrganizationMember",
    "UserSession",
    "WcagRule",
    "AuditJob",
    "AuditSummary",
    "AuditPage",
    "AuditFail",
    "Report",
    "AuditLog",
    "CrashReport",
    "Feedback",
]
