from __future__ import annotations

import copy
from functools import lru_cache
from pathlib import Path

import yaml


@lru_cache(maxsize=4)
def _load_config_cached(config_path: str) -> dict:
    path = Path(config_path)
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


# The one runtime configuration file. It used to be shadowed by a
# <repo>/config/universal.yml that only existed on developer machines (the
# Docker image copies ka11y/ alone), so local runs and production read
# different files; that second file was removed on 2026-09-27.
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "config.yml"


def load_config(config_path: str | None = None) -> dict:
    config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

    # Return a defensive copy so callers can tweak nested values in-memory
    # without mutating the cached shared config instance.
    return copy.deepcopy(_load_config_cached(str(config_path.resolve())))


config = load_config()
