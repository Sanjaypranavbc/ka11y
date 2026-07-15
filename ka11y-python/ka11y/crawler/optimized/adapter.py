"""
ka11y/crawler/optimized/adapter.py
==================================
Convert the optimized crawler's raw per-page JSON facts into the records the
existing ka11y image pipeline consumes — ``List[ImageData]`` — without touching
any downstream stage (OCR / audit / report).

The pipeline correlates OCR results back to images by FILE BASENAME
(``Path(filename).name`` — see text_detector + alttext auditor). So for every
captured image we copy its pixel file into ``output_dir`` under a unique,
stable name ``img_<md5(src)>.<ext>`` and stamp that name onto both
``ImageData.filename`` and ``ImageData.screenshot_path``. Files are laid out
under ``<classification>/<sub_type>/`` so the OCR category heuristic (which keys
off substrings like "button"/"logo"/"chart") keeps working.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Dict, List, Set, Tuple

from ka11y.crawler.models import ImageData

# Image-classified element types that become an ImageData record. (``area`` is
# an image-map sub-part with no standalone pixels, so it is excluded.)
_IMAGE_TYPES = {
    "img", "svg_via_img", "svg_inline", "svg_via_use", "svg_via_object",
    "css_background_image", "css_background_svg", "input_image", "canvas",
}
# Per type, the element field holding the source URL (for hashing + file_format).
_SRC_FIELD = {
    "img": "src", "svg_via_img": "src", "input_image": "src",
    "svg_via_object": "data_url", "css_background_image": "resolved_background_url",
    "css_background_svg": "resolved_background_url",
}


def _src_of(el: dict) -> str:
    field = _SRC_FIELD.get(el.get("element_type", ""))
    return (el.get(field) if field else None) or ""


def _alt_text(el: dict):
    """The effective accessible name, mirroring meghana's resolved-label:
    prefer the computed accessible name, fall back to the alt attribute.
    Returns None only when the name is genuinely absent (a 1.1.1 signal)."""
    name = (el.get("accessibility_snapshot_name") or "").strip()
    if el.get("alt_present"):
        av = el.get("alt_value")
        if av == "":
            return name or ""          # explicit decorative empty alt
        return name or av
    return name or None                 # alt attribute missing → None


def _ext(el: dict, captured: Path | None) -> str:
    if captured and captured.suffix:
        return captured.suffix.lstrip(".").lower()
    src = _src_of(el)
    if src.startswith("data:"):
        head = src[5:].split(",", 1)[0]
        mime = head.split(";", 1)[0]
        return (mime.split("/", 1)[1].split("+")[0] if "/" in mime else "bin")
    tail = src.split("?", 1)[0].rsplit(".", 1)
    return tail[1].lower() if len(tail) == 2 and len(tail[1]) <= 5 else "png"


def build_image_data(
    raw_dir: Path, output_dir: Path
) -> Tuple[List[ImageData], Dict[str, str], Set[str]]:
    """Read every per-page JSON in ``raw_dir`` and return
    ``(images_data, page_langs, visited_urls)``. Captured pixel files are copied
    into ``output_dir`` with basenames the OCR/audit stages can correlate on."""
    raw_dir = Path(raw_dir)
    output_dir = Path(output_dir)
    images: List[ImageData] = []
    page_langs: Dict[str, str] = {}
    visited: Set[str] = set()

    for jf in sorted(raw_dir.glob("*.json")):
        try:
            doc = json.loads(jf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if doc.get("processing_status") != "success":
            continue
        page_url = doc.get("page_url", "")
        visited.add(page_url)
        lang = doc.get("page_lang")
        if lang:
            page_langs[page_url] = lang

        for el in doc.get("elements", []):
            if not isinstance(el, dict) or el.get("element_type") not in _IMAGE_TYPES:
                continue
            if el.get("classification") is None:
                continue

            src = _src_of(el)
            flags = el.get("flags") or {}
            sub_type = el.get("sub_type")

            # Locate the captured pixel file (screenshot overlay OR download).
            rel = el.get("screenshot") or el.get("asset_file")
            captured = (raw_dir / rel) if rel else None
            if captured is not None and not captured.exists():
                captured = None

            filename = ""
            screenshot_path = ""
            capture_status = "dom_missing"
            if captured is not None:
                key = src or f"{page_url}#{el.get('id', '')}"
                digest = hashlib.md5(key.encode("utf-8")).hexdigest()
                ext = _ext(el, captured)
                dest_dir = output_dir / (el.get("classification") or "images") / (sub_type or "images")
                dest_dir.mkdir(parents=True, exist_ok=True)
                filename = f"img_{digest}.{ext}"
                dest = dest_dir / filename
                try:
                    shutil.copy2(captured, dest)
                    screenshot_path = str(dest)
                    capture_status = "ok"
                except OSError:
                    filename = ""
                    capture_status = "failed"

            dec = el.get("decorative_signals") or {}
            images.append(ImageData(
                url=page_url,
                src=src,
                alt_text=_alt_text(el),
                title=el.get("title_attr") or "",
                classification=el.get("classification"),
                sub_type=sub_type,
                is_functional=bool(flags.get("is_functional")),
                is_decorative=bool(flags.get("is_decorative")),
                is_complex=bool(flags.get("is_complex")),
                is_text_image=bool((el.get("image_of_text") or {}).get("possible_image_of_text")),
                is_logo=bool(flags.get("is_logo")),
                is_icon=bool(flags.get("is_icon")),
                is_button=(sub_type == "buttons"),
                file_format=_ext(el, captured),
                element_id=el.get("id"),
                screenshot_path=screenshot_path,
                filename=filename,
                capture_status=capture_status,
                aria_hidden="true" if dec.get("aria_hidden") else None,
                role=el.get("role"),
            ))

    return images, page_langs, visited
