"""ka11y/config/logger.py
======================
Rich-based structured logger.

Console output  — colored by level via RichHandler
File output     — plain rotating text logs (no markup)

Levels
------
  DEBUG    →  dim cyan
  INFO     →  bold green
  SUCCESS  →  bold bright_green   (custom level 25)
  WARNING  →  bold yellow
  ERROR    →  bold red
  CRITICAL →  bold white on red
"""
from __future__ import annotations

import datetime
import logging
import os
from logging.handlers import RotatingFileHandler

from rich.console import Console
from rich.highlighter import NullHighlighter
from rich.logging import RichHandler
from rich.theme import Theme

# ── Custom SUCCESS level ─────────────────────────────────────────────────────
SUCCESS_LEVEL: int = 25
if logging.getLevelName(SUCCESS_LEVEL) == f"Level {SUCCESS_LEVEL}":
    logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")

# ── Rich theme — one style per level name ───────────────────────────────────
_THEME = Theme(
    {
        "logging.level.debug":    "dim cyan",
        "logging.level.info":     "bold green",
        "logging.level.success":  "bold bright_green",
        "logging.level.warning":  "bold yellow",
        "logging.level.error":    "bold red",
        "logging.level.critical": "bold white on red",
        "log.time":               "dim white",
    }
)

_console = Console(theme=_THEME, stderr=False, highlight=False)

_FILE_FMT = logging.Formatter(
    "%(asctime)s | %(levelname)-8s | [%(tag)-14s] | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ── Logger adapter ───────────────────────────────────────────────────────────


class KaLogger(logging.LoggerAdapter):
    """
    LoggerAdapter that:
    - Prepends [TAG] to every console message
    - Exposes .success() and .processing() helpers
    """

    def process(self, msg: str, kwargs: dict) -> tuple[str, dict]:
        tag = self.extra.get("tag", "GENERAL")
        kwargs["extra"] = {**self.extra, **kwargs.get("extra", {})}
        return f"[bold cyan]\\[{tag}][/bold cyan] {msg}", kwargs

    def success(self, msg: str, *args, **kwargs) -> None:
        """Log at SUCCESS level (25 — between DEBUG and INFO)."""
        self.log(SUCCESS_LEVEL, f"✓ {msg}", *args, **kwargs)

    def processing(self, msg: str, *args, **kwargs) -> None:
        """Log an ongoing-work INFO message with a spinner prefix."""
        self.info(f"⚙  {msg}", *args, **kwargs)


# ── Factory ──────────────────────────────────────────────────────────────────


def setup_logger(name: str = "KAC", tag: str | None = None) -> KaLogger:
    """
    Return a KaLogger for *name*.

    Handlers are attached only once per underlying logger name so repeated
    calls to setup_logger() with the same *name* are safe.
    """
    log_dir = os.path.join(".", "logs")
    os.makedirs(log_dir, exist_ok=True)

    base = logging.getLogger(name)

    if not base.handlers:
        base.setLevel(logging.DEBUG)
        base.propagate = False

        # ── Console handler (Rich, colored) ──────────────────────────────────
        rich_handler = RichHandler(
            console=_console,
            level=logging.DEBUG,
            rich_tracebacks=True,
            tracebacks_show_locals=False,
            show_time=True,
            show_level=True,
            show_path=False,
            markup=True,
            highlighter=NullHighlighter(),
        )
        # Only the message column — Rich draws time/level/path itself
        rich_handler.setFormatter(logging.Formatter("%(message)s"))
        base.addHandler(rich_handler)

        # ── File handler (plain rotating text) ───────────────────────────────
        date = datetime.datetime.now().strftime("%Y-%m-%d")
        log_path = os.path.join(log_dir, f"{name}_{date}.log")
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(_FILE_FMT)
        base.addHandler(file_handler)

    return KaLogger(base, {"tag": tag or "GENERAL"})


# ── Convenience wrappers (kept for back-compat) ───────────────────────────────


def log_info(logger: KaLogger, message: str) -> None:
    logger.info(message)


def log_warning(logger: KaLogger, message: str) -> None:
    logger.warning(message)


def log_error(logger: KaLogger, message: str) -> None:
    logger.error(message)


def log_debug(logger: KaLogger, message: str) -> None:
    logger.debug(message)


def log_success(logger: KaLogger, message: str) -> None:
    logger.success(message)


def log_processing(logger: KaLogger, message: str) -> None:
    logger.processing(message)