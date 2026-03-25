from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, HttpUrl


class PipelineRequest(BaseModel):
    url: HttpUrl = "https://www.kao.com/global/en/"
    max_depth: int = Field(default=0, ge=0, le=5)
    run_ocr: bool = True
    run_image_audit: bool = True
    run_form_audit: bool = True
    run_label_in_name_audit: bool = True
    run_pause_stop_hide_audit: bool = True
    run_target_size_audit: bool = True
    run_text_spacing_audit: bool = True


class PipelineResponse(BaseModel):
    status: str
    output_dir: str
    url: str
    max_depth: int
    # Image crawl
    total_images: int
    ocr_dir: Optional[str] = None
    image_audit_report: Optional[str] = None
    image_audit_summary: Optional[Dict[str, Any]] = None
    # ── NEW: contrast analysis ─────────────────────────────────────────────
    contrast_report: Optional[Dict[str, Any]] = None  # structured contrast JSON + table
    # Form crawl
    total_fields: int
    form_audit_report: Optional[str] = None
    form_audit_summary: Optional[Dict[str, Any]] = None
    # WCAG 2.5.3 — Label in Name
    total_interactive_elements: int = 0
    label_in_name_report: Optional[str] = None
    label_in_name_summary: Optional[Dict[str, Any]] = None
    # WCAG 2.2.2 — Pause, Stop, Hide
    total_moving_content_items: int = 0
    pause_stop_hide_report: Optional[str] = None
    pause_stop_hide_summary: Optional[Dict[str, Any]] = None
    # WCAG 2.5.8 — Target Size (Minimum)
    total_target_size_elements: int = 0
    target_size_report: Optional[str] = None
    target_size_summary: Optional[Dict[str, Any]] = None
    # WCAG 1.4.12 — Text Spacing
    total_text_spacing_elements: int = 0
    text_spacing_report: Optional[str] = None
    text_spacing_summary: Optional[Dict[str, Any]] = None
