"""
ka11y/store/db.py
=================
SQLite (WAL) persistence with a single serialized writer.

Why a single writer thread
--------------------------
SQLite permits many concurrent readers but only one writer. Under the audit
workload several coroutines (runner, stage timers, asset registrar) want to
write at once. Rather than sprinkle ``busy_timeout`` retries everywhere, all
writes are funnelled through ONE background thread owning ONE connection and
fed by a ``queue.Queue``. That makes every write serialized and lock-free from
the caller's perspective:

    await db.execute("INSERT ...", params)     # awaits the writer thread
    db.enqueue("INSERT ...", params)           # fire-and-forget (telemetry)
    await db.run_write(lambda c: ...)          # multi-statement atomic txn
    rows = await db.query("SELECT ...", params)# concurrent reader (WAL)

Reads run in the default asyncio thread pool against short-lived, thread-local
connections; WAL means they never block the writer and the writer never blocks
them.

Nothing here is allowed to take down the event loop: ``enqueue`` never blocks,
and ``execute``/``run_write`` resolve a ``concurrent.futures.Future`` that the
writer thread completes.
"""

from __future__ import annotations

import asyncio
import os
import queue
import sqlite3
import threading
from concurrent.futures import Future
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="store.db")

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

# Sentinel pushed onto the write queue to stop the writer thread.
_SHUTDOWN = object()


def _default_db_path() -> str:
    override = os.getenv("KA11Y_DB_PATH")
    if override:
        return override
    # Default lives next to the rotating app logs so a single mounted volume
    # (logs/) captures both. Compose can override with KA11Y_DB_PATH=/data/...
    log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    return str(log_dir / "ka11y.db")


class _WriteItem:
    __slots__ = ("fn", "future")

    def __init__(self, fn: Callable[[sqlite3.Connection], Any], future: Optional[Future]):
        self.fn = fn
        self.future = future


