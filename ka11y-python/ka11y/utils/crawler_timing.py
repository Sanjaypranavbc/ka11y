"""
ka11y/utils/crawler_timing.py
=============================
Per-audit crawler timing table.

Each crawler invocation in the combined pipeline is wrapped with
:func:`time_crawler`, which appends one row to ``<output_dir>/crawler_timings.log``
recording how long that crawler took. The file is a fixed-width Markdown table
so it is readable both as plain text and rendered Markdown:

    | Crawler              | Scope                                              |  Pages | Duration (s) | Status   |
    |----------------------|----------------------------------------------------|--------|--------------|----------|
    | universal_snapshot   | https://www.kao.com/jp/                            |      4 |        18.21 | ok       |
    | image                | https://www.kao.com/jp/                            |      4 |        42.07 | ok       |
    | sensory              | https://www.kao.com/jp/                            |        |         3.94 | ok       |

Writes are guarded by a per-path lock because the stage coroutines run
concurrently (``asyncio.gather``) and several may finish at once.
"""

from __future__ import annotations

import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable, Optional

# Column widths (content only; borders/padding added in _format_row).
_W_CRAWLER = 20
_W_SCOPE = 50
_W_PAGES = 6
_W_DURATION = 12
_W_STATUS = 8

_HEADER = (
    f"| {'Crawler':<{_W_CRAWLER}} | {'Scope':<{_W_SCOPE}} | "
    f"{'Pages':>{_W_PAGES}} | {'Duration (s)':>{_W_DURATION}} | {'Status':<{_W_STATUS}} |\n"
    f"|{'-' * (_W_CRAWLER + 2)}|{'-' * (_W_SCOPE + 2)}|"
    f"{'-' * (_W_PAGES + 2)}|{'-' * (_W_DURATION + 2)}|{'-' * (_W_STATUS + 2)}|\n"
)

_DEFAULT_FILENAME = "crawler_timings.log"

# Per-path locks so concurrent stages don't interleave row writes.
_locks: dict[str, threading.Lock] = {}
_registry_lock = threading.Lock()


def _lock_for(path: str) -> threading.Lock:
    with _registry_lock:
        lock = _locks.get(path)
        if lock is None:
            lock = threading.Lock()
            _locks[path] = lock
        return lock


class CrawlerTimingLogger:
    """Appends crawler timing rows to a single per-audit table file."""

    def __init__(self, output_dir, filename: str = _DEFAULT_FILENAME) -> None:
        self.path = Path(output_dir) / filename
        with _lock_for(str(self.path)):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Write the header exactly once (first crawler to finish creates it).
            if not self.path.exists() or self.path.stat().st_size == 0:
                self.path.write_text(_HEADER, encoding="utf-8")

    def record(
        self,
        crawler: str,
        scope: str = "",
        duration_s: float = 0.0,
        status: str = "ok",
        pages: Optional[int] = None,
    ) -> None:
        scope = (scope or "").replace("\n", " ")
        if len(scope) > _W_SCOPE:
            scope = scope[: _W_SCOPE - 1] + "…"  # ellipsis
        pages_s = "" if pages is None else str(pages)
        row = (
            f"| {crawler:<{_W_CRAWLER}.{_W_CRAWLER}} | {scope:<{_W_SCOPE}.{_W_SCOPE}} | "
            f"{pages_s:>{_W_PAGES}} | {duration_s:>{_W_DURATION}.2f} | "
            f"{status:<{_W_STATUS}.{_W_STATUS}} |\n"
        )
        with _lock_for(str(self.path)):
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(row)


@asynccontextmanager
async def time_crawler(
    output_dir,
    crawler: str,
    scope: str = "",
    *,
    pages_getter: Optional[Callable[[], Optional[int]]] = None,
):
    """
    Time the wrapped crawler call and append a row to the timing table.

    Records ``status="error"`` (and re-raises) if the crawler raises, so a
    failing crawler still shows up in the table with its elapsed time.

    ``pages_getter`` is called after the crawl to report pages crawled (e.g.
    ``lambda: len(crawler.images_data)``); it is optional and any exception in
    it is swallowed so timing never breaks the audit.
    """
    timing = CrawlerTimingLogger(output_dir)
    start = time.perf_counter()
    status = "ok"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        duration = time.perf_counter() - start
        pages: Optional[int] = None
        if pages_getter is not None:
            try:
                pages = pages_getter()
            except Exception:
                pages = None
        timing.record(crawler, scope, duration, status, pages)
