"""
ka11y/accessibility/rules/media/video_analysis.py
==================================================
Frame-level analysis of directly linked video files (Phase 3, WP-11).

The DOM cannot see what a video shows. For each ``<video>`` with a direct
same-site file source (mp4/webm/ogv/mov — not HLS/DASH streams) the file is
downloaded once (public hosts, size cap) and decoded with OpenCV:

* **G19 / G15 / G176 (2.3.1 / 2.3.2)** — flash analysis: relative-luminance
  transitions per 32×18 cell over the first seconds; more than three
  opposing transition pairs in any one-second window is a flash; the flashing
  area is compared with the general-flash threshold (≈ 25 % of a 10° field,
  approximated as 2.8 % of the frame).
* **G93 (1.2.2 / 1.2.4)** — open (burned-in) captions: the lower third of
  frames sampled every 5 s is run through the OCR text detector; consistent
  text bands are reported as probable open captions.
* **G203 (1.2.3 / 1.2.5)** — talking-head classification with a Haar face
  cascade: a face present in most sampled frames and occupying a meaningful
  area means a static text alternative can be acceptable.
* **G54 (1.2.6)** — a small face persistently in a bottom corner is noted as a
  possible sign-language interpreter (manual review, not a verdict).

Everything is bounded (frames, seconds, bytes) and best-effort.
"""

from __future__ import annotations

import os
import re
import tempfile
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlsplit

from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="video-analysis")

_VIDEO_RE = re.compile(r"\.(mp4|m4v|webm|ogv|ogg|mov)(?:[?#].*)?$", re.IGNORECASE)
_MAX_BYTES = int(os.environ.get("KA11Y_VIDEO_MAX_BYTES", str(40_000_000)))
_MAX_VIDEOS = int(os.environ.get("KA11Y_VIDEO_MAX_FILES", "3"))
_TIMEOUT_S = 30.0
_FLASH_SECONDS = 6.0
_MAX_FLASH_FRAMES = 240
_GRID = (32, 18)
_AREA_THRESHOLD = 0.028  # ≈ 25 % of a 10° field on a typical display, as a fraction of the frame


def is_direct_video(src: Optional[str]) -> bool:
    return bool(src) and src.startswith(("http://", "https://")) and bool(_VIDEO_RE.search(src.split("?")[0] + ("?" + src.split("?", 1)[1] if "?" in src else "")))


def fetch_video(src: str, *, timeout: float = _TIMEOUT_S, max_bytes: int = _MAX_BYTES) -> Optional[str]:
    """Download to a temp file; return its path or None."""
    try:
        from ka11y.crawler._ssrf_guard import _host_is_blocked

        host = urlsplit(src).hostname or ""
        if not host or _host_is_blocked(host):
            return None
        import httpx

        fd, path = tempfile.mkstemp(suffix=os.path.splitext(src.split("?")[0])[1] or ".mp4", prefix="ka11y-video-")
        size = 0
        with os.fdopen(fd, "wb") as fh, httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": "ka11y-audit/1.0"}) as client:
            with client.stream("GET", src) as resp:
                if resp.status_code != 200:
                    os.unlink(path)
                    return None
                for chunk in resp.iter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        fh.close()
                        os.unlink(path)
                        return None
                    fh.write(chunk)
        return path
    except Exception:
        return None