class Database:
    """Single-writer SQLite wrapper. Use the module-level :func:`get_db`."""

    def __init__(self, path: Optional[str] = None) -> None:
        self._path = path or _default_db_path()
        self._write_q: "queue.Queue[Any]" = queue.Queue()
        self._writer: Optional[threading.Thread] = None
        self._tls = threading.local()
        self._started = threading.Event()
        self._start_lock = threading.Lock()

    # ── lifecycle ───────────────────────────────────────────────────────────

    @property
    def path(self) -> str:
        return self._path

    def start(self) -> None:
        """Idempotently open the DB, run migrations, and launch the writer."""
        with self._start_lock:
            if self._started.is_set():
                return
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
            # Run migrations on a throwaway connection before the writer starts
            # so a migration failure surfaces synchronously at startup.
            self._migrate()
            self._writer = threading.Thread(
                target=self._writer_loop, name="ka11y-db-writer", daemon=True
            )
            self._writer.start()
            self._started.set()
            logger.info("[store] SQLite ready at %s (WAL)", self._path)

    def stop(self) -> None:
        if not self._started.is_set():
            return
        self._write_q.put(_SHUTDOWN)
        if self._writer is not None:
            self._writer.join(timeout=10)
        self._started.clear()

    # ── connection helpers ──────────────────────────────────────────────────

    def _configure(self, conn: sqlite3.Connection) -> None:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=30, check_same_thread=False)
        self._configure(conn)
        return conn

    def _read_conn(self) -> sqlite3.Connection:
        """Thread-local read connection (WAL → readers never block writer)."""
        conn = getattr(self._tls, "conn", None)
        if conn is None:
            conn = self._open()
            self._tls.conn = conn
        return conn

    # ── migrations ──────────────────────────────────────────────────────────

    def _migrate(self) -> None:
        conn = self._open()
        try:
            self._configure(conn)
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "  version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            applied = {
                r[0] for r in conn.execute("SELECT version FROM schema_migrations")
            }
            files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
            for f in files:
                version = f.stem
                if version in applied:
                    continue
                logger.info("[store] applying migration %s", version)
                conn.executescript(f.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO schema_migrations(version, applied_at) "
                    "VALUES (?, datetime('now'))",
                    (version,),
                )
                conn.commit()
        finally:
            conn.close()

    # ── writer thread ───────────────────────────────────────────────────────

    def _writer_loop(self) -> None:
        conn = self._open()
        try:
            while True:
                item = self._write_q.get()
                if item is _SHUTDOWN:
                    break
                assert isinstance(item, _WriteItem)
                try:
                    result = item.fn(conn)
                    conn.commit()
                    if item.future is not None and not item.future.done():
                        item.future.set_result(result)
                except Exception as exc:  # noqa: BLE001
                    try:
                        conn.rollback()
                    except Exception:  # noqa: BLE001
                        pass
                    if item.future is not None and not item.future.done():
                        item.future.set_exception(exc)
                    else:
                        # Fire-and-forget write failed; log but keep serving.
                        logger.warning("[store] write failed: %s", exc, exc_info=True)
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    def _submit(self, fn: Callable[[sqlite3.Connection], Any]) -> Future:
        fut: Future = Future()
        self._write_q.put(_WriteItem(fn, fut))
        return fut

    # ── public async API ────────────────────────────────────────────────────

    async def execute(self, sql: str, params: Sequence[Any] = ()) -> Optional[int]:
        """Run one write statement; return ``lastrowid``."""

        def _fn(conn: sqlite3.Connection) -> Optional[int]:
            cur = conn.execute(sql, params)
            return cur.lastrowid

        return await asyncio.wrap_future(self._submit(_fn))

    async def executemany(self, sql: str, seq_params: Sequence[Sequence[Any]]) -> None:
        def _fn(conn: sqlite3.Connection) -> None:
            conn.executemany(sql, seq_params)

        await asyncio.wrap_future(self._submit(_fn))

    async def run_write(self, fn: Callable[[sqlite3.Connection], Any]) -> Any:
        """Run a multi-statement function atomically on the writer connection."""
        return await asyncio.wrap_future(self._submit(fn))

    def enqueue(self, sql: str, params: Sequence[Any] = ()) -> None:
        """Fire-and-forget write — never blocks, never raises to the caller.

        Used by telemetry sinks that must not stall or fail an audit. Failures
        are logged by the writer loop.
        """
        if not self._started.is_set():
            return

        def _fn(conn: sqlite3.Connection) -> None:
            conn.execute(sql, params)

        self._write_q.put(_WriteItem(_fn, None))

    def enqueue_fn(self, fn: Callable[[sqlite3.Connection], Any]) -> None:
        """Fire-and-forget multi-statement write (telemetry batches)."""
        if not self._started.is_set():
            return
        self._write_q.put(_WriteItem(fn, None))

    async def query(self, sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
        def _q() -> List[Dict[str, Any]]:
            cur = self._read_conn().execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

        return await asyncio.to_thread(_q)

    async def query_one(
        self, sql: str, params: Sequence[Any] = ()
    ) -> Optional[Dict[str, Any]]:
        rows = await self.query(sql, params)
        return rows[0] if rows else None


# ── module singleton ─────────────────────────────────────────────────────────

_db: Optional[Database] = None
_db_lock = threading.Lock()


def get_db() -> Database:
    """Return the process-wide :class:`Database`, creating+starting it lazily."""
    global _db
    if _db is None:
        with _db_lock:
            if _db is None:
                _db = Database()
                _db.start()
    return _db


def init_db(path: Optional[str] = None) -> Database:
    """Explicitly initialise the DB (called from FastAPI lifespan startup)."""
    global _db
    with _db_lock:
        if _db is None:
            _db = Database(path)
            _db.start()
    return _db


def shutdown_db() -> None:
    global _db
    if _db is not None:
        _db.stop()
        _db = None
