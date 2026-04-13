from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence

from ka11y.utils.config_loader import load_config


def _get_nested(config: dict[str, Any], path: Sequence[str], default: Any) -> Any:
    current: Any = config
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def get_config_value(*path: str, default: Any = None) -> Any:
    config = load_config()
    return _get_nested(config, path, default)


def get_int_config(*path: str, default: int, minimum: int | None = None) -> int:
    value = get_config_value(*path, default=default)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None:
        return max(parsed, minimum)
    return parsed


def get_cjk_langs() -> list[str]:
    raw = get_config_value(
        "crawler",
        "language",
        "cjk_langs",
        default=["ja", "zh", "zh-CN", "zh-TW", "zh-HK", "ko"],
    )
    if not isinstance(raw, list):
        return ["ja", "zh", "zh-CN", "zh-TW", "zh-HK", "ko"]
    langs = [str(item).strip() for item in raw if str(item).strip()]
    return langs or ["ja", "zh", "zh-CN", "zh-TW", "zh-HK", "ko"]


def get_check_config_value(check_key: str, *path: str, default: Any = None) -> Any:
    return get_config_value("checks", check_key, *path, default=default)


def get_localized_check_terms(check_key: str, term_key: str) -> list[str]:
    raw = get_check_config_value(check_key, term_key, default=[])
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if not isinstance(raw, dict):
        return []

    terms: list[str] = []
    for values in raw.values():
        if isinstance(values, list):
            terms.extend(str(item).strip() for item in values if str(item).strip())
    return list(dict.fromkeys(terms))


def get_max_warning_samples() -> int:
    return get_int_config(
        "crawler",
        "reporting",
        "max_warning_samples",
        default=3,
        minimum=1,
    )


def get_max_focus_steps() -> int:
    return get_int_config(
        "crawler",
        "performance",
        "max_focus_steps",
        default=100,
        minimum=10,
    )


def get_max_hover_candidates() -> int:
    return get_int_config(
        "crawler",
        "performance",
        "max_hover_candidates",
        default=20,
        minimum=1,
    )


def get_max_ocr_images_per_run() -> int:
    return get_int_config(
        "crawler",
        "performance",
        "max_ocr_images_per_run",
        default=60,
        minimum=1,
    )


def build_text_spacing_cjk_selector_css() -> str:
    selectors = []
    descendant_selectors = []
    for lang in get_cjk_langs():
        selectors.extend([f":lang({lang})", f'[lang="{lang}"]'])
        descendant_selectors.extend([f":lang({lang}) *", f'[lang="{lang}"] *'])

    top_level = ", ".join(selectors)
    descendants = ", ".join(descendant_selectors)
    return (
        "/* CJK languages: letter-spacing and word-spacing WCAG overrides do not apply.\n"
        "   These languages have built-in inter-character spacing and no word separators,\n"
        "   so only line-height override remains enabled. */\n"
        f"{top_level} {{\n"
        "    letter-spacing: normal !important;\n"
        "    word-spacing: normal !important;\n"
        "}\n"
        f"{descendants} {{\n"
        "    letter-spacing: normal !important;\n"
        "    word-spacing: normal !important;\n"
        "}\n"
    )


def select_ocr_candidate_paths(
    images: Iterable[Any],
    *,
    limit: int,
) -> tuple[list[str], list[str]]:
    ranked: list[tuple[tuple[int, int, str], str]] = []
    seen: set[str] = set()

    for index, item in enumerate(images):
        path = str(getattr(item, "screenshot_path", "") or "").strip()
        if not path:
            continue
        resolved = str(Path(path).resolve())
        if resolved in seen:
            continue
        seen.add(resolved)

        classification = str(getattr(item, "classification", "") or "").strip().lower()
        sub_type = str(getattr(item, "sub_type", "") or "").strip().lower()
        is_button = bool(getattr(item, "is_button", False))
        is_text_image = bool(getattr(item, "is_text_image", False))
        is_complex = bool(getattr(item, "is_complex", False))
        is_decorative = bool(getattr(item, "is_decorative", False))
        is_logo = bool(getattr(item, "is_logo", False))

        if is_button or sub_type == "buttons":
            priority = 0
        elif is_text_image:
            priority = 1
        elif classification == "functional":
            priority = 2
        elif classification == "informative":
            priority = 3
        elif is_complex:
            priority = 4
        elif is_logo:
            priority = 5
        elif is_decorative:
            priority = 6
        else:
            priority = 7

        ranked.append(((priority, index, resolved), resolved))

    ranked.sort(key=lambda item: item[0])
    ordered = [path for _, path in ranked]

    if limit <= 0 or len(ordered) <= limit:
        return ordered, []
    return ordered[:limit], ordered[limit:]
