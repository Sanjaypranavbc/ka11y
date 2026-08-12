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


def _sha1_of(path: Path) -> str:
    """Content hash of a captured file, used to tell "same image reused" from
    "different element that merely shares a src"."""
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _unique_basename(
    taken: Dict[str, str],
    prefix: str,
    digest: str,
    ext: str,
    element_id: str,
    content_hash: str,
) -> str:
    """Return the basename this capture should be stored under.

    Basenames are the pipeline's join key: OCR results are correlated back to
    images by ``Path(filename).name`` alone (see ``_build_ocr_index``). Naming
    the file after ``md5(src)`` therefore collapsed every element sharing a src
    onto ONE file — a logo in the sticky header and the same logo in the footer
    render differently, so the second copy overwrote the first and both records
    then pointed at one screenshot with one OCR result. Identical bytes still
    share a name (that keeps OCR work deduplicated, which is the point of
    hashing the src); only genuinely different pixels get a suffix.
    """
    base = f"{prefix}{digest}.{ext}"
    seen = taken.get(base)
    if seen is None or seen == content_hash:
        taken[base] = content_hash
        return base

    suffix = hashlib.md5(element_id.encode("utf-8")).hexdigest()[:6]
    candidate = f"{prefix}{digest}_{suffix}.{ext}"
    n = 1
    while taken.get(candidate) not in (None, content_hash):
        candidate = f"{prefix}{digest}_{suffix}_{n}.{ext}"
        n += 1
    taken[candidate] = content_hash
    return candidate


def _subpath(classification: str | None, sub_type: str | None) -> Path:
    cls = classification or "informative"
    if cls == "functional":
        sub = sub_type or "images"
        if sub in ("buttons", "icons", "logos", "images"):
            return Path("functional") / sub
        return Path("functional")
    if cls == "complex":
        sub = sub_type or "charts"
        if sub in ("charts", "emojis"):
            return Path("complex") / sub
        return Path("complex")
    return Path(cls)


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
    # basename → content hash, across the whole run (basenames are the OCR
    # correlation key, so they must be unique per distinct set of pixels even
    # across classification sub-directories).
    taken_basenames: Dict[str, str] = {}

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
            classification = el.get("classification")
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
                digest = hashlib.md5(key.encode("utf-8")).hexdigest()[:12]
                ext = _ext(el, captured)

                el_type = el.get("element_type", "")
                if "svg" in el_type:
                    prefix = "svg_"
                    ext = "png"
                elif sub_type == "buttons" and (flags.get("is_button") or el_type == "button"):
                    prefix = "btn_"
                    ext = "png"
                else:
                    prefix = "img_"

                dest_dir = output_dir / _subpath(classification, sub_type)
                dest_dir.mkdir(parents=True, exist_ok=True)
                try:
                    filename = _unique_basename(
                        taken_basenames,
                        prefix,
                        digest,
                        ext,
                        str(el.get("id") or f"{page_url}#{src}"),
                        _sha1_of(captured),
                    )
                    dest = dest_dir / filename
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
                classification=classification,
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

