"""
ka11y/api/v1/combined/models.py
=================================
Pydantic request / response models for the combined audit endpoint.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, model_validator


_SC_STAGE_PREREQUISITES = {
    "1.1.1": ("run_image_audit",),
    "1.2.1": ("run_media_audit",),
    "1.3.4": ("run_orientation_audit",),
    "1.4.3": ("run_ocr",),
    "1.4.4": ("run_resize_text_audit",),
    "1.4.5": ("run_image_audit",),
    "1.4.6": ("run_ocr",),
    "1.4.10": ("run_reflow_audit",),
    "1.4.11": ("run_image_audit",),
    "1.4.12": ("run_text_spacing_audit",),
    "1.4.13": ("run_hover_focus_content_audit",),
    "2.2.2": ("run_pause_stop_hide_audit",),
    "2.4.11": ("run_focus_not_obscured_min_audit",),
    "2.4.12": ("run_focus_not_obscured_enh_audit",),
    "2.5.3": ("run_label_in_name_audit",),
    "2.5.8": ("run_target_size_audit",),
    "3.3.1": ("run_form_audit",),
    "3.3.2": ("run_form_audit",),
    "4.1.2": ("run_image_audit",),
}


class CombinedRequest(BaseModel):
    url: HttpUrl
    # max_depth: 0 = single-page; capped at 5 to prevent exponential crawl DoS
    max_depth: int = Field(default=0, ge=0, le=5)
    wcag_level: str = "AAA"  # "A" | "AA" | "AAA"
    success_criteria_id: Optional[str] = Field(default=None, pattern=r"^\d+\.\d+\.\d+$")
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
    lang: str = "en"

    @model_validator(mode="after")
    def validate_success_criteria_dependencies(self) -> "CombinedRequest":
        sc_id = self.success_criteria_id
        if not sc_id:
            return self

        missing = [
            flag
            for flag in _SC_STAGE_PREREQUISITES.get(sc_id, ())
            if not getattr(self, flag)
        ]
        if missing:
            joined = ", ".join(f"{flag}=true" for flag in missing)
            raise ValueError(
                f"success_criteria_id {sc_id!r} requires {joined}"
            )
        return self


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
    current_stage: Optional[str] = None
    stages: List[Dict[str, Any]] = []
    warnings: List[str] = []
