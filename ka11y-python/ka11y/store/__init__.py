"""
ka11y/store/
============
Persistence for audit runs — PostgreSQL only (``DATABASE_URL``), through the
async SQLAlchemy engine in ``ka11y/db``. The SQLite run store this package
used to be was removed on 2026-09-28: every run was being written twice, once
here and once as an ``audit_jobs`` ownership row, and the two drifted.

Modules
-------
repo.py      — the one run repository: queue row, lifecycle, report JSON,
               findings, pages, events, timings, ownership/history, report
               file pointers, manual verdicts, asset queries, retention.
assets.py    — content-addressed asset store (bytes on disk, index in
               ``audit_assets``).
writer.py    — fire-and-forget row writer (events, timings) from any thread.
retention.py — periodic sweep of old runs + their on-disk assets.
cpu_pool.py  — shared ProcessPoolExecutor for CPU-bound work (not storage).

Design invariants
-----------------
* Degrade, never fail. Persistence on the audit hot-path is wrapped so a DB
  error logs and is swallowed — an audit must never fail because the DB
  hiccuped. The one exception is ``repo.create_run``: the ``audit_jobs`` row
  *is* the queue, so its failure is raised and answered with a 503.
* One write per fact. Lifecycle transitions write the job row, the summary
  and the event-log row in one transaction; nothing is mirrored elsewhere.
* Not configured → inert. Without ``DATABASE_URL`` reads return nothing and
  writes are no-ops (with one warning), and submitting an audit is refused.
"""

from __future__ import annotations

from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="store")


def init_store() -> bool:
    """Start the fire-and-forget writer. Returns False when DATABASE_URL is unset."""
    from ka11y.store import writer

    ok = writer.start()
    if not ok:
        logger.error(
            "DATABASE_URL is not set: audit runs cannot be persisted or queued. "
            "Set it (ka11y-python/.env) — the SQLite run store no longer exists."
        )
    return ok


def shutdown_store() -> None:
    from ka11y.store import writer

    writer.stop()


__all__ = ["init_store", "shutdown_store"]
