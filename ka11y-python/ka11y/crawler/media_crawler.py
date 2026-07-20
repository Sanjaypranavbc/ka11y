"""
ka11y/crawler/media_crawler.py
================================
Data model for time-based media elements.
Feeds the MediaAuditor (WCAG 1.2.1 — Audio-only and Video-only, Prerecorded).

What is extracted per element
─────────────────────────────
  • Media source URL and tag type
  • Child <track> elements (captions, descriptions, subtitles)
  • Nearby <a> links (potential transcript links)
  • Nearby text content (potential inline transcripts)
  • ARIA attributes (aria-hidden, aria-label, aria-describedby, role)
  • Autoplay / controls / muted / loop attributes
  • <details> blocks nearby (collapsible transcript sections)

Extraction itself happens in the shared universal-page JS loader
(``ka11y/crawler/universal_page.py``) — this module only defines the
Pydantic shape of the extracted data for downstream analysis.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel


# ── Data model ────────────────────────────────────────────────────────────────
# One instance per detected media element on the page.


class MediaElementData(BaseModel):
    """Raw data for a single <audio> or <video> media element."""

    page_url: str
    element_index: int

    # ── Identity ──────────────────────────────────────────────────────────
    tag: str  # "AUDIO" | "VIDEO"
    element_id: Optional[str] = None  # HTML id attribute
    src: Optional[str] = None  # media source URL
    html_snippet: str = ""  # outer HTML truncated to 500 chars

    # ── Media attributes ──────────────────────────────────────────────────
    has_autoplay: bool = False
    has_controls: bool = False
    has_loop: bool = False
    is_muted: bool = False

    # ── Track children (<track> elements inside <audio>/<video>) ──────────
    # Each track: {"kind": "captions", "src": "/captions.vtt",
    #              "srclang": "en", "label": "English"}
    tracks: List[Dict[str, Optional[str]]] = []

    # ── ARIA and role attributes ──────────────────────────────────────────
    aria_hidden: bool = False  # aria-hidden="true" → decorative
    role: Optional[str] = None  # role="presentation" → decorative
    aria_label: Optional[str] = None  # explicit accessible name
    aria_describedby_text: Optional[str] = None  # resolved aria-describedby

    # ── Nearby context (for transcript detection in the auditor) ──────────
    # Links in the parent container — the auditor searches these for
    # keywords like "transcript", "text version", etc.
    nearby_links: List[Dict[str, str]] = []  # [{"href": "...", "text": "..."}]

    # Text content of the closest parent container (truncated).
    # Used to detect inline transcripts or "audio version of" labeling.
    nearby_text: str = ""

    # <details> blocks near the media element — common pattern for
    # collapsible transcript sections.
    nearby_details: List[Dict[str, str]] = []  # [{"summary": "...", "content": "..."}]

    selector: Optional[str] = None
    element_ref_id: Optional[str] = None
    frame_path: Optional[str] = None
