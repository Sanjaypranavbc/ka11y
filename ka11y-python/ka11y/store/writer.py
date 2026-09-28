"""
ka11y/store/writer.py
=====================
Fire-and-forget row writer for telemetry (``stage_timings``) and lifecycle
events (``audit_logs``) that are emitted from *anywhere*: the event loop,
auditor threads, the crawler's timing logger.

Why a thread and not ``asyncio.create_task``
--------------------------------------------
The emitters are synchronous functions that may run in worker threads with
no event loop at hand, and the rows must land in the order they were
produced (``get_events`` and the admin log order by id). One daemon thread
owning one *synchronous* SQLAlchemy connection, fed by a thread-safe queue,
gives both without touching the async engine's pool: ``enqueue`` never
blocks and never raises to the caller, exactly the contract the old SQLite
single-writer thread had. Each row is its own transaction so a rejected one
(an event for a job id that was never persisted → FK violation) cannot take
its neighbours down.
"""

from __future__ import annotations

import os
import queue
import threading
from typing import Any, Dict, Optional

from sqlalchemy import insert

from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="store.writer")

_SHUTDOWN = object()


class _Writer:
    def __init__(self) -> None:
        self._q: "queue.Queue[Any]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._started = threading.Event()
        self._lock = threading.Lock()
        self._engine = None

    # ── lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Idempotent. Returns False when DATABASE_URL is unset (nothing to write to)."""
        from ka11y.db.engine import database_url

        with self._lock:
            if self._started.is_set():
                return True
            url = database_url()
            if not url:
                return False
            from sqlalchemy import create_engine

            self._engine = create_engine(
                url,
                pool_size=1,
                max_overflow=0,
                pool_pre_ping=True,
                echo=os.getenv("KA11Y_DB_ECHO", "0") == "1",
            )
            self._thread = threading.Thread(target=self._loop, name="ka11y-store-writer", daemon=True)
            self._thread.start()
            self._started.set()
            return True

    def stop(self, timeout: float = 10.0) -> None:
        with self._lock:
            if not self._started.is_set():
                return
            self._q.put(_SHUTDOWN)
            if self._thread is not None:
                self._thread.join(timeout=timeout)
            self._thread = None
            self._started.clear()
            engine, self._engine = self._engine, None
        if engine is not None:
            try:
                engine.dispose()
            except Exception:  # noqa: BLE001
                pass

    def flush(self, timeout: Optional[float] = None) -> None:
        """Block until every queued row has been attempted (tests)."""
        if not self._started.is_set():
            return
        if timeout is None:
            self._q.join()
            return
        done = threading.Event()

        def _mark() -> None:
            self._q.join()
            done.set()

        threading.Thread(target=_mark, daemon=True).start()
        done.wait(timeout)

    # ── producer side ────────────────────────────────────────────────────────

    def enqueue(self, table: Any, row: Dict[str, Any]) -> None:
        """Queue one INSERT. Never blocks, never raises."""
        try:
            if not self._started.is_set() and not self.start():
                return
            self._q.put((table, row))
        except Exception:  # noqa: BLE001
            pass

    # ── consumer side ────────────────────────────────────────────────────────

    def _loop(self) -> None:
        while True:
            item = self._q.get()
            try:
                if item is _SHUTDOWN:
                    return
                table, row = item
                try:
                    with self._engine.begin() as conn:  # type: ignore[union-attr]
                        conn.execute(insert(table).values(**row))
                except Exception as exc:  # noqa: BLE001
                    # Typically an FK violation: a timing/event for a job id
                    # that was never persisted (CLI runs, tests). Telemetry
                    # must never be louder than the audit it describes.
                    logger.debug("[store.writer] row dropped for %s: %s", getattr(table, "__tablename__", table), exc)
            finally:
                self._q.task_done()


_writer = _Writer()


def start() -> bool:
    return _writer.start()


def stop() -> None:
    _writer.stop()


def flush(timeout: Optional[float] = None) -> None:
    _writer.flush(timeout)


def enqueue(table: Any, row: Dict[str, Any]) -> None:
    _writer.enqueue(table, row)