def _flash_stats(frames_gray: List[Any], fps: float) -> Dict[str, Any]:
    """frames_gray: list of (H, W) float arrays in 0..1 (grid-downscaled)."""
    import numpy as np

    if len(frames_gray) < 4 or fps <= 0:
        return {"max_flashes_per_second": 0.0, "flashing_area": 0.0}
    seq = np.stack(frames_gray)  # (T, gh, gw)
    lum = np.where(seq <= 0.03928, seq / 12.92, ((seq + 0.055) / 1.055) ** 2.4)
    diff = np.diff(lum, axis=0)  # (T-1, gh, gw)
    darker = np.minimum(lum[1:], lum[:-1])
    sig = np.where((np.abs(diff) >= 0.10) & (darker < 0.80), np.sign(diff), 0)  # significant transitions
    T = sig.shape[0]
    win = max(2, int(round(fps)))
    max_fps = 0.0
    flashing = np.zeros(sig.shape[1:], dtype=bool)
    gh, gw = sig.shape[1], sig.shape[2]
    # per cell: sequence of (frame index, sign) for significant transitions; a flash is a
    # pair of opposing transitions, counted inside any window of one second
    for y in range(gh):
        for x in range(gw):
            col = sig[:, y, x]
            idx = np.nonzero(col)[0]
            if idx.size < 2:
                continue
            signs = col[idx]
            best = 0
            for i in range(idx.size):
                pairs, last = 0, signs[i]
                j = i + 1
                while j < idx.size and idx[j] - idx[i] <= win:
                    if signs[j] != last:
                        pairs += 1
                        last = signs[j]
                    j += 1
                best = max(best, (pairs + 1) // 2)
            rate = float(best)
            max_fps = max(max_fps, rate)
            if rate > 3:
                flashing[y, x] = True
    return {"max_flashes_per_second": round(max_fps, 2), "flashing_area": round(float(flashing.mean()), 4)}


def analyze_video_file(path: str, *, ocr: Optional[Callable[[str], str]] = None) -> Dict[str, Any]:
    """Return {duration, fps, flash, faces, captions} for a local video file."""
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return {"error": "cannot decode"}
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = n / fps if fps > 0 else 0.0
    out: Dict[str, Any] = {"duration": round(duration, 2), "fps": round(fps, 2), "frames": n}

    # ── flash: first _FLASH_SECONDS at native fps ──
    grays: List[Any] = []
    limit = min(int(fps * _FLASH_SECONDS) if fps > 0 else 0, _MAX_FLASH_FRAMES, n or _MAX_FLASH_FRAMES)
    for _ in range(limit):
        ok, frame = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(g, _GRID, interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        grays.append(small)
    out["flash"] = _flash_stats(grays, fps)

    # ── sampled frames for faces / captions ──
    sample_times = [t for t in np.linspace(0.5, max(0.5, duration - 0.5), num=min(8, max(1, int(duration // 5) + 1)))] if duration else [0.0]
    cascade = None
    try:
        cascade = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))
    except Exception:
        cascade = None
    face_frames = 0
    corner_frames = 0
    face_area = []
    caption_hits = 0
    caption_samples = 0
    for i, t in enumerate(sample_times):
        cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000.0)
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        if cascade is not None and not cascade.empty():
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(max(24, w // 20), max(24, h // 20)))
            if len(faces):
                face_frames += 1
                fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3])
                face_area.append((fw * fh) / float(w * h))
                if (fw * fh) / float(w * h) < 0.08 and fy + fh > h * 0.55 and (fx < w * 0.3 or fx + fw > w * 0.7):
                    corner_frames += 1
        if ocr is not None and i % max(1, len(sample_times) // 5) == 0:
            caption_samples += 1
            band = frame[int(h * 0.66):h, :]
            tmp = os.path.join(tempfile.gettempdir(), f"ka11y-caption-{os.getpid()}-{i}.png")
            try:
                cv2.imwrite(tmp, band)
                text = (ocr(tmp) or "").strip()
                if len(re.sub(r"[^A-Za-z぀-ヿ㐀-鿿]", "", text)) >= 8:
                    caption_hits += 1
            except Exception:
                pass
            finally:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
    cap.release()
    sampled = len(sample_times)
    out["faces"] = {
        "sampled": sampled, "with_face": face_frames,
        "talking_head": bool(sampled and face_frames / sampled >= 0.6 and face_area and (sum(face_area) / len(face_area)) >= 0.03),
        "possible_corner_interpreter": bool(sampled and corner_frames / sampled >= 0.6),
    }
    out["captions"] = {"sampled": caption_samples, "text_bands": caption_hits, "open_captions_likely": bool(caption_samples and caption_hits / caption_samples >= 0.6)}
    return out


def _make_ocr(lang: str = "en") -> Optional[Callable[[str], str]]:
    """Lazily build an OCR callable on the project's text detector; None if unavailable."""
    try:
        from ka11y.text_detector.text_detector import OCRPreprocessing

        holder: Dict[str, Any] = {}

        def run(path: str) -> str:
            if "det" not in holder:
                holder["det"] = OCRPreprocessing(source_directory=os.path.dirname(path), lang=lang)
            res = holder["det"].detect_text_in_image(path)
            return " ".join(d.text for d in (res.detections or []) if getattr(d, "text", None))

        return run
    except Exception:
        return None


def analyze_media_records(records: List[Dict[str, Any]], page_url: str, *, lang: str = "en", fetch=fetch_video, analyze=analyze_video_file, use_ocr: bool = True) -> List[Dict[str, Any]]:
    """Annotate media audit records in place (keys ``video_analysis``) and return 2.3.1/2.3.2 findings."""
    from ka11y.api.v1.combined.findings import _make_finding

    findings: List[Dict[str, Any]] = []
    seen: Dict[str, Dict[str, Any]] = {}
    ocr = _make_ocr(lang) if use_ocr else None
    budget = _MAX_VIDEOS
    for r in records:
        if (r.get("tag") or "").lower() != "video":
            continue
        src = r.get("src") or ""
        if not is_direct_video(src):
            continue
        if src not in seen:
            if budget <= 0:
                continue
            budget -= 1
            path = fetch(src)
            if not path:
                continue
            try:
                seen[src] = analyze(path, ocr=ocr) if "ocr" in analyze.__code__.co_varnames else analyze(path)
            except Exception as exc:
                logger.warning("video analysis failed for %s: %s", src, exc)
                seen[src] = {"error": str(exc)}
            finally:
                try:
                    os.unlink(path)
                except Exception:
                    pass
        a = seen[src]
        if not a or a.get("error"):
            continue
        r["video_analysis"] = a
        html = (r.get("html_snippet") or f'<video src="{src}">')[:300]
        purl = r.get("page_url") or page_url
        fl = a.get("flash") or {}
        # ── 2.3.1 / 2.3.2 ──
        rate, area = fl.get("max_flashes_per_second", 0), fl.get("flashing_area", 0)
        if rate > 3:
            over_area = area > _AREA_THRESHOLD
            findings.append(_make_finding(source="python", rule_id="python_2_3_1_video_flash", wcag_sc="2.3.1",
                status="fail" if over_area else "needs_review", severity="critical" if over_area else "moderate",
                reason=(f"Video content flashes {rate}×/s over {round(area * 100, 1)}% of the frame in the first {int(_FLASH_SECONDS)} s — "
                        + ("exceeds the general flash threshold (G19/G15)." if over_area else "small area; verify against the general flash threshold (G176 area exception, G19).")),
                element_html=html, element_tag="video", page_url=purl))
            findings.append(_make_finding(source="python", rule_id="python_2_3_2_video_flash", wcag_sc="2.3.2", status="fail", severity="critical",
                reason=f"Video content flashes {rate}×/s — under 2.3.2 no area exception applies (G19).", element_html=html, element_tag="video", page_url=purl))
        else:
            findings.append(_make_finding(source="python", rule_id="python_2_3_1_video_flash", wcag_sc="2.3.1", status="pass", severity=None,
                reason=f"Video frames analysed ({a.get('fps')} fps, first {int(_FLASH_SECONDS)} s): no region flashes more than three times per second (G19/G15).",
                element_html=html, element_tag="video", page_url=purl))
        # ── annotate 1.2.2 / 1.2.3 records (consumed by the media findings converter) ──
        caps = a.get("captions") or {}
        if caps.get("open_captions_likely"):
            for key in ("wcag_1_2_2_status", "wcag_1_2_4_status"):
                if r.get(key) in ("FAILED", "NEEDS_REVIEW"):
                    r[key] = "NEEDS_REVIEW"
                    vk = key.replace("_status", "_violation")
                    r[vk] = (r.get(vk) or "") + f" Frame OCR found text bands in the lower third of {caps.get('text_bands')}/{caps.get('sampled')} sampled frames — probably open (burned-in) captions (G93); confirm they cover all dialogue."
        faces = a.get("faces") or {}
        if faces.get("talking_head") and r.get("wcag_1_2_3_status") == "NEEDS_REVIEW":
            r["wcag_1_2_3_violation"] = (r.get("wcag_1_2_3_violation") or "") + f" A face fills the frame in {faces.get('with_face')}/{faces.get('sampled')} sampled frames — talking-head video (G203): a static text alternative describing the speaker is acceptable instead of audio description."
        if faces.get("possible_corner_interpreter"):
            r["wcag_1_2_6_note"] = "A small face persists in a bottom corner of the frame — possibly a sign-language interpreter (G54); confirm manually."
    return findings
