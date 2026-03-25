from __future__ import annotations

from pathlib import Path

import yaml


def load_config(config_path: str | None = None):
    if config_path is None:
        config_path = Path(__file__).resolve().parents[1] / "config" / "config.yml"
    else:
        config_path = Path(config_path)

    with config_path.open("r", encoding="utf-8") as file:
        _config = yaml.safe_load(file)
    return _config


config = load_config()
