"""
ka11y/db — production PostgreSQL layer (SQLAlchemy 2.0 async + Alembic).

    from ka11y.db import is_configured, session_scope

Startup sequence (``ka11y.main`` lifespan → :func:`init_postgres`):
  1. DATABASE_URL set?  no → log + return, everything PG-backed stays inert
  2. ping
  3. ``alembic upgrade head`` (unless KA11Y_DB_AUTO_MIGRATE=0)
  4. seed the WCAG rule catalogue (idempotent)

The SQLite run store in ``ka11y/store`` is a separate, older layer and keeps
working with or without this one.
"""

from __future__ import annotations

from ka11y.config.logger import setup_logger
from ka11y.db.engine import (
    dispose,
    get_engine,
    get_sessionmaker,
    is_configured,
    ping,
    session_scope,
)

logger = setup_logger(name="KAC", tag="db")

__all__ = [
    "dispose",
    "get_engine",
    "get_sessionmaker",
    "init_postgres",
    "is_configured",
    "ping",
    "session_scope",
    "shutdown_postgres",
]


async def init_postgres() -> bool:
    """Bring the PG layer up. Returns True when it is usable. Never raises."""
    if not is_configured():
        logger.info("[db] DATABASE_URL not set — PostgreSQL layer disabled")
        return False
    try:
        if not await ping():
            return False
        from ka11y.db.migrate import auto_migrate_enabled, upgrade_head

        if auto_migrate_enabled():
            await upgrade_head()
        from ka11y.db.seed import seed_all

        await seed_all()
        logger.info("[db] PostgreSQL ready")
        return True
    except Exception:  # noqa: BLE001
        logger.exception("[db] PostgreSQL initialisation failed; PG-backed features disabled")
        return False


async def shutdown_postgres() -> None:
    try:
        await dispose()
    except Exception:  # noqa: BLE001
        logger.debug("[db] dispose failed", exc_info=True)
