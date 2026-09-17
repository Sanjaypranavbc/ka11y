"""
ka11y/db/models/audit.py
========================
One audit execution and everything hanging off it. ``audit_jobs.id`` is the
correlation id for the whole tree and is the same value as the ``job_id`` the
API hands to the client and the SQLite run store uses as ``run_id``.

Responsibility split (keep it):
  audit_jobs      — the execution: who, what url, status, timings
  audit_summary   — one row of counts per job; what dashboards and history read
  audit_pages     — pages scanned
  audit_fails     — individual WCAG failures ("fails", not "violations")
  reports         — metadata + S3 key of generated files (bytes live in S3)
  audit_logs      — permanent event log, append-only, BIGINT id
  crash_reports   — what went wrong when a job/worker died

Children cascade from the job so a retention delete of one job is one DELETE.
Nothing cascades from users/organizations (they are soft-deleted).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ka11y.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow

if TYPE_CHECKING:
    from ka11y.db.models.identity import User


class AuditJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audit_jobs"
    __table_args__ = (
        Index("ix_audit_jobs_user_created", "user_id", "created_at"),
        Index("ix_audit_jobs_org_created", "organization_id", "created_at"),
        Index("ix_audit_jobs_status", "status"),
        Index("ix_audit_jobs_session_id", "session_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("user_sessions.id", ondelete="SET NULL")
    )
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    crawl_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    requested_pages: Mapped[Optional[int]] = mapped_column(Integer)
    actual_pages: Mapped[Optional[int]] = mapped_column(Integer)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="audit_jobs")
    summary: Mapped[Optional["AuditSummary"]] = relationship(
        back_populates="job", uselist=False, cascade="all, delete-orphan"
    )
    pages: Mapped[List["AuditPage"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    fails: Mapped[List["AuditFail"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    reports: Mapped[List["Report"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class AuditSummary(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audit_summary"
    __table_args__ = (UniqueConstraint("job_id", name="uq_audit_summary_job_id"),)

    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("audit_jobs.id", ondelete="CASCADE"), nullable=False
    )
    total_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_fails: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    critical_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    serious_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    moderate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    minor_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    needs_review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[Optional[int]] = mapped_column(BigInteger)

    job: Mapped["AuditJob"] = relationship(back_populates="summary")


class AuditPage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audit_pages"
    __table_args__ = (
        Index("ix_audit_pages_job_id", "job_id"),
        Index("ix_audit_pages_job_scan_status", "job_id", "scan_status"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("audit_jobs.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(Text)
    status_code: Mapped[Optional[int]] = mapped_column(Integer)
    scan_status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    job: Mapped["AuditJob"] = relationship(back_populates="pages")
    fails: Mapped[List["AuditFail"]] = relationship(back_populates="page", cascade="all, delete-orphan")


class AuditFail(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audit_fails"
    __table_args__ = (
        Index("ix_audit_fails_job_id", "job_id"),
        Index("ix_audit_fails_page_id", "page_id"),
        Index("ix_audit_fails_wcag_rule_id", "wcag_rule_id"),
        Index("ix_audit_fails_job_needs_review", "job_id", "needs_review"),
        Index("ix_audit_fails_job_severity", "job_id", "severity"),
        Index("ix_audit_fails_job_status", "job_id", "status"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("audit_jobs.id", ondelete="CASCADE"), nullable=False
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("audit_pages.id", ondelete="CASCADE"), nullable=False
    )
    # Nullable: an engine can report a best-practice failure with no WCAG SC.
    wcag_rule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("wcag_rules.id", ondelete="RESTRICT")
    )
    severity: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    selector: Mapped[Optional[str]] = mapped_column(Text)
    html_snippet: Mapped[Optional[str]] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    recommendation: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSONB)

    job: Mapped["AuditJob"] = relationship(back_populates="fails")
    page: Mapped["AuditPage"] = relationship(back_populates="fails")


class Report(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_reports_job_id", "job_id"),
        Index("ix_reports_user_created", "user_id", "created_at"),
        Index("ix_reports_org_created", "organization_id", "created_at"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("audit_jobs.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    report_type: Mapped[str] = mapped_column(String(50), nullable=False)
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="generating")
    s3_bucket: Mapped[Optional[str]] = mapped_column(String(255))
    s3_key: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)

    job: Mapped["AuditJob"] = relationship(back_populates="reports")


class AuditLog(Base):
    """Append-only. BIGINT identity rather than UUID: high volume, never exposed."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_job_created", "job_id", "created_at"),
        Index("ix_audit_logs_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("audit_jobs.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_status: Mapped[Optional[str]] = mapped_column(String(30))
    message: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class CrashReport(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "crash_reports"
    __table_args__ = (
        Index("ix_crash_reports_job_id", "job_id"),
        Index("ix_crash_reports_created_at", "created_at"),
    )

    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("audit_jobs.id", ondelete="CASCADE")
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    service: Mapped[Optional[str]] = mapped_column(String(100))
    stage: Mapped[Optional[str]] = mapped_column(String(100))
    error_type: Mapped[Optional[str]] = mapped_column(String(255))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    stack_trace: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
