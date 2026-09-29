"""One store: the SQLite run store folds into PostgreSQL.

audit_jobs becomes the queue/run row (parameters, queue + wall timings,
error, output dir, summary; user_id nullable for anonymous runs);
audit_pages / audit_fails gain the crawl and finding columns the report
flattens into; reports.user_id nullable; new tables audit_results (report
JSON), audit_assets (asset index), finding_reviews (manual verdicts) and
stage_timings (telemetry).

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-28 12:00:00+00:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── audit_jobs: the run row ─────────────────────────────────────────────
    op.alter_column('audit_jobs', 'user_id', existing_type=sa.Uuid(), nullable=True)
    op.add_column('audit_jobs', sa.Column('lang_requested', sa.String(length=16), nullable=True))
    op.add_column('audit_jobs', sa.Column('lang_resolved', sa.String(length=16), nullable=True))
    op.add_column('audit_jobs', sa.Column('wcag_level', sa.String(length=8), nullable=True))
    op.add_column('audit_jobs', sa.Column('params', postgresql.JSONB(astext_type=sa.Text()),
                                          server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.add_column('audit_jobs', sa.Column('queue_wait_ms', sa.Integer(), nullable=True))
    op.add_column('audit_jobs', sa.Column('wall_ms', sa.Integer(), nullable=True))
    op.add_column('audit_jobs', sa.Column('error_id', sa.String(length=64), nullable=True))
    op.add_column('audit_jobs', sa.Column('error_stage', sa.String(length=100), nullable=True))
    op.add_column('audit_jobs', sa.Column('attempt', sa.Integer(), server_default='0', nullable=False))
    op.add_column('audit_jobs', sa.Column('worker_pid', sa.Integer(), nullable=True))
    op.add_column('audit_jobs', sa.Column('output_dir', sa.Text(), nullable=True))
    op.add_column('audit_jobs', sa.Column('summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # ── audit_pages: crawl record ───────────────────────────────────────────
    op.add_column('audit_pages', sa.Column('depth', sa.Integer(), nullable=True))
    op.add_column('audit_pages', sa.Column('crawl_ms', sa.Integer(), nullable=True))
    op.add_column('audit_pages', sa.Column('snapshot_ref', sa.Text(), nullable=True))

    # ── audit_fails: flattened fail / needs_review findings ─────────────────
    op.alter_column('audit_fails', 'page_id', existing_type=sa.Uuid(), nullable=True)
    op.alter_column('audit_fails', 'severity', existing_type=sa.String(length=30), nullable=True)
    op.add_column('audit_fails', sa.Column('page_url', sa.Text(), nullable=True))
    op.add_column('audit_fails', sa.Column('wcag_sc', sa.String(length=16), nullable=True))
    op.add_column('audit_fails', sa.Column('level', sa.String(length=4), nullable=True))
    op.add_column('audit_fails', sa.Column('source', sa.String(length=16), nullable=True))
    op.add_column('audit_fails', sa.Column('reason_code', sa.String(length=100), nullable=True))
    op.add_column('audit_fails', sa.Column('element', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_index('ix_audit_fails_job_wcag_sc', 'audit_fails', ['job_id', 'wcag_sc'], unique=False)
    op.create_index('ix_audit_fails_created_at', 'audit_fails', ['created_at'], unique=False)

    # ── reports: anonymous runs have no user ────────────────────────────────
    op.alter_column('reports', 'user_id', existing_type=sa.Uuid(), nullable=True)

    # ── audit_results: the report JSON ──────────────────────────────────────
    op.create_table(
        'audit_results',
        sa.Column('job_id', sa.Uuid(), nullable=False),
        sa.Column('report_zlib', sa.LargeBinary(), nullable=False),
        sa.Column('bytes_raw', sa.Integer(), nullable=True),
        sa.Column('bytes_stored', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['audit_jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('job_id'),
    )

    # ── audit_assets: content-addressed asset index ─────────────────────────
    op.create_table(
        'audit_assets',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column('job_id', sa.Uuid(), nullable=False),
        sa.Column('page_url', sa.Text(), nullable=True),
        sa.Column('kind', sa.String(length=40), nullable=False),
        sa.Column('rel_path', sa.Text(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('mime', sa.String(length=100), nullable=True),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('bytes', sa.BigInteger(), nullable=True),
        sa.Column('object_key', sa.Text(), nullable=True),
        sa.Column('object_bucket', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['audit_jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id', 'rel_path', name='uq_audit_assets_job_rel_path'),
    )
    op.create_index('ix_audit_assets_job_id', 'audit_assets', ['job_id'], unique=False)
    op.create_index('ix_audit_assets_sha256', 'audit_assets', ['sha256'], unique=False)

    # ── finding_reviews: manual verdicts ────────────────────────────────────
    op.create_table(
        'finding_reviews',
        sa.Column('job_id', sa.Uuid(), nullable=False),
        sa.Column('finding_id', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('reviewer', sa.String(length=320), nullable=True),
        sa.Column('wcag_sc', sa.String(length=16), nullable=True),
        sa.Column('page_url', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['audit_jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('job_id', 'finding_id'),
    )
    op.create_index('ix_finding_reviews_job_id', 'finding_reviews', ['job_id'], unique=False)

    # ── stage_timings: telemetry ────────────────────────────────────────────
    op.create_table(
        'stage_timings',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column('job_id', sa.Uuid(), nullable=False),
        sa.Column('page_url', sa.Text(), nullable=True),
        sa.Column('depth', sa.Integer(), nullable=True),
        sa.Column('stage', sa.String(length=100), nullable=False),
        sa.Column('sub_stage', sa.String(length=100), nullable=True),
        sa.Column('rule', sa.String(length=100), nullable=True),
        sa.Column('duration_ms', sa.Float(), nullable=True),
        sa.Column('item_count', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('extra', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('ts', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['audit_jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_stage_timings_job_id', 'stage_timings', ['job_id'], unique=False)
    op.create_index('ix_stage_timings_job_stage', 'stage_timings', ['job_id', 'stage'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_stage_timings_job_stage', table_name='stage_timings')
    op.drop_index('ix_stage_timings_job_id', table_name='stage_timings')
    op.drop_table('stage_timings')
    op.drop_index('ix_finding_reviews_job_id', table_name='finding_reviews')
    op.drop_table('finding_reviews')
    op.drop_index('ix_audit_assets_sha256', table_name='audit_assets')
    op.drop_index('ix_audit_assets_job_id', table_name='audit_assets')
    op.drop_table('audit_assets')
    op.drop_table('audit_results')

    # Rows written by anonymous runs (NULL user) cannot survive the NOT NULL
    # constraints below; they are removed first, which is the data cost of
    # going back to the ownership-only schema.
    op.execute("DELETE FROM reports WHERE user_id IS NULL")
    op.alter_column('reports', 'user_id', existing_type=sa.Uuid(), nullable=False)

    op.drop_index('ix_audit_fails_created_at', table_name='audit_fails')
    op.drop_index('ix_audit_fails_job_wcag_sc', table_name='audit_fails')
    for col in ('element', 'reason_code', 'source', 'level', 'wcag_sc', 'page_url'):
        op.drop_column('audit_fails', col)
    op.execute("DELETE FROM audit_fails WHERE page_id IS NULL OR severity IS NULL")
    op.alter_column('audit_fails', 'severity', existing_type=sa.String(length=30), nullable=False)
    op.alter_column('audit_fails', 'page_id', existing_type=sa.Uuid(), nullable=False)

    for col in ('snapshot_ref', 'crawl_ms', 'depth'):
        op.drop_column('audit_pages', col)

    for col in ('summary', 'output_dir', 'worker_pid', 'attempt', 'error_stage', 'error_id',
                'wall_ms', 'queue_wait_ms', 'params', 'wcag_level', 'lang_resolved', 'lang_requested'):
        op.drop_column('audit_jobs', col)
    op.execute("DELETE FROM audit_jobs WHERE user_id IS NULL")
    op.alter_column('audit_jobs', 'user_id', existing_type=sa.Uuid(), nullable=False)
