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


def get_int_config(
    *path: str, default: int | None = None, minimum: int | None = None
) -> int | None:
    value = get_config_value(*path, default=default)
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
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


def get_max_ocr_images_per_run() -> int | None:
    return get_int_config(
        "crawler",
        "performance",
        "max_ocr_images_per_run",
        default=None,
        minimum=1,
    )


def get_max_ocr_images_per_page() -> int:
    """Per-page OCR budget for multi-page crawls. The total run budget scales as
    ``per_page * num_pages`` (capped by :func:`get_max_ocr_images_ceiling`), so a
    page audited as a child gets the same image coverage it would as the root —
    instead of competing with every sibling for one shared ``max_ocr_images_per_run``
    budget. Falls back to the legacy per-run value (or 60)."""
    per_page = get_int_config(
        "crawler", "performance", "max_ocr_images_per_page", default=None, minimum=1
    )
    if per_page:
        return per_page
    legacy = get_max_ocr_images_per_run()
    return legacy if legacy else 60


def get_max_ocr_images_ceiling() -> int:
    """Hard cap on total OCR images per run regardless of page count — bounds the
    cost of a deep crawl. Default 3000 (full 60/page coverage up to ~50 pages
    before the cap engages)."""
    ceiling = get_int_config(
        "crawler", "performance", "max_ocr_images_ceiling", default=None, minimum=1
    )
    return ceiling if ceiling else 3000


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
    fair_per_page: bool = False,
) -> tuple[list[str], list[str]]:
    """Rank screenshots and return ``(selected, skipped)`` within *limit*.

    ``fair_per_page`` (multi-page crawls): after global priority ranking, the
    budget is distributed round-robin across source pages so one page's images
    can't monopolise it and starve a sibling — the cross-page coverage gap that
    made a child page yield fewer findings than the same page audited alone.
    """
    ranked: list[tuple[tuple[int, int, str], str]] = []
    page_by_path: dict[str, str] = {}
    seen: set[str] = set()
    seen_asset_keys: set[str] = set()

    for index, item in enumerate(images):
        path = str(getattr(item, "screenshot_path", "") or "").strip()
        if not path:
            continue
        resolved = str(Path(path).resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        page_by_path[resolved] = str(getattr(item, "url", "") or "")

        classification = str(getattr(item, "classification", "") or "").strip().lower()
        sub_type = str(getattr(item, "sub_type", "") or "").strip().lower()
        is_button = bool(getattr(item, "is_button", False))
        is_text_image = bool(getattr(item, "is_text_image", False))
        is_complex = bool(getattr(item, "is_complex", False))
        is_decorative = bool(getattr(item, "is_decorative", False))
        is_logo = bool(getattr(item, "is_logo", False))
        src = str(getattr(item, "src", "") or "").strip()

        # Live-site bug fix: repeated decorative/logo assets often get screenshotted
        # multiple times on the same page (e.g. carousels, duplicated heroes, sticky
        # headers). OCRing every duplicate burns most of the image-audit budget while
        # producing identical text/contrast results. Deduplicate those low-priority
        # assets by their source URL before ranking.
        asset_key = None
        if src and (is_decorative or is_logo or classification == "decorative"):
            asset_key = f"{classification}:{sub_type}:{src}"
        if asset_key:
            if asset_key in seen_asset_keys:
                continue
            seen_asset_keys.add(asset_key)

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

    if limit is None or len(ordered) <= limit:  # None = no limit
        return ordered, []

    if not fair_per_page:
        return ordered[:limit], ordered[limit:]

    # Fair per-page round-robin. Bucket the globally-ranked paths by source page
    # (buckets keyed by first appearance ⇒ ordered by page priority), then take
    # one image per page per round until the budget is spent. Each page keeps its
    # own priority order internally, so every page contributes its top images.
    from collections import OrderedDict, deque

    buckets: "OrderedDict[str, deque[str]]" = OrderedDict()
    for path in ordered:
        buckets.setdefault(page_by_path.get(path, ""), deque()).append(path)

    selected: list[str] = []
    queues = list(buckets.values())
    while len(selected) < limit and any(queues):
        progressed = False
        for q in queues:
            if q:
                selected.append(q.popleft())
                progressed = True
                if len(selected) >= limit:
                    break
        if not progressed:
            break

    selected_set = set(selected)
    skipped = [p for p in ordered if p not in selected_set]
    return selected, skipped
