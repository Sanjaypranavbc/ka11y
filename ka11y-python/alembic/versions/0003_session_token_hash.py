"""Add user_sessions.token_hash: the SHA-256 of the per-session bearer token.

The cookie now carries ``<session id>.<token>.<remember>``; the DB keeps only
the hash, so the table alone can never be replayed as a cookie. Pre-existing
rows keep NULL and are refused by ``sessions.resolve`` (everyone signs in
again once), and are closed here so the admin console does not list them as
live.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-23 14:00:00+00:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('user_sessions', sa.Column('token_hash', sa.String(length=64), nullable=True))
    op.execute("UPDATE user_sessions SET ended_at = now() WHERE ended_at IS NULL")


def downgrade() -> None:
    op.drop_column('user_sessions', 'token_hash')
