"""
ka11y/i18n/loader.py
====================
Loads WCAG rules from the shared i18n/rules.yml and optional locale
overlay files (i18n/locales/<lang>.yml).

Non-translatable fields (level, severity) always come from rules.yml.
Translatable fields (name, description, suggested_fix) are overridden
by the locale file when the translated value is present and non-empty.

Results are cached per language after the first load.
"""

from __future__ import annotations

import logging
import os
from pydantic import BaseModel, ConfigDict
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

import yaml

logger = logging.getLogger(__name__)

# Allow Docker override via env var.
# Prefer the repo-shared i18n directory, then fall back to the service-local copy.
_REPO_ROOT = Path(__file__).parents[3]
_SHARED_I18N_DIR = _REPO_ROOT / "i18n"
_LOCAL_I18N_DIR = Path(__file__).parents[2] / "i18n"
_DEFAULT_I18N_DIR = _SHARED_I18N_DIR if _SHARED_I18N_DIR.exists() else _LOCAL_I18N_DIR
I18N_DIR = Path(os.environ.get("KA11Y_I18N_DIR", str(_DEFAULT_I18N_DIR)))


class RuleEntry(BaseModel):
    """A single WCAG success criterion entry."""
    model_config = ConfigDict(frozen=True)
    id: str
    level: str                    # "A" | "AA" | "AAA"
    severity: Optional[str]       # "critical" | "high" | "medium" | "low" | None
    name: str
    description: str
    suggested_fix: str


def _load_yaml(path: Path) -> dict:
    """Load a YAML file safely; return {} if the file is missing or invalid."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return {}
    except yaml.YAMLError as exc:
        logger.warning("YAML parse error in %s: %s", path, exc)
        return {}


@lru_cache(maxsize=16)
def _load_rules_cached(lang: str) -> Dict[str, RuleEntry]:
    """
    Internal cached loader. Returns {sc_id: RuleEntry} for the given language.
    Falls back to English for any missing or blank translations.
    """
    base_path = I18N_DIR / "rules.yml"
    base_data = _load_yaml(base_path)
    base_rules: dict = base_data.get("rules", {})

    if lang == "en":
        return _build_entries(base_rules, {})

    locale_path = I18N_DIR / "locales" / f"{lang}.yml"
    locale_data = _load_yaml(locale_path)
    locale_rules: dict = locale_data.get("rules", {})

    return _build_entries(base_rules, locale_rules)


def _build_entries(
    base_rules: dict,
    locale_rules: dict,
) -> Dict[str, RuleEntry]:
    """Merge base + locale dicts into {sc_id: RuleEntry}."""
    result: Dict[str, RuleEntry] = {}
    for sc_id, base in base_rules.items():
        override = locale_rules.get(sc_id, {}) or {}
        result[sc_id] = RuleEntry(
            id=sc_id,
            level=base.get("level", "A"),
            severity=base.get("severity"),  # never localised
            name=_pick(override.get("name"), base.get("name", "")),
            description=_pick(override.get("description"), base.get("description", "")),
            suggested_fix=_pick(override.get("suggested_fix"), base.get("suggested_fix", "")),
        )
    return result


def _pick(override: Optional[str], fallback: str) -> str:
    """Return *override* if it is non-empty, otherwise *fallback*."""
    if override and str(override).strip():
        return str(override).strip()
    return fallback or ""


def load_rules(lang: str = "en") -> Dict[str, RuleEntry]:
    """
    Public API — returns a {sc_id: RuleEntry} mapping for the requested language.
    Caches on first call per language.  Falls back to English for missing entries.

    Example::

        rules = load_rules("en")
        print(rules["1.1.1"].name)          # "Non-text Content"
        print(rules["1.1.1"].suggested_fix)  # "Add a descriptive alt attribute..."
    """
    # Sanitise lang to prevent path traversal
    safe_lang = "".join(c for c in lang if c.isalpha() or c == "-")[:10] or "en"
    return _load_rules_cached(safe_lang)


# ---------------------------------------------------------------------------
# Convenience dict-like accessors — same interface as the old constants.py
# ---------------------------------------------------------------------------

def get_wcag_names(lang: str = "en") -> Dict[str, str]:
    """Return {sc_id: name} for the given language."""
    return {sc_id: r.name for sc_id, r in load_rules(lang).items()}


def get_wcag_levels() -> Dict[str, str]:
    """Return {sc_id: level}.  Level is not localised, so no lang param."""
    return {sc_id: r.level for sc_id, r in load_rules("en").items()}


def get_suggested_fixes(lang: str = "en") -> Dict[str, str]:
    """Return {sc_id: suggested_fix} for the given language."""
    return {sc_id: r.suggested_fix for sc_id, r in load_rules(lang).items()}


def get_severities() -> Dict[str, str]:
    """Return {sc_id: severity} for rules that have a severity set."""
    return {
        sc_id: r.severity
        for sc_id, r in load_rules("en").items()
        if r.severity is not None
    }
