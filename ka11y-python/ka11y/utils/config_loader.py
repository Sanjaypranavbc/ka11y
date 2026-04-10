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


def load_config(config_path: str | None = None):
    if config_path is None:
        config_path = Path(__file__).resolve().parents[1] / "config" / "config.yml"
    else:
        config_path = Path(config_path)

    # Return a defensive copy so callers can tweak nested values in-memory
    # without mutating the cached shared config instance.
    return copy.deepcopy(_load_config_cached(str(config_path.resolve())))


config = load_config()
