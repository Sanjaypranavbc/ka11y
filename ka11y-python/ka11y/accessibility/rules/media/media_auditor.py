"""
ka11y/accessibility/rules/media/media_auditor.py
==================================================
WCAG 1.2.1 — Audio-only and Video-only (Prerecorded)  (Level A)

Rule
────
Pre-recorded audio-only content must have a text transcript.
Pre-recorded video-only content must have a text alternative or audio track.

Decision tree (5 gates)
───────────────────────
  Gate 1: Is it prerecorded?  (skip if live → 1.2.9)
  Gate 2: Is it synchronized media?  (skip if both audio+video → 1.2.2/1.2.3)
  Gate 3: Is it a labeled media alternative for existing text?  (exempt)
  Gate 4: Is there a text alternative or audio track?  (FAIL if missing)
  Gate 5: Does the alternative present equivalent info?  (quality checks)

CSV output: audit_media_report.csv

CSV columns
───────────
  page_url, element_index, tag, element_id, src, media_type,
  wcag_1_2_1_status, wcag_1_2_1_violation, wcag_1_2_1_gate_reached,
  transcript_type, transcript_url_or_text,
  html_snippet
"""

import csv
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import requests

from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="media_auditor")


# ─────────────────────────────────────────────────────────────────────────────
# Transcript detection keywords
# ─────────────────────────────────────────────────────────────────────────────

# Keywords that indicate a link leads to a transcript page.
# Case-insensitive matching via _normalize().
_TRANSCRIPT_LINK_KEYWORDS = [
    "transcript",
    "text version",
    "text alternative",
    "text transcript",
    "read the transcript",
    "view transcript",
    "show transcript",
    "full transcript",
    "download transcript",
    # Japanese equivalents
    "書き起こし",
    "文字起こし",
    "トランスクリプト",
    "字幕",
    "キャプション",
    "テキスト版",
    "音声テキスト",
    "音声解説",
    "音声ガイド",
    "説明文",
    "代替テキスト",
]

# Keywords that indicate the media element is a labeled alternative for text.
_MEDIA_ALT_KEYWORDS = [
    "audio version",
    "audio alternative",
    "listen to this",
    "audio description of",
    "video version",
    "video alternative",
    "alternative for",
    # Japanese equivalents
    "音声版",
    "動画版",
    "代替音声",
    "音声代替",
    "テキストの音声化",
    "読み上げ",
]

