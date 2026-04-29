"""
ka11y/i18n/loader.py
====================
Loads WCAG rules from the shared i18n/rules.yml and optional locale
overlay files (i18n/locales/<lang>.yml).

Stable machine fields (level, severity, status) always come from
rules.yml — clients filter on these and they must be identical across
languages.

Translatable fields are overridden per locale:
  - name, description, suggested_fix   (per rule)
  - reason_templates.<rule>.<code>      (per rule)
  - severities.<key>                    (display label for a severity)
  - levels.<key>                        (display label for a WCAG level)
  - statuses.<key>                      (display label for a finding status)

Results are cached per language after the first load.
"""

from __future__ import annotations

import logging
import os
import re
from pydantic import BaseModel, ConfigDict
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

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
    reason_templates: Mapping[str, str] = {}


class LocaleBundle(BaseModel):
    """Localized labels + per-rule entries for one language."""
    model_config = ConfigDict(frozen=True)
    lang: str
    rules: Mapping[str, RuleEntry]
    severities: Mapping[str, str]
    levels: Mapping[str, str]
    statuses: Mapping[str, str]


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


_DEFAULT_SEVERITY_LABELS_EN = {
    "critical": "Critical",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
    "none": "None",
}

_DEFAULT_LEVEL_LABELS_EN = {
    "A": "Level A",
    "AA": "Level AA",
    "AAA": "Level AAA",
}

_DEFAULT_STATUS_LABELS_EN = {
    "pass": "Pass",
    "fail": "Fail",
    "needs_review": "Needs Review",
    "inapplicable": "Not Applicable",
}


@lru_cache(maxsize=16)
def _load_bundle_cached(lang: str) -> LocaleBundle:
    """Cached per-language loader returning a complete LocaleBundle."""
    base_path = I18N_DIR / "rules.yml"
    base_data = _load_yaml(base_path)
    base_rules: dict = base_data.get("rules", {}) or {}
    base_severities: dict = base_data.get("severities", {}) or {}
    base_levels: dict = base_data.get("levels", {}) or {}
    base_statuses: dict = base_data.get("statuses", {}) or {}
    base_templates_top: dict = base_data.get("reason_templates", {}) or {}

    if lang == "en":
        locale_data: dict = {}
    else:
        locale_path = I18N_DIR / "locales" / f"{lang}.yml"
        locale_data = _load_yaml(locale_path)

    locale_rules: dict = locale_data.get("rules", {}) or {}
    locale_severities: dict = locale_data.get("severities", {}) or {}
    locale_levels: dict = locale_data.get("levels", {}) or {}
    locale_statuses: dict = locale_data.get("statuses", {}) or {}
    locale_templates_top: dict = locale_data.get("reason_templates", {}) or {}

    rules = _build_entries(
        base_rules,
        locale_rules,
        base_templates_top,
        locale_templates_top,
    )
    severities = _merge_label_map(_DEFAULT_SEVERITY_LABELS_EN, base_severities, locale_severities)
    levels = _merge_label_map(_DEFAULT_LEVEL_LABELS_EN, base_levels, locale_levels)
    statuses = _merge_label_map(_DEFAULT_STATUS_LABELS_EN, base_statuses, locale_statuses)

    return LocaleBundle(
        lang=lang,
        rules=rules,
        severities=severities,
        levels=levels,
        statuses=statuses,
    )


def _merge_label_map(
    fallback_en: Dict[str, str],
    base: Dict[str, Any],
    override: Dict[str, Any],
) -> Dict[str, str]:
    """Merge default English labels with rules.yml + locale overrides."""
    out: Dict[str, str] = {}
    keys = set(fallback_en) | set(base or {}) | set(override or {})
    for key in keys:
        out[str(key)] = _pick(
            (override or {}).get(key),
            _pick((base or {}).get(key), fallback_en.get(key, str(key))),
        )
    return out


def _build_entries(
    base_rules: dict,
    locale_rules: dict,
    base_templates_top: Optional[dict] = None,
    locale_templates_top: Optional[dict] = None,
) -> Dict[str, RuleEntry]:
    """Merge base + locale dicts into {sc_id: RuleEntry}.

    Reason templates may live either nested under each rule (`rules.X.reason_templates`)
    or under a top-level `reason_templates: { X: {...} }` block — entries from both
    sources are merged, with the top-level block taking precedence over the nested form
    when both define the same code.
    """
    base_templates_top = base_templates_top or {}
    locale_templates_top = locale_templates_top or {}

    # Include synthetic SC IDs (e.g. "_generic") that exist only in
    # reason_templates so callers can render shared catch-all messages.
    synthetic_ids = (set(base_templates_top) | set(locale_templates_top)) - set(base_rules)

    result: Dict[str, RuleEntry] = {}
    iter_ids = list(base_rules.keys()) + sorted(synthetic_ids)
    for sc_id in iter_ids:
        base = base_rules.get(sc_id, {}) or {}
        override = locale_rules.get(sc_id, {}) or {}

        nested_base_templates = base.get("reason_templates", {}) or {}
        nested_override_templates = override.get("reason_templates", {}) or {}
        top_base_templates = base_templates_top.get(sc_id, {}) or {}
        top_override_templates = locale_templates_top.get(sc_id, {}) or {}

        merged_templates: Dict[str, str] = {}
        all_keys = (
            set(nested_base_templates)
            | set(nested_override_templates)
            | set(top_base_templates)
            | set(top_override_templates)
        )
        for key in all_keys:
            merged_templates[str(key)] = _pick(
                top_override_templates.get(key),
                _pick(
                    nested_override_templates.get(key),
                    _pick(
                        top_base_templates.get(key),
                        nested_base_templates.get(key, ""),
                    ),
                ),
            )
        result[sc_id] = RuleEntry(
            id=sc_id,
            level=base.get("level", "A"),
            severity=base.get("severity"),  # never localised — stable enum
            name=_pick(override.get("name"), base.get("name", "")),
            description=_pick(override.get("description"), base.get("description", "")),
            suggested_fix=_pick(override.get("suggested_fix"), base.get("suggested_fix", "")),
            reason_templates=merged_templates,
        )
    return result


