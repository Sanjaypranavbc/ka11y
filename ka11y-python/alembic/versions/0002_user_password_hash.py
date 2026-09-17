"""Add users.password_hash for the e-mail + password sign-in.

Nullable: users created through OIDC have no password until they set one.
The value is a self-describing scrypt string (see ka11y/auth/passwords.py).

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-17 17:30:00+00:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('password_hash', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'password_hash')
