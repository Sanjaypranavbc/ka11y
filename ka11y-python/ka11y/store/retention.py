"""
ka11y/store/retention.py
=======================
Durable-store retention sweep (P1). Replaces the in-memory TTL eviction's role
for the DB: periodically delete runs older than ``KA11Y_RUN_RETENTION_DAYS``
(default 30) and prune their on-disk assets. ON DELETE CASCADE removes child
rows (findings, reports, pages, assets metadata); we delete the asset *files*
ourselves.

Runs as a background task started from the FastAPI lifespan. Never raises.
"""

from __future__ import annotations

import asyncio
import os

from ka11y.config.logger import setup_logger
from ka11y.store import repo
from ka11y.store.assets import prune_run_assets

logger = setup_logger(name="KAC", tag="store.retention")

_SWEEP_INTERVAL_SECONDS = int(os.getenv("KA11Y_RETENTION_SWEEP_SECONDS", "3600"))


async def run_retention_loop() -> None:
    retention_days = int(os.getenv("KA11Y_RUN_RETENTION_DAYS", "30"))
    while True:
        try:
            await asyncio.sleep(_SWEEP_INTERVAL_SECONDS)
            removed = await repo.retention_sweep(retention_days)
            for run_id in removed:
                await asyncio.to_thread(prune_run_assets, run_id)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.warning("[store] retention sweep failed", exc_info=True)