def _pick(override: Optional[Any], fallback: Any) -> str:
    """Return *override* if it is a non-empty string, otherwise *fallback*."""
    if override is not None and str(override).strip():
        return str(override).strip()
    if fallback is None:
        return ""
    return str(fallback).strip()


def _safe_lang(lang: Optional[str]) -> str:
    """Sanitise lang to prevent path traversal and unify casing."""
    safe_lang = re.sub(r"[^a-zA-Z\-]", "", str(lang or "en"))[:10].strip("-") or "en"
    return safe_lang


def load_bundle(lang: str = "en") -> LocaleBundle:
    """Return the full LocaleBundle for the requested language."""
    return _load_bundle_cached(_safe_lang(lang))


def load_rules(lang: str = "en") -> Dict[str, RuleEntry]:
    """
    Public API — returns a {sc_id: RuleEntry} mapping for the requested language.
    Caches on first call per language.  Falls back to English for missing entries.
    """
    return dict(load_bundle(lang).rules)


# ---------------------------------------------------------------------------
# Convenience dict-like accessors
# ---------------------------------------------------------------------------

def get_wcag_names(lang: str = "en") -> Dict[str, str]:
    """Return {sc_id: name} for the given language."""
    return {sc_id: r.name for sc_id, r in load_rules(lang).items()}


def get_wcag_levels() -> Dict[str, str]:
    """Return {sc_id: level}.  Level value is not localised."""
    return {sc_id: r.level for sc_id, r in load_rules("en").items()}


def get_suggested_fixes(lang: str = "en") -> Dict[str, str]:
    """Return {sc_id: suggested_fix} for the given language."""
    return {sc_id: r.suggested_fix for sc_id, r in load_rules(lang).items()}


def get_severities() -> Dict[str, str]:
    """Return {sc_id: severity} for rules that have a severity set.
    The value is the stable machine enum (critical/high/medium/low)."""
    return {
        sc_id: r.severity
        for sc_id, r in load_rules("en").items()
        if r.severity is not None
    }


def get_severity_labels(lang: str = "en") -> Dict[str, str]:
    """Return {severity_value: localized_label}, e.g. {"critical": "重大", ...}."""
    return dict(load_bundle(lang).severities)


def get_level_labels(lang: str = "en") -> Dict[str, str]:
    """Return {level_value: localized_label}, e.g. {"AA": "レベル AA"}."""
    return dict(load_bundle(lang).levels)


def get_status_labels(lang: str = "en") -> Dict[str, str]:
    """Return {status_value: localized_label}, e.g. {"pass": "合格"}."""
    return dict(load_bundle(lang).statuses)


def get_severity_label(value: Optional[str], lang: str = "en") -> Optional[str]:
    """Localized label for a single severity value. Returns None for None input."""
    if value is None:
        return None
    return load_bundle(lang).severities.get(str(value), str(value))


def get_level_label(value: Optional[str], lang: str = "en") -> Optional[str]:
    """Localized label for a single WCAG level value."""
    if value is None:
        return None
    return load_bundle(lang).levels.get(str(value), str(value))


def get_status_label(value: Optional[str], lang: str = "en") -> Optional[str]:
    """Localized label for a single status value."""
    if value is None:
        return None
    return load_bundle(lang).statuses.get(str(value), str(value))


def render_reason(
    sc: str,
    code: str,
    lang: str = "en",
    fallback: str = "",
    params: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Render a localized reason string from `reason_templates` in i18n YAML.

    `params` is a dict of placeholder values; we deliberately pass it as a
    dict (rather than **kwargs) so callers can use placeholder names that
    happen to collide with this function's own positional names — e.g.
    {wcag_sc} in the _generic templates.

    Missing placeholders render as empty rather than raising KeyError.

    Example:
        render_reason("1.1.1", "fail_missing_alt", lang="ja",
                      params={"src": "logo.png"})
    """
    params = dict(params or {})
    # Inject a default {wcag_sc} so the _generic templates render usefully
    # even when callers don't pass one explicitly.
    params.setdefault("wcag_sc", str(sc))
    bundle = load_bundle(lang)
    rule = bundle.rules.get(str(sc))
    template = (rule.reason_templates.get(str(code)) if rule else None) or ""

    if not template:
        # Fall back to English if the locale has no override for this code
        if lang != "en":
            en_rule = load_bundle("en").rules.get(str(sc))
            template = (en_rule.reason_templates.get(str(code)) if en_rule else "") or ""

    if not template:
        # Fall back to the shared `_generic` block so every SC participates in
        # localization even when it doesn't define its own templates.
        generic = bundle.rules.get("_generic")
        template = (generic.reason_templates.get(str(code)) if generic else None) or ""
        if not template and lang != "en":
            en_generic = load_bundle("en").rules.get("_generic")
            template = (en_generic.reason_templates.get(str(code)) if en_generic else "") or ""

    if not template:
        return fallback

    try:
        return template.format_map(_SafeDict(params))
    except Exception as exc:  # noqa: BLE001
        logger.warning("reason template format failed (%s/%s): %s", sc, code, exc)
        return fallback or template


class _SafeDict(dict):
    """Dict that returns an empty string for missing format keys."""

    def __missing__(self, key: str) -> str:  # noqa: D401
        return ""
