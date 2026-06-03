"""
a11y/store/
============
Durable persistence layer for a11y (single-box SQLite, WAL).

Modules
-------
db.py       — Database singleton: WAL connection, single serialized writer
              thread, schema migrations, async read/write helpers.
repo.py     — high-level CRUD for runs / findings / reports / events / timings.
assets.py   — content-addressed asset store (bytes on disk, metadata in DB).
cpu_pool.py — shared ProcessPoolExecutor for CPU-bound auditors.

Design invariants
-----------------
* One writer.  All writes funnel through a single background thread owning one
  connection, so SQLite never raises "database is locked".
* Degrade, never fail.  Persistence on the audit hot-path is wrapped so a DB
  error logs and is swallowed — an audit must never fail because the DB hiccuped.
* SQLite-swappable.  All SQL is parameterized and lives here; a future Postgres
  move is mechanical.
"""

from __future__ import annotations

from .db import Database, get_db, init_db, shutdown_db

__all__ = ["Database", "get_db", "init_db", "shutdown_db"]
