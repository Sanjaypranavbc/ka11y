# bc_rag/core/logger.py
from rich.console import Console
from rich.logging import RichHandler

import logging
import sys
import os
import yaml
import datetime
from logging.handlers import RotatingFileHandler


def setup_logger(name="KAC", level=logging.INFO, tag=None):
    BASE_DIR = "."
    log_dir = os.path.join(BASE_DIR, "logs")

    # 🔹 ALWAYS ensure log directory exists
    os.makedirs(log_dir, exist_ok=True)
    base_logger = logging.getLogger(name)

    if not base_logger.handlers:

        base_logger.setLevel(level)
        base_logger.propagate = False

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)

        # File handler
        date = datetime.datetime.now().strftime("%d-%m-%Y")
        log_filename = os.path.join(log_dir, f"{name}_{date}.log")

        file_handler = RotatingFileHandler(
            log_filename,
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(level)

        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - [%(tag)s] - %(levelname)s - %(message)s"
        )

        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)

        base_logger.addHandler(console_handler)
        base_logger.addHandler(file_handler)

    # 🔹 Always return adapter
    return logging.LoggerAdapter(base_logger, {"tag": tag or "GENERAL"})


# Helper functions for styled logging
def log_info(logger, message):
    """Log information message."""
    logger.info(message)


def log_warning(logger, message):
    """Log warning message."""
    logger.warning(message)


def log_error(logger, message):
    """Log error message."""
    logger.error(message)


def log_debug(logger, message):
    """Log debug message."""
    logger.debug(message)


def log_success(logger, message):
    """Log success message."""
    logger.info(message)


def log_processing(logger, message):
    """Log processing status."""
    logger.info(message)
