from pydantic import BaseModel, Field, HttpUrl


class CrawlRequest(BaseModel):
    url: HttpUrl = "https://www.kao.com/global/en/"
    max_depth: int = Field(default=0, ge=0, le=5)
    run_ocr: bool = True
    run_audit: bool = True


class CrawlResponse(BaseModel):
    status: str
    output_dir: str
    url: str
    max_depth: int
    # Image pipeline
    total_images: int = 0
    ocr_dir: str | None = None
    audit_report: str | None = None
    audit_summary: dict | None = None
