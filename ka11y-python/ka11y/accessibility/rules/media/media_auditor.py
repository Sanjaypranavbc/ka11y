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

    # Explicit live labeling. Genuine live badges/labels are short
    # ("Live", "LIVE NOW", "Watch Live") — scanning arbitrary long prose in
    # `nearby_text` for the bare word "live" false-matches ordinary sentences
    # like "This interview was recorded live in our studio last year and is
    # now archived", wrongly exempting prerecorded media that actually needs
    # a transcript. Cap the scan to short, label-like text.
    _LIVE_LABEL_MAX_LEN = 40
    for text in [aria_label, nearby_text]:
        if not text or len(text) > _LIVE_LABEL_MAX_LEN:
            continue
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
      "synchronized"  — <video> tag with strong indicators of audio + video
      "unknown"       — <video> tag with no reliable signal either way

    Note: Accurately detecting whether a <video> has an audio track
    requires JS media API access (audioTracks / webkitAudioDecodedByteCount),
    which is generally unpopulated until the browser has actually started
    loading the media — not reliably available from a static crawl pass. The
    crawler extracts `is_muted` / `has_loop` / `has_autoplay` as heuristic
    hints only.
    """
    tag = (item.get("tag") or "").upper()

    if tag == "AUDIO":
        return "audio_only"

    if tag == "VIDEO":
        is_muted = item.get("is_muted", False)
        has_loop = item.get("has_loop", False)
        has_autoplay = item.get("has_autoplay", False)

        # Muted autoplay loop = likely decorative/video-only background.
        if is_muted and has_loop and has_autoplay:
            return "video_only"

        # Default assumption: synchronized media. This is a deliberate
        # prior, not a certainty — most <video> elements do carry audio, and
        # assuming otherwise by default would misroute the common case away
        # from the (much more frequently applicable and already
        # well-covered) 1.2.2 captions pipeline. The known gap this leaves —
        # a silent, non-autoplaying, click-to-play video with no muted/loop
        # signal is indistinguishable from a normal synchronized video using
        # only static HTML attributes — is called out explicitly in the
        # 1.2.1 N/A reason text below (see `_audit_single`) rather than
        # silently asserted, so a reviewer skimming results can tell this
        # was a default, not a confirmed fact. A real fix needs an actual
        # audio-track check (`audioTracks`/`webkitAudioDecodedByteCount`),
        # which requires the browser to have started loading the media —
        # not reliably available from a static crawl pass.
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

    Returns ("N/A", reason, 3) if exempt, ("NEEDS_REVIEW", reason, 3) if the
    signal is weaker (see below), else None to continue.
    """
    aria_label = _normalize(item.get("aria_label") or "")
    nearby_text = _normalize(item.get("nearby_text") or "")

    # `aria_label` is a deliberate, author-set accessible name — a keyword
    # match there is a trustworthy, high-confidence signal, so it's a
    # confident exemption.
    for keyword in _MEDIA_ALT_KEYWORDS:
        if keyword in aria_label:
            return (
                "N/A",
                f"Media is a clearly labeled alternative for existing text content "
                f"(matched: '{keyword}' in its accessible name). Exempt from 1.2.1.",
                3,
            )

    # `nearby_text` is arbitrary surrounding prose, not a deliberate label —
    # a substring match there can be a coincidental mention (e.g. unrelated
    # accessibility-statement boilerplate near the element) rather than the
    # media actually being a labeled alternative. Confidently exempting
    # every such match previously hid genuine missing-transcript violations
    # behind an authoritative-looking N/A with no way to tell it was a
    # guess. Surface it as NEEDS_REVIEW instead so a human confirms it.
    for keyword in _MEDIA_ALT_KEYWORDS:
        if keyword in nearby_text:
            return (
                "NEEDS_REVIEW",
                f"Nearby text mentions '{keyword}', which may mean this media is "
                "a labeled alternative for existing text content (exempt from "
                "1.2.1) — or may be an unrelated, coincidental mention. Confirm "
                "whether this media is genuinely a text alternative.",
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
        status_code = resp.status_code

        # A server that blanket-405s HEAD requests (including for files that
        # don't exist) would previously make ANY track URL pass Gate 5
        # unconditionally — including genuinely broken ones. Retry with GET
        # (streamed, closed immediately without reading the body) so a real
        # 404/500 on such a server is still caught here rather than only
        # surfacing later as a silent downgrade to NEEDS_REVIEW when the
        # download-and-parse step fails.
        if status_code == 405:
            get_resp = requests.get(track_url, timeout=5, allow_redirects=True, stream=True)
            status_code = get_resp.status_code
            get_resp.close()

        if status_code >= 400:
            if status_code == 404:
                return ("FAILED", f"Caption file URL returned 404 Not Found: {track_url} (F8 violation)", 5)
            return ("FAILED", f"Caption file URL returned HTTP error {status_code}: {track_url} (F8 violation)", 5)
    except Exception as e:
        # Network errors = broken link
        return ("FAILED", f"Caption file URL is unreachable: {str(e)} (F8 violation)", 5)

    return None


# ─────────────────────────────────────────────────────────────────────────────
# WCAG 1.2.3 — Audio Description or Media Alternative (Prerecorded), Level A
# ─────────────────────────────────────────────────────────────────────────────


def _check_1_2_3_audio_description(
    item: Dict[str, Any], tracks: List[Dict[str, Any]]
) -> Tuple[str, str]:
    """
    WCAG 1.2.3: Synchronized video must have either an audio-description
    track (or equivalent full alternative) for visual-only information, or
    be exempt because that information is already conveyed in the audio.

    Whether a given video's visual track carries information the audio
    doesn't (e.g. on-screen text, a silent demonstration) is a judgment call
    this auditor cannot make automatically — most synchronized video (talking-
    head interviews, screencasts with narration) needs no audio description
    at all, so a blanket FAILED here would be a false positive on the
    majority of ordinary video content. This mirrors the same automation
    ceiling already documented for judgment-heavy criteria elsewhere in this
    codebase (e.g. WCAG 2.5.4's "all findings need manual review").

    Returns (status, violation_message).
    """
    for track in tracks:
        kind = _normalize(track.get("kind") or "")
        if kind == "descriptions":
            return (
                "PASSED",
                f"Video has an audio-description track ({track.get('src') or 'inline'}).",
            )

    gate3 = _gate_3_is_labeled_alternative(item)
    if gate3:
        _, violation, _ = gate3
        return ("N/A", violation)

    return (
        "NEEDS_REVIEW",
        "No <track kind=\"descriptions\"> found. WCAG 1.2.3 requires audio "
        "description (or a full text/media alternative) ONLY if the video "
        "track conveys information not already available from the audio "
        "(e.g. on-screen text, a silent demonstration) — confirm whether "
        "that applies to this video.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# WCAG 1.4.2 — Audio Control, Level A
# ─────────────────────────────────────────────────────────────────────────────


def _check_1_4_2_audio_control(item: Dict[str, Any]) -> Tuple[str, str]:
    """
    WCAG 1.4.2: Audio that plays automatically for more than 3 seconds must
    be either mutable/stoppable independently of the system volume, or not
    play audibly without user action in the first place.

    Reuses attributes the crawler already captures (has_autoplay, is_muted,
    has_controls) — no new capture step required. Cannot detect a custom
    (non-native-`controls`) pause/stop mechanism implemented in JS elsewhere
    on the page, or the exact clip duration (the native-`<3s`-exemption), so
    a FAIL here is reported as a strong (F23-pattern) signal, not an
    absolute — the message says so.

    Returns (status, violation_message).
    """
    if not item.get("has_autoplay"):
        return ("N/A", "Media does not autoplay. WCAG 1.4.2 does not apply.")

    if item.get("is_muted"):
        return (
            "PASSED",
            "Media autoplays muted — no audio plays automatically, so WCAG "
            "1.4.2 does not require a stop/pause mechanism.",
        )

    if item.get("has_controls"):
        return (
            "PASSED",
            "Media autoplays with audible sound, but native playback "
            "controls (which include pause and volume) are present, "
            "satisfying WCAG 1.4.2.",
        )

    tag = (item.get("tag") or "media").lower()
    return (
        "FAILED",
        f"This {tag} autoplays with audible sound and has no native "
        "controls attribute. WCAG 1.4.2 requires a way to pause, stop, or "
        "independently control the volume of automatically-playing audio "
        "(F23 failure pattern). If a custom pause/mute control exists "
        "elsewhere on the page (implemented in JS rather than the native "
        "`controls` attribute), verify it before treating this as a "
        "confirmed violation.",
    )


def _download_and_parse_vtt(track_url: str) -> Optional[str]:
    """
    Downloads a VTT or SRT file and strips out timestamps, tags, and IDs to return pure spoken text.
    """
    try:
        resp = requests.get(track_url, timeout=10)
        resp.raise_for_status()
        text = resp.text
        
        # Simple VTT/SRT parser
        lines = text.splitlines()
        spoken_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.upper() == "WEBVTT":
                continue
            # Match timestamp lines like 00:00:00.000 --> 00:00:02.000
            if "-->" in line:
                continue
            # Match just numeric IDs
            if line.isdigit():
                continue
            # Strip simple HTML tags like <b>, <i>, <font>
            line = re.sub(r'<[^>]+>', '', line)
            # Remove any inline styling like <c.color>
            line = re.sub(r'<c[^>]*>', '', line)
            line = line.replace('</c>', '')
            spoken_lines.append(line)
            
        return " ".join(spoken_lines)
    except Exception as e:
        logger.warning(f"Failed to download and parse VTT from {track_url}: {e}")
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
        "wcag_1_2_3_status",
        "wcag_1_2_3_violation",
        "wcag_1_4_2_status",
        "wcag_1_4_2_violation",
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
            "wcag_1_2_3_status": "N/A",
            "wcag_1_2_3_violation": "",
            "wcag_1_4_2_status": "N/A",
            "wcag_1_4_2_violation": "",
            "html_snippet": (item.get("html_snippet") or "")[:400],
            "transcript_type": None,
            "transcript_url_or_text": None,
            "quality_report": None,
            "selector": item.get("selector"),
            "element_ref_id": item.get("element_ref_id"),
            "frame_path": item.get("frame_path"),
        }

        # ── WCAG 1.4.2 (Audio Control) ──────────────────────────────────────
        # Applies to any automatically-playing audio regardless of live/
        # prerecorded status or media type classification, so it's computed
        # independently of (and before) the 1.2.1/1.2.2/1.2.3 gate pipeline
        # below, which all only apply to prerecorded content.
        status_1_4_2, violation_1_4_2 = _check_1_4_2_audio_control(item)
        base["wcag_1_4_2_status"] = status_1_4_2
        base["wcag_1_4_2_violation"] = violation_1_4_2

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

        # Synchronized media → 1.2.1 does not apply.
        #
        # NOTE: `_gate_2_media_type` only returns "synchronized" as a
        # default assumption, not a confirmed fact — static HTML attributes
        # give no reliable signal for real audio-track presence outside the
        # confident muted+loop+autoplay video-only pattern (handled
        # separately, above). It defaults to "synchronized" deliberately
        # (most <video> elements do carry audio, and flipping the default
        # would misroute the common case away from the 1.2.2 captions
        # pipeline), but that means a genuinely silent, non-autoplaying,
        # click-to-play video is indistinguishable from a normal
        # synchronized one here — the reason text says so explicitly rather
        # than silently asserting confidence.
        if media_type == "synchronized":
            base.update({
                "wcag_1_2_1_status": "N/A",
                "wcag_1_2_1_violation": (
                    "Assumed synchronized media (no muted+loop+autoplay "
                    "video-only signal detected) — WCAG 1.2.1 is reported "
                    "N/A on that assumption. If this video is actually "
                    "silent, it needs a 1.2.1 text/audio alternative "
                    "instead; static HTML attributes cannot confirm "
                    "audio-track presence either way. See 1.2.2 / 1.2.3."
                ),
                "wcag_1_2_1_gate_reached": 2,
            })

            # ── WCAG 1.2.3 (Audio Description or Media Alternative) ─────────
            # Cheap (track/label inspection only, no network/transcription),
            # so it always runs for synchronized media regardless of the
            # run_1_2_2 flag below.
            status_1_2_3, violation_1_2_3 = _check_1_2_3_audio_description(
                item, item.get("tracks") or []
            )
            base["wcag_1_2_3_status"] = status_1_2_3
            base["wcag_1_2_3_violation"] = violation_1_2_3

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
                
            # Gate 6: Deepgram Caption Verification
            track_kind = track_info["kind"]
            
            # Fetch and parse the VTT/SRT text
            caption_text = _download_and_parse_vtt(track_url)
            media_url = item.get("src")
            
            if not caption_text or not media_url:
                review_msg = (
                    f"Video has a valid <track kind=\"{track_kind}\"> but we could not "
                    "download the media or captions to automatically verify accuracy. "
                    "Human review required."
                )
                base.update({
                    "wcag_1_2_2_status": "NEEDS_REVIEW",
                    "wcag_1_2_2_violation": review_msg, 
                    "wcag_1_2_2_gate_reached": 6,
                })
                return base
                
            from ka11y.accessibility.rules.media.quality_engine import evaluate_captions_quality
            
            report = evaluate_captions_quality(
                media_url=media_url,
                caption_text=caption_text,
                output_dir=str(self.output_dir),
                lang=self.lang
            )
            
            base["quality_report"] = report
            status = report["overall_status"]
            message = report["message"]

            # WCAG 1.2.2 requires *captions* — dialogue text AND non-speech
            # audio cues (music, sound effects, speaker changes). A
            # kind="subtitles" track is only required to carry translated
            # dialogue, so Gate 6's word-error-rate check above (dialogue
            # accuracy only) confirms the track matches the audio but can't
            # confirm non-speech cues are present. Accepting "subtitles" at
            # Gate 4 avoids false-failing the common real-world pattern of
            # compliant tracks mislabeled kind="subtitles", but a clean WER
            # score alone shouldn't be reported as a confident 1.2.2 PASS —
            # cap it at NEEDS_REVIEW so a reviewer confirms non-speech
            # cues are covered.
            if track_kind == "subtitles" and status in ("PASS", "PASSED"):
                status = "NEEDS_REVIEW"
                message = (
                    f"{message} Track is kind=\"subtitles\" — dialogue "
                    "accuracy checked, but WCAG 1.2.2 captions must also "
                    "describe non-speech audio (music, sound effects, "
                    "speaker changes); confirm those are covered or change "
                    "the track to kind=\"captions\"."
                )

            base.update({
                "wcag_1_2_2_status": status,
                "wcag_1_2_2_violation": message,
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
