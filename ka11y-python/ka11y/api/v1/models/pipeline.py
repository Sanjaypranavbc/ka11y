from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, HttpUrl


class PipelineRequest(BaseModel):
    url: HttpUrl = "https://www.kao.com/global/en/"
    max_depth: int = Field(default=0, ge=0, le=5)
    run_ocr: bool = True
    run_image_audit: bool = True


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
    contrast_report: Optional[Dict[str, Any]] = None  # structured contrast JSON + table
