"""
ka11y/db/migrate.py
===================
Run Alembic migrations programmatically at application startup, the same way
the SQLite store applies its own migrations in ``store/db.py``.

Controlled by ``KA11Y_DB_AUTO_MIGRATE`` (default "1"). Turn it off in any
deployment where migrations are applied by a release step instead
(``alembic upgrade head``) — for instance multiple API replicas starting at
once. Alembic's own version table makes a second concurrent ``upgrade`` a
no-op, but "one writer at release time" is the safer habit.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="db.migrate")

_INI = Path(__file__).resolve().parent.parent.parent / "alembic.ini"


def upgrade_head_sync() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_INI))
    command.upgrade(cfg, "head")


async def upgrade_head() -> None:
    """Blocking Alembic run pushed to a thread so the event loop keeps serving."""
    await asyncio.to_thread(upgrade_head_sync)


def auto_migrate_enabled() -> bool:
    return os.getenv("KA11Y_DB_AUTO_MIGRATE", "1") == "1"
