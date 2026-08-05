"""
ka11y/api/v1/combined/models.py
=================================
Pydantic request / response models for the combined audit endpoint.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


# Maps a success_criteria_id to the CombinedRequest flags that must be enabled
# for that SC to produce results. Only flags that exist as active (non-commented)
# fields on CombinedRequest are listed here. Entries for removed/commented-out
# flags have been deleted so validate_success_criteria_dependencies never does
# a getattr() against a nonexistent attribute.
_SC_STAGE_PREREQUISITES = {
    # image / OCR audits
    "1.1.1": ("run_image_audit",),
    "1.4.3": ("run_ocr",),
    "1.4.5": ("run_image_audit",),
    "1.4.6": ("run_ocr",),
    "1.4.11": ("run_image_audit",),
    "4.1.2": ("run_image_audit",),
    # media / captions audits
    "1.2.1": ("run_media_audit",),
    "1.2.2": ("run_captions_audit",),
}


class CombinedRequest(BaseModel):
    url: HttpUrl
    # max_depth: 0 = single-page; capped at 5 to prevent exponential crawl DoS
    max_depth: int = Field(default=0, ge=0, le=5)
    # internal_links: retained as a safeguard. The crawl ALWAYS follows only
    # exact-hostname (domain-specific) links and never leaves the audited domain
    # — in both the Python crawl and the Node BFS — regardless of this flag.
    internal_links: bool = True
    # Hard page budget for the whole crawl (RAM/time ceiling), independent of
    # depth. Accepts up to 200 but is clamped to 20 below — callers never get
    # a validation error for an out-of-policy value, the policy is just applied.
    max_pages: int = Field(default=20, ge=1, le=200)
    # Pattern + max_length on string fields prevents oversized-payload DoS
    wcag_level: str = Field(default="AAA", pattern=r"^(A|AA|AAA)$")
    success_criteria_id: Optional[str] = Field(default=None, pattern=r"^\d+\.\d+\.\d+$")
    # ── Active audit toggles ─────────────────────────────────────────────────
    run_ocr: bool = False
    run_image_audit: bool = True
    run_media_audit: bool = True
    run_captions_audit: bool = True
    lang: str = Field(default="auto", max_length=20, pattern=r"^(auto|[A-Za-z][A-Za-z0-9_-]*)$")

    @field_validator("max_pages")
    @classmethod
    def _cap_max_pages(cls, v: int) -> int:
        return min(v, 20)

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
    # Opaque correlation id for failed jobs. Maps a 5xx response to the
    # server-side log entry that holds the real traceback. Never contains
    # exception type, message, file path, or any other internal detail.
    error_id: Optional[str] = None
    error_stage: Optional[str] = None
    current_stage: Optional[str] = None
    stages: List[Dict[str, Any]] = []
    warnings: List[str] = []
