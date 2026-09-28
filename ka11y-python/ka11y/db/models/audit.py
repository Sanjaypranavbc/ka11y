"""
ka11y/db/models/audit.py
========================
One audit execution and everything hanging off it. ``audit_jobs.id`` is the
correlation id for the whole tree and is the same value as the ``job_id`` the
API hands to the client. Since 2026-09-28 this is the ONLY store for a run:
the SQLite run store is gone, so the queue row, the report JSON, the
findings, the assets index, the telemetry and the manual verdicts all live
here, written once.

Responsibility split (keep it):
  audit_jobs      — the execution: who, what url, parameters, status, queue
                    and wall timings, error, output dir (this row IS the queue)
  audit_summary   — one row of counts per job; what dashboards and history read
  audit_results   — the full report JSON, zlib-compressed, one row per job
  audit_pages     — pages crawled
  audit_fails     — individual fail / needs_review findings, flattened for
                    the admin console (passes stay in the report JSON only)
  audit_assets    — content-addressed asset index (bytes on disk / S3)
  finding_reviews — manual verdicts on needs_review findings
  stage_timings   — per-(page, stage, rule) telemetry
  reports         — metadata + S3 key of generated files (bytes live in S3)
  audit_logs      — permanent event log, append-only, BIGINT id
  crash_reports   — what went wrong when a job/worker died

Children cascade from the job so a retention delete of one job is one DELETE.
Nothing cascades from users/organizations (they are soft-deleted).
``user_id`` is NULL for a run submitted with KA11Y_AUTH_DISABLED (anonymous).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sqlalchemy import func

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

    # NULL: submitted anonymously (KA11Y_AUTH_DISABLED). Ownership checks
    # treat such a job as visible to any signed-in user.
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("user_sessions.id", ondelete="SET NULL")
    )
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    # queued | running | completed | failed | cancelled — this row is the queue.
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    crawl_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    requested_pages: Mapped[Optional[int]] = mapped_column(Integer)
    actual_pages: Mapped[Optional[int]] = mapped_column(Integer)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Run parameters and outcome (formerly the SQLite ``runs`` row).
    lang_requested: Mapped[Optional[str]] = mapped_column(String(16))
    lang_resolved: Mapped[Optional[str]] = mapped_column(String(16))
    wcag_level: Mapped[Optional[str]] = mapped_column(String(8))
    # The full CombinedRequest (toggles, depth, max_pages): what a re-run replays.
    params: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    queue_wait_ms: Mapped[Optional[int]] = mapped_column(Integer)
    wall_ms: Mapped[Optional[int]] = mapped_column(Integer)
    error_id: Mapped[Optional[str]] = mapped_column(String(64))
    error_stage: Mapped[Optional[str]] = mapped_column(String(100))
    # Crash-requeue counter (KA11Y_MAX_ATTEMPTS).
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    worker_pid: Mapped[Optional[int]] = mapped_column(Integer)
    output_dir: Mapped[Optional[str]] = mapped_column(Text)
    # report["summary"] verbatim ({violations, needs_review, passes, score, …});
    # audit_summary holds the same numbers as typed counts for dashboards.
    summary: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)

    user: Mapped[Optional["User"]] = relationship(back_populates="audit_jobs")
    summary_row: Mapped[Optional["AuditSummary"]] = relationship(
        back_populates="job", uselist=False, cascade="all, delete-orphan"
    )
    result: Mapped[Optional["AuditResult"]] = relationship(
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

    job: Mapped["AuditJob"] = relationship(back_populates="summary_row")


class AuditResult(Base):
    """The complete report JSON of a finished run, zlib-compressed. One row per
    job; what GET /combined/{job_id} serves after the hot cache forgot the
    run, and what every export is built from."""

    __tablename__ = "audit_results"

    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("audit_jobs.id", ondelete="CASCADE"), primary_key=True
    )
    report_zlib: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    bytes_raw: Mapped[Optional[int]] = mapped_column(Integer)
    bytes_stored: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    job: Mapped["AuditJob"] = relationship(back_populates="result")


class AuditPage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audit_pages"
    __table_args__ = (
        Index("ix_audit_pages_job_id", "job_id"),
        Index("ix_audit_pages_job_scan_status", "job_id", "scan_status"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("audit_jobs.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)  # resolved (post-redirect)
    title: Mapped[Optional[str]] = mapped_column(Text)
    status_code: Mapped[Optional[int]] = mapped_column(Integer)
    scan_status: Mapped[str] = mapped_column(String(30), nullable=False, default="completed")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    depth: Mapped[Optional[int]] = mapped_column(Integer)
    crawl_ms: Mapped[Optional[int]] = mapped_column(Integer)
    snapshot_ref: Mapped[Optional[str]] = mapped_column(Text)

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
        Index("ix_audit_fails_job_wcag_sc", "job_id", "wcag_sc"),
        Index("ix_audit_fails_created_at", "created_at"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("audit_jobs.id", ondelete="CASCADE"), nullable=False
    )
    # Findings are flattened straight from the report, which knows pages by
    # url, so the page row is optional and ``page_url`` is the working key.
    page_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("audit_pages.id", ondelete="CASCADE")
    )
    page_url: Mapped[Optional[str]] = mapped_column(Text)
    # Nullable: an engine can report a best-practice failure with no WCAG SC.
    wcag_rule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("wcag_rules.id", ondelete="RESTRICT")
    )
    wcag_sc: Mapped[Optional[str]] = mapped_column(String(16))
    level: Mapped[Optional[str]] = mapped_column(String(4))
    severity: Mapped[Optional[str]] = mapped_column(String(30))
    # fail | needs_review (passes are not flattened; the report JSON has them)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="fail")
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[Optional[str]] = mapped_column(String(16))  # axe | python
    reason_code: Mapped[Optional[str]] = mapped_column(String(100))
    selector: Mapped[Optional[str]] = mapped_column(Text)
    html_snippet: Mapped[Optional[str]] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    recommendation: Mapped[Optional[str]] = mapped_column(Text)
    element: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)
    metadata_: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSONB)

    job: Mapped["AuditJob"] = relationship(back_populates="fails")
    page: Mapped[Optional["AuditPage"]] = relationship(back_populates="fails")


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
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
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


class AuditAsset(Base):
    """Content-addressed asset index (``ka11y/store/assets.py``): bytes live
    under KA11Y_ASSET_DIR (and, once mirrored, in object storage); this row
    is the authority for where. Integer id: it is the public
    ``/api/v1/assets/{id}`` handle."""

    __tablename__ = "audit_assets"
    __table_args__ = (
        UniqueConstraint("job_id", "rel_path", name="uq_audit_assets_job_rel_path"),
        Index("ix_audit_assets_job_id", "job_id"),
        Index("ix_audit_assets_sha256", "sha256"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("audit_jobs.id", ondelete="CASCADE"), nullable=False
    )
    page_url: Mapped[Optional[str]] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    rel_path: Mapped[str] = mapped_column(Text, nullable=False)  # relative to KA11Y_ASSET_DIR
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime: Mapped[Optional[str]] = mapped_column(String(100))
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    # Where the bytes live in object storage (S3 or the local artifact dir);
    # NULL = never uploaded (storage off), the on-disk rel_path is the only copy.
    object_key: Mapped[Optional[str]] = mapped_column(Text)
    object_bucket: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )


class FindingReview(Base):
    """A reviewer's decision (pass | violation) on one needs_review finding.
    ``finding_id`` is the report's stable per-finding signature."""

    __tablename__ = "finding_reviews"
    __table_args__ = (Index("ix_finding_reviews_job_id", "job_id"),)

    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("audit_jobs.id", ondelete="CASCADE"), primary_key=True
    )
    finding_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text)
    reviewer: Mapped[Optional[str]] = mapped_column(String(320))
    wcag_sc: Mapped[Optional[str]] = mapped_column(String(16))
    page_url: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )


class StageTiming(Base):
    """One row per fine-grained step (page × stage × rule) of a run. Written
    fire-and-forget by the telemetry sinks; read by /admin/metrics and the
    durable fallback of GET /combined/{job_id}/timings."""

    __tablename__ = "stage_timings"
    __table_args__ = (
        Index("ix_stage_timings_job_id", "job_id"),
        Index("ix_stage_timings_job_stage", "job_id", "stage"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("audit_jobs.id", ondelete="CASCADE"), nullable=False
    )
    page_url: Mapped[Optional[str]] = mapped_column(Text)
    depth: Mapped[Optional[int]] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(100), nullable=False)
    sub_stage: Mapped[Optional[str]] = mapped_column(String(100))
    rule: Mapped[Optional[str]] = mapped_column(String(100))
    duration_ms: Mapped[Optional[float]] = mapped_column(Float)
    item_count: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[Optional[str]] = mapped_column(String(20))  # ok | error | timeout
    error: Mapped[Optional[str]] = mapped_column(Text)
    extra: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
