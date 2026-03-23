"""
ka11y/api/v1/combined/models.py
=================================
Pydantic request / response models for the combined audit endpoint.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, HttpUrl


class CombinedRequest(BaseModel):
    url: HttpUrl
    max_depth: int = 0
    wcag_level: str = "AA"  # "A" | "AA" | "AAA"
    run_ocr: bool = True
    run_image_audit: bool = True
    run_form_audit: bool = True
    run_label_in_name_audit: bool = True
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


class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # pending | running | completed | failed
    url: str
    submitted_at: str
    completed_at: Optional[str] = None
    report_path: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    current_stage: Optional[str] = None
    stages: List[Dict[str, Any]] = []
    warnings: List[str] = []