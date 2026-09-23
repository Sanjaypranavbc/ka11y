"""
ka11y/accessibility/rules/media/animated_images.py
===================================================
WCAG 2.2.2 Pause, Stop, Hide — animated raster images (G152).

The DOM cannot tell whether a ``.gif`` / ``.webp`` / ``.png`` keeps moving. This
module downloads each candidate image once (bounded size and time, public hosts
only) and reads the frame count, loop flag and total duration with Pillow.

Verdicts (per distinct source URL):

* not animated                         → no finding
* animated, finite loop, ≤ 5 s total    → pass (G152 satisfied by design)
* animated, infinite loop or > 5 s      → needs_review: the page must offer a
                                          pause/stop/hide control (checked by the
                                          Node pause-stop-hide rule) or the
                                          animation must be trimmed.
"""

from __future__ import annotations

import io
import re
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="animated-images")

_CANDIDATE_RE = re.compile(r"\.(gif|webp|png|apng)(?:[?#].*)?$", re.IGNORECASE)
_MAX_BYTES = 3_000_000
_MAX_IMAGES = 40
_TIMEOUT_S = 6.0
_LIMIT_MS = 5000


def _is_candidate(src: str) -> bool:
    return bool(src) and src.startswith(("http://", "https://")) and bool(_CANDIDATE_RE.search(src))


def _host_allowed(src: str) -> bool:
    """Reuse the crawler's SSRF classification so we never fetch private hosts."""
    try:
        from ka11y.crawler._ssrf_guard import _host_is_blocked

        host = urlparse(src).hostname or ""
        return bool(host) and not _host_is_blocked(host)
    except Exception:
        return False


def inspect_image_bytes(data: bytes) -> Optional[Dict[str, Any]]:
    """Return ``{frames, loop_infinite, total_ms}`` for animated data, ``None`` otherwise."""
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as im:
            if not getattr(im, "is_animated", False):
                return None
            frames = int(getattr(im, "n_frames", 1) or 1)
            if frames <= 1:
                return None
            loop = im.info.get("loop")
            # GIF/WebP/APNG: loop == 0 means "forever"; missing loop on GIF = play once.
            loop_infinite = loop == 0
            total_ms = 0
            for i in range(min(frames, 400)):
                try:
                    im.seek(i)
                    total_ms += int(im.info.get("duration") or 100)
                except EOFError:
                    break
            if frames > 400:
                total_ms = int(total_ms * frames / 400)
            return {"frames": frames, "loop_infinite": bool(loop_infinite), "total_ms": total_ms, "loop": loop}
    except Exception:
        return None


def fetch_bytes(src: str, *, timeout: float = _TIMEOUT_S, max_bytes: int = _MAX_BYTES) -> Optional[bytes]:
    if not _host_allowed(src):
        return None
    try:
        import httpx

        with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": "ka11y-audit/1.0"}) as client:
            with client.stream("GET", src) as resp:
                if resp.status_code != 200:
                    return None
                ctype = (resp.headers.get("content-type") or "").lower()
                if ctype and not ctype.startswith("image/"):
                    return None
                buf = bytearray()
                for chunk in resp.iter_bytes():
                    buf.extend(chunk)
                    if len(buf) > max_bytes:
                        return None
                return bytes(buf)
    except Exception:
        return None


def scan_animated_images(images_data: Iterable[Any], *, max_images: int = _MAX_IMAGES, fetch=fetch_bytes) -> List[Dict[str, Any]]:
    """Inspect distinct candidate sources; return one record per animated image."""
    seen: set[str] = set()
    records: List[Dict[str, Any]] = []
    for img in images_data:
        src = str(getattr(img, "src", "") or "")
        if not _is_candidate(src) or src in seen:
            continue
        seen.add(src)
        if len(seen) > max_images:
            break
        data = fetch(src)
        if not data:
            continue
        info = inspect_image_bytes(data)
        if not info:
            continue
        records.append({
            "src": src,
            "page_url": getattr(img, "url", "") or "",
            "element_id": getattr(img, "element_id", None),
            "alt_text": getattr(img, "alt_text", None),
            **info,
        })
    return records


def animated_images_to_findings(images_data: Iterable[Any], page_url: str, **kw) -> List[Dict[str, Any]]:
    """Turn animated-image records into 2.2.2 findings (G152)."""
    from ka11y.api.v1.combined.findings import _make_finding

    findings: List[Dict[str, Any]] = []
    try:
        records = scan_animated_images(images_data, **kw)
    except Exception as exc:  # never break the stage
        logger.warning("animated image scan failed: %s", exc)
        return findings
    for r in records:
        over = r["loop_infinite"] or r["total_ms"] > _LIMIT_MS
        secs = round(r["total_ms"] / 1000, 1)
        html = f'<img src="{r["src"]}"' + (f' alt="{r["alt_text"]}"' if r.get("alt_text") is not None else "") + ">"
        if over:
            reason = (
                f"Animated image ({r['frames']} frames, {secs} s per cycle, "
                f"{'loops forever' if r['loop_infinite'] else 'finite loop'}) plays for more than 5 seconds. "
                "Provide a pause/stop/hide control for it, or limit the animation to 5 seconds (G152)."
            )
            status, severity = "needs_review", "moderate"
        else:
            reason = f"Animated image ({r['frames']} frames, {secs} s, finite loop) stops within 5 seconds (G152)."
            status, severity = "pass", None
        findings.append(_make_finding(
            source="python",
            rule_id="python_2_2_2_animated_image",
            wcag_sc="2.2.2",
            status=status,
            severity=severity,
            reason=reason,
            element_html=html,
            element_id=r.get("element_id") or r["src"],
            element_tag="img",
            image_src=None,
            image_reference=r["src"].rsplit("/", 1)[-1][:80],
            page_url=r.get("page_url") or page_url,
        ))
    return findings