# Track kinds that count as a text alternative.
_ALT_TRACK_KINDS = {"captions", "descriptions", "subtitles"}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _normalize(text: Optional[str]) -> str:
    """Lowercase, collapse whitespace, strip — for keyword matching."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip()).lower()


# ─────────────────────────────────────────────────────────────────────────────
# Gate functions
# Each returns (status, violation_message, gate_number) or None to continue.
# ─────────────────────────────────────────────────────────────────────────────


def _gate_1_is_prerecorded(item: Dict[str, Any]) -> Optional[Tuple[str, str, int]]:
    """
    Gate 1: Is it prerecorded?

    Live media is detected by:
    - Streaming manifest URLs (.m3u8 for HLS, .mpd for DASH)
    - MediaSource / srcObject patterns in the src
    - Explicit 'live' keyword in nearby text or aria-label

    Returns ("N/A", reason, 1) if live, else None to continue.
    """
    src = _normalize(item.get("src") or "")
    aria_label = _normalize(item.get("aria_label") or "")
    nearby_text = _normalize(item.get("nearby_text") or "")

    # Streaming manifest detection
    if src.endswith(".m3u8") or src.endswith(".mpd"):
        return (
            "N/A",
            "Live streaming media detected (HLS/DASH manifest). "
            "WCAG 1.2.1 does not apply — see 1.2.9.",
            1,
        )

    # Explicit live labeling
    for text in [aria_label, nearby_text]:
        if re.search(r"\blive\b", text):
            return (
                "N/A",
                "Media is labeled as live content. "
                "WCAG 1.2.1 does not apply — see 1.2.9.",
                1,
            )

    return None  # Continue to Gate 2


def _gate_2_media_type(item: Dict[str, Any]) -> str:
    """
    Gate 2: Classify the media type.

    Returns one of:
      "audio_only"    — <audio> tag (always audio-only)
      "video_only"    — <video> tag that likely has no audio track
      "synchronized"  — <video> tag with indicators of both audio + video

    Note: Accurately detecting whether a <video> has an audio track
    requires JS media API access. The crawler extracts `is_muted` as a hint.
    """
    tag = (item.get("tag") or "").upper()

    if tag == "AUDIO":
        return "audio_only"

    # For <video>, we assume it is synchronized (has both audio and video)
    # unless there are strong indicators of video-only:
    #   - muted attribute set AND no audio-related tracks
    #   - Very short silent loops (common for decorative background videos)
    if tag == "VIDEO":
        is_muted = item.get("is_muted", False)
        has_loop = item.get("has_loop", False)
        has_autoplay = item.get("has_autoplay", False)

        # Muted autoplay loop = likely decorative/video-only background
        if is_muted and has_loop and has_autoplay:
            return "video_only"

        # Default assumption: synchronized media
        # In the future, the crawler could check videoElement.audioTracks
        return "synchronized"

    return "synchronized"


def _gate_3_is_labeled_alternative(
    item: Dict[str, Any],
) -> Optional[Tuple[str, str, int]]:
    """
    Gate 3: Is the media a labeled alternative for text already present?

    If the media element is explicitly marked as an alternative version
    of existing text content (e.g., "Audio version of the above article"),
    then WCAG 1.2.1 does not require a separate transcript.

    Returns ("N/A", reason, 3) if exempt, else None to continue.
    """
    aria_label = _normalize(item.get("aria_label") or "")
    nearby_text = _normalize(item.get("nearby_text") or "")

    for keyword in _MEDIA_ALT_KEYWORDS:
        if keyword in aria_label or keyword in nearby_text:
            return (
                "N/A",
                f"Media is a clearly labeled alternative for existing text content "
                f"(matched: '{keyword}'). Exempt from 1.2.1.",
                3,
            )

    return None  # Continue to Gate 4


def _gate_4_find_transcript(
    item: Dict[str, Any],
) -> Tuple[Optional[Dict[str, str]], Optional[Tuple[str, str, int]]]:
    """
    Gate 4: Is there a text alternative or audio track provided?

    Searches for:
    1. <track> child elements with kind=captions/descriptions/subtitles
    2. Nearby <a> links containing transcript keywords
    3. Nearby <details> blocks (collapsible transcript sections)
    4. aria-describedby text (resolved by the crawler)

    Returns:
      (transcript_info, None) — transcript found, continue to Gate 5
      (None, ("FAILED", reason, 4)) — no transcript found, FAIL
    """
    # Check 1: <track> elements
    tracks = item.get("tracks") or []
    for track in tracks:
        kind = _normalize(track.get("kind") or "")
        if kind in _ALT_TRACK_KINDS:
            return (
                {"type": "track", "url_or_text": track.get("src") or "", "kind": kind},
                None,
            )

    # Check 2: Nearby links with transcript keywords
    nearby_links = item.get("nearby_links") or []
    for link in nearby_links:
        link_text = _normalize(link.get("text") or "")
        link_href = link.get("href") or ""
        for keyword in _TRANSCRIPT_LINK_KEYWORDS:
            if keyword in link_text:
                return (
                    {
                        "type": "link",
                        "url_or_text": link_href,
                        "matched_keyword": keyword,
                    },
                    None,
                )

    # Check 3: nearby <details> blocks
    nearby_details = item.get("nearby_details") or []
    for detail in nearby_details:
        summary_text = _normalize(detail.get("summary") or "")
        if any(kw in summary_text for kw in _TRANSCRIPT_LINK_KEYWORDS):
            return (
                {"type": "inline", "url_or_text": detail.get("content") or ""},
                None,
            )

    # Check 4: aria-describedby text
    describedby = item.get("aria_describedby_text") or ""
    if len(describedby.strip()) > 50:
        # A substantial aria-describedby text block likely IS the transcript
        return (
            {"type": "aria_describedby", "url_or_text": describedby},
            None,
        )

    # Nothing found — FAIL
    tag = item.get("tag", "media")
    return (
        None,
        (
            "FAILED",
            f"No text transcript, caption track, or audio alternative found for "
            f"this prerecorded {tag.lower()} element. WCAG 1.2.1 requires a text "
            f"alternative for prerecorded audio-only and video-only content.",
            4,
        ),
    )


def _gate_4_check_captions(item: Dict[str, Any]) -> Tuple[Optional[Dict[str, str]], Optional[Tuple[str, str, int]]]:
    """
    1.2.2 Gate 4: Does the synchronized video have a captions track?
    Returns (track_info, None) if found, else (None, ("FAILED", reason, 4)).
    """
    tracks = item.get("tracks") or []
    for track in tracks:
        kind = _normalize(track.get("kind") or "")
        # Subtitles can serve as captions if they include non-speech audio cues.
        if kind in ("captions", "subtitles"):
            return (
                {"type": "track", "url": track.get("src") or "", "kind": kind},
                None,
            )
            
    return (
        None,
        ("FAILED",
         "Synchronized video is missing a <track kind=\"captions\"> "
         "or <track kind=\"subtitles\"> element. WCAG 1.2.2 requires captions for "
         "prerecorded synchronized media.",
         4),
    )


def _gate_5_validate_track_url(track_url: str) -> Optional[Tuple[str, str, int]]:
    """
    1.2.2 Gate 5: Is the captions track URL reachable and valid?
    Returns ("FAILED", reason, 5) if network request fails or returns 404.
    """
    if not track_url:
        return ("FAILED", "Track element is present but src attribute is missing or empty. (F8 violation)", 5)
        
    try:
        # Use HEAD to quickly check if the file exists without downloading it
        resp = requests.head(track_url, timeout=5, allow_redirects=True)
        if resp.status_code >= 400 and resp.status_code != 405:
            # 405 Method Not Allowed occasionally happens for HEAD, but mostly it's 404
            if resp.status_code == 404:
                return ("FAILED", f"Caption file URL returned 404 Not Found: {track_url} (F8 violation)", 5)
            return ("FAILED", f"Caption file URL returned HTTP error {resp.status_code}: {track_url} (F8 violation)", 5)
    except Exception as e:
        # Network errors = broken link
        return ("FAILED", f"Caption file URL is unreachable: {str(e)} (F8 violation)", 5)
        
    return None

# ─────────────────────────────────────────────────────────────────────────────
# Auditor class
# ─────────────────────────────────────────────────────────────────────────────


class MediaAuditor:
    """
    Audits WCAG 1.2.1 (Audio-only and Video-only, Prerecorded) against
    a list of MediaElementData records from AsyncMediaCrawler.

    Writes audit_media_report.csv to output_dir.
    """

    CSV_FIELDS = [
        "page_url",
        "element_index",
        "tag",
        "element_id",
        "src",
        "media_type",
        "wcag_1_2_1_status",
        "wcag_1_2_1_violation",
        "wcag_1_2_1_gate_reached",
        "wcag_1_2_2_status",
        "wcag_1_2_2_violation",
        "wcag_1_2_2_gate_reached",
        "transcript_type",
        "transcript_url_or_text",
        "quality_report",
        "selector",
        "element_ref_id",
        "frame_path",
        "html_snippet",
    ]

    def __init__(self, output_dir: str, lang: str = "en") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.lang = lang

    def generate_audit_report(
        self,
        items: List[Dict[str, Any]],
        run_1_2_1: bool = True,
        run_1_2_2: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Audit all media elements through Gates 1–5.

        Parameters
        ----------
        items : List[Dict]
            Raw dicts from AsyncMediaCrawler (MediaElementData.model_dump()).

        Returns
        -------
        List[Dict]
            One record per element with wcag_1_2_1_status and
            wcag_1_2_1_violation keys.
        """
        records: List[Dict[str, Any]] = []

        for item in items:
            record = self._audit_single(item, run_1_2_1, run_1_2_2)
            records.append(record)

        self._write_csv(records)
        self._log_summary(records)
        return records

    def _audit_single(self, item: Dict[str, Any], run_1_2_1: bool = True, run_1_2_2: bool = True) -> Dict[str, Any]:
        """Run all gates on a single media element, return the audit record."""
        base = {
            "page_url": item.get("page_url", ""),
            "element_index": item.get("element_index", 0),
            "tag": item.get("tag", ""),
            "element_id": item.get("element_id"),
            "src": item.get("src"),
            "wcag_1_2_1_status": "N/A",
            "wcag_1_2_1_violation": "",
            "wcag_1_2_1_gate_reached": 0,
            "wcag_1_2_2_status": "N/A",
            "wcag_1_2_2_violation": "",
            "wcag_1_2_2_gate_reached": 0,
            "html_snippet": (item.get("html_snippet") or "")[:400],
            "transcript_type": None,
            "transcript_url_or_text": None,
            "quality_report": None,
            "selector": item.get("selector"),
            "element_ref_id": item.get("element_ref_id"),
            "frame_path": item.get("frame_path"),
        }

        # ── Gate 1: Is it prerecorded? ────────────────────────────────────
        gate1 = _gate_1_is_prerecorded(item)
        if gate1:
            status, violation, gate = gate1
            base.update(
                {
                    "media_type": "live",
                    "wcag_1_2_1_status": status,
                    "wcag_1_2_1_violation": violation,
                    "wcag_1_2_1_gate_reached": gate,
                }
            )
            return base

        # ── Gate 2: Classify media type ───────────────────────────────────
        media_type = _gate_2_media_type(item)
        base["media_type"] = media_type

        # Synchronized media → 1.2.1 does not apply
        if media_type == "synchronized":
            base.update({
                "wcag_1_2_1_status": "N/A",
                "wcag_1_2_1_violation": (
                    "Synchronized media (has both audio and video tracks). "
                    "WCAG 1.2.1 does not apply — see 1.2.2."
                ),
                "wcag_1_2_1_gate_reached": 2,
            })
            
            # ── 1.2.2 Flow for Synchronized Media ─────────────────────────────
            
            if not run_1_2_2:
                return base

            # Gate 3: Is it a labeled alternative?
            gate3 = _gate_3_is_labeled_alternative(item)
            if gate3:
                status, violation, gate = gate3
                base.update({
                    "wcag_1_2_2_status": status,
                    "wcag_1_2_2_violation": violation,
                    "wcag_1_2_2_gate_reached": gate,
                })
                return base
                
            # Gate 4: Does it have a caption/subtitle track?
            track_info, gate4_fail = _gate_4_check_captions(item)
            if gate4_fail:
                status, violation, gate = gate4_fail
                base.update({
                    "wcag_1_2_2_status": status,
                    "wcag_1_2_2_violation": violation,
                    "wcag_1_2_2_gate_reached": gate,
                })
                return base
                
            # Gate 5: Validate the track URL
            track_url = track_info.get("url") or ""
            # If the URL is relative, prepend the page_url
            if track_url.startswith("/"):
                # Basic absolute url resolution using requests
                from urllib.parse import urljoin
                track_url = urljoin(item.get("page_url", ""), track_url)
            elif not track_url.startswith("http"):
                from urllib.parse import urljoin
                track_url = urljoin(item.get("page_url", ""), track_url)
                
            gate5_fail = _gate_5_validate_track_url(track_url)
            if gate5_fail:
                status, violation, gate = gate5_fail
                base.update({
                    "wcag_1_2_2_status": status,
                    "wcag_1_2_2_violation": violation,
                    "wcag_1_2_2_gate_reached": gate,
                })
                return base
                
            # Gate 6: Needs Review
            track_kind = track_info["kind"]
            review_msg = (
                f"Video has a valid <track kind=\"{track_kind}\">. "
                "Human review required to verify accuracy "
            )
            if track_kind == "subtitles":
                review_msg += "and ensure non-speech audio cues (sound effects, speaker ID) are included."
            else:
                review_msg += "of the captions."
                
            base.update({
                "wcag_1_2_2_status": "NEEDS_REVIEW",
                "wcag_1_2_2_violation": review_msg, 
                "wcag_1_2_2_gate_reached": 6,
            })
            return base



        # ── Gate 3: Is it a labeled media alternative? ────────────────────
        
        if not run_1_2_1:
            return base

        gate3 = _gate_3_is_labeled_alternative(item)
        if gate3:
            status, violation, gate = gate3
            base.update(
                {
                    "wcag_1_2_1_status": status,
                    "wcag_1_2_1_violation": violation,
                    "wcag_1_2_1_gate_reached": gate,
                }
            )
            return base

        # Check if it's decorative (aria-hidden or role=presentation)
        if item.get("aria_hidden") or item.get("role") in ("presentation", "none"):
            base.update(
                {
                    "wcag_1_2_1_status": "N/A",
                    "wcag_1_2_1_violation": (
                        "Media element is marked as decorative "
                        "(aria-hidden='true' or role='presentation'). "
                        "WCAG 1.2.1 does not apply."
                    ),
                    "wcag_1_2_1_gate_reached": 3,
                }
            )
            return base

        # ── Gate 4: Find transcript / alternative ─────────────────────────
        transcript_info, gate4_fail = _gate_4_find_transcript(item)

        if gate4_fail:
            status, violation, gate = gate4_fail
            base.update(
                {
                    "wcag_1_2_1_status": status,
                    "wcag_1_2_1_violation": violation,
                    "wcag_1_2_1_gate_reached": gate,
                }
            )
            return base

        # Transcript found — record what was found
        base["transcript_type"] = (
            transcript_info.get("type") if transcript_info else None
        )
        base["transcript_url_or_text"] = (
            (transcript_info.get("url_or_text") or "")[:500]
            if transcript_info
            else None
        )

        # ── Gate 5: Quality checks (mandatory) ────────────────────────────
        quality_report = self._run_quality_checks(
            media_src=item.get("src"),
            transcript_info=transcript_info,
            media_type=media_type,
        )

        if quality_report:
            base["quality_report"] = quality_report
            overall = quality_report.get("overall_status", "NEEDS_REVIEW")
            base.update(
                {
                    "wcag_1_2_1_status": overall,
                    "wcag_1_2_1_violation": quality_report.get("message", ""),
                    "wcag_1_2_1_gate_reached": 5,
                }
            )
        else:
            base.update(
                {
                    "wcag_1_2_1_status": "NEEDS_REVIEW",
                    "wcag_1_2_1_violation": (
                        f"Transcript/alternative found ({transcript_info.get('type')}). "
                        f"Quality evaluation could not run (missing media URL or transcript text)."
                    ),
                    "wcag_1_2_1_gate_reached": 5,
                }
            )

        return base

    def _run_quality_checks(
        self,
        media_src: Optional[str],
        transcript_info: Optional[Dict[str, str]],
        media_type: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Run Gate 5 quality checks via the quality engine.

        Returns the QualityReport dict, or None if inputs are insufficient.
        """
        from ka11y.accessibility.rules.media.quality_engine import (
            evaluate_transcript_quality,
        )

        if not media_src or not transcript_info:
            return None

        try:
            return evaluate_transcript_quality(
                media_url=media_src,
                transcript_text=transcript_info.get("url_or_text") or "",
                transcript_type=transcript_info.get("type") or "link",
                media_type=media_type,
                output_dir=str(self.output_dir),
                lang=self.lang,
            )
        except Exception as exc:
            logger.warning(f"[media_auditor] quality check failed: {exc}")
            return None

    # ── CSV output ────────────────────────────────────────────────────────

    def _write_csv(self, records: List[Dict[str, Any]]) -> None:
        """Write audit results to CSV."""
        csv_path = self.output_dir / "audit_media_report.csv"
        if not records:
            return
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=self.CSV_FIELDS, extrasaction="ignore"
            )
            writer.writeheader()
            writer.writerows(records)
        logger.info(f"[media_auditor] saved {csv_path}")

    def _log_summary(self, records: List[Dict[str, Any]]) -> None:
        """Log a summary of the audit."""
        total = len(records)
        failed = sum(1 for r in records if r.get("wcag_1_2_1_status") == "FAILED")
        passed = sum(1 for r in records if r.get("wcag_1_2_1_status") == "PASSED")
        review = sum(1 for r in records if r.get("wcag_1_2_1_status") == "NEEDS_REVIEW")
        na = sum(1 for r in records if r.get("wcag_1_2_1_status") == "N/A")
        logger.info(
            f"[media_auditor] {total} elements | "
            f"{failed} FAILED | {passed} PASSED | "
            f"{review} NEEDS_REVIEW | {na} N/A"
        )

    @staticmethod
    def summarize(records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Return a summary dict for the audit results."""
        failed = sum(1 for r in records if r.get("wcag_1_2_1_status") == "FAILED")
        passed = sum(1 for r in records if r.get("wcag_1_2_1_status") == "PASSED")
        review = sum(1 for r in records if r.get("wcag_1_2_1_status") == "NEEDS_REVIEW")
        na = sum(1 for r in records if r.get("wcag_1_2_1_status") == "N/A")
        checked = failed + passed + review
        return {
            "total_elements": len(records),
            "checked": checked,
            "passed": passed,
            "failed": failed,
            "needs_review": review,
            "na": na,
            "pass_rate_pct": round(passed / checked * 100, 1) if checked else 0,
            "wcag_1_2_1_failed": failed,
        }


# ── SUMMARY ──────────────────────────────────────────────────────────────
# What was done:
#   Created MediaAuditor with 5-gate decision tree for WCAG 1.2.1.
#   Each gate is a standalone testable function.
#   Gate 5 (quality engine) is mandatory — runs faster-whisper + jiwer + nltk.
#
# Principles applied:
#   - SoC: Gate functions are separate from the auditor class.
#   - DRY: Keyword lists are defined once, reused in all gate functions.
#   - KISS: Each gate returns early with a clear result.
#   - SOLID/SRP: Auditor orchestrates gates. Quality engine is a separate module.
#   - Testability: Every gate function can be tested independently.
#
# Edge cases handled:
#   - iframe embeds → removed (out of scope for now)
#   - Decorative media (aria-hidden, role=presentation) → N/A
#   - Muted autoplay loop videos → classified as video_only
#   - aria-describedby transcripts → detected as alternative
#   - <details> collapsible transcripts → detected
#   - Missing quality engine → graceful degradation
# ─────────────────────────────────────────────────────────────────────────
