"""
ka11y/api/v1/combined/models.py
=================================
Pydantic request / response models for the combined audit endpoint.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl


class CombinedRequest(BaseModel):
    url: HttpUrl
    # max_depth: 0 = single-page; capped at 5 to prevent exponential crawl DoS
    max_depth: int = Field(default=0, ge=0, le=5)
    # Pattern + max_length on string fields prevents oversized-payload DoS
    # (a 100 MB body in `lang` would otherwise tie up a worker for free).
    wcag_level: str = Field(default="AAA", pattern=r"^(A|AA|AAA)$")
    run_ocr: bool = True
    run_image_audit: bool = True
    run_form_audit: bool = True
    run_label_in_name_audit: bool = True
    run_media_audit: bool = True
    run_pause_stop_hide_audit: bool = True
    run_target_size_audit: bool = True
    # ── Rendered-layout WCAG checks ──────────────────────────────────────────
    run_resize_text_audit: bool = True
    run_reflow_audit: bool = True
    run_text_spacing_audit: bool = True
    run_orientation_audit: bool = True
    run_hover_focus_content_audit: bool = True
    run_focus_not_obscured_min_audit: bool = True
    run_focus_not_obscured_enh_audit: bool = True
    run_sensory_audit: bool = True
    lang: str = Field(default="en", max_length=20, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")


class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # pending | running | completed | failed
    url: str
    submitted_at: str
    lang: str
    completed_at: Optional[str] = None
    report_path: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    # Opaque correlation id for failed jobs. Maps a 5xx response to the
    # server-side log entry that holds the real traceback. Never contains
    # exception type, message, file path, or any other internal detail.
    error_id: Optional[str] = None
    error_stage: Optional[str] = None
    current_stage: Optional[str] = None
    stages: List[Dict[str, Any]] = []
    warnings: List[str] = []
