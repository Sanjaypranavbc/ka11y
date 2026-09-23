"""
ka11y/db/engine.py
==================
Async SQLAlchemy engine + session factory for the production PostgreSQL DB.

Configuration is one environment variable::

    DATABASE_URL=postgresql://user:pass@host:5432/ka11y

Any of ``postgresql://``, ``postgres://`` or ``postgresql+psycopg://`` is
accepted; the URL is normalised to the psycopg 3 driver, which serves both the
app (async) and Alembic (sync) — see ``alembic/env.py``. Nothing here assumes
RDS: the same URL shape works for a local ``postgres:16`` container and for an
RDS endpoint. TLS: when the URL carries no ``sslmode`` one is added —
``require`` for any non-local host (RDS, a managed Postgres), nothing for
``localhost`` / ``127.0.0.1`` / the compose ``postgres`` service, whose
traffic never leaves the private network. ``KA11Y_DB_SSLMODE`` overrides both
(``verify-full`` + ``KA11Y_DB_SSLROOTCERT`` pins the CA, the strongest
setting; ``disable`` turns it off).

``DATABASE_URL`` unset → :func:`is_configured` is False, no engine is created,
and every caller degrades: auth reports "not configured", the audit bridge
skips its writes. The SQLite run store (``ka11y/store``) is unaffected.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="db")

_engine: Optional[AsyncEngine] = None
_sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None
# id() of the event loop the engine was created on. An async engine's pooled
# connections belong to that loop; awaiting them from another loop hangs
# forever. Production has one loop (uvicorn), but the test suite opens several
# (TestClient portals, asyncio.run), so a loop change recreates the engine.
_engine_loop_id: Optional[int] = None


_LOCAL_DB_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres", "db"}


def database_url() -> Optional[str]:
    raw = os.getenv("DATABASE_URL", "").strip()
    return apply_tls_default(normalize_url(raw)) if raw else None


def apply_tls_default(url: str) -> str:
    """Add ``sslmode`` (and ``sslrootcert``) to a PostgreSQL URL that has none.

    Explicit query parameters in the URL always win. ``KA11Y_DB_SSLMODE``
    comes next. Otherwise any host that is not on the local list gets
    ``sslmode=require`` so credentials and audit data never cross a network
    in clear text by accident.
    """
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    override = os.getenv("KA11Y_DB_SSLMODE", "").strip()
    rootcert = os.getenv("KA11Y_DB_SSLROOTCERT", "").strip()
    if "sslmode" not in query:
        if override:
            query["sslmode"] = override
        elif (parts.hostname or "").lower() not in _LOCAL_DB_HOSTS:
            query["sslmode"] = "require"
    if rootcert and "sslrootcert" not in query and query.get("sslmode") not in (None, "disable"):
        query["sslrootcert"] = rootcert
    return urlunsplit(parts._replace(query=urlencode(query)))


def normalize_url(url: str) -> str:
    """Force the psycopg 3 driver so one URL serves app + Alembic."""
    for prefix in ("postgresql+psycopg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def is_configured() -> bool:
    return database_url() is not None


def _current_loop_id() -> Optional[int]:
    import asyncio

    try:
        return id(asyncio.get_running_loop())
    except RuntimeError:
        return None


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker, _engine_loop_id
    loop_id = _current_loop_id()
    if _engine is not None and loop_id is not None and _engine_loop_id not in (None, loop_id):
        logger.info("[db] event loop changed; recreating the PostgreSQL engine")
        _engine = None
        _sessionmaker = None
    if _engine is None:
        url = database_url()
        if not url:
            raise RuntimeError("DATABASE_URL is not set")
        _engine = create_async_engine(
            url,
            pool_pre_ping=True,
            pool_size=int(os.getenv("KA11Y_DB_POOL_SIZE", "5")),
            max_overflow=int(os.getenv("KA11Y_DB_MAX_OVERFLOW", "5")),
            echo=os.getenv("KA11Y_DB_ECHO", "0") == "1",
        )
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
        _engine_loop_id = loop_id
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """``async with session_scope() as s:`` — commits on success, rolls back on error."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


async def ping() -> bool:
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        logger.warning("[db] PostgreSQL ping failed", exc_info=True)
        return False


async def dispose() -> None:
    """Close the pool. Only awaited when the engine belongs to the running
    loop — disposing connections that were opened on another (possibly
    closed) loop never returns, so those are simply dropped."""
    global _engine, _sessionmaker, _engine_loop_id
    engine, loop_id = _engine, _engine_loop_id
    _engine = None
    _sessionmaker = None
    _engine_loop_id = None
    if engine is None:
        return
    if loop_id in (None, _current_loop_id()):
        await engine.dispose()
    else:
        logger.info("[db] engine belongs to another event loop; dropping without dispose")
