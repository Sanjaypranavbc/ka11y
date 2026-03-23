from pydantic import BaseModel, HttpUrl

class CrawlRequest(BaseModel):
    url: HttpUrl = "https://www.kao.com/global/en/"
    max_depth: int = 0
    run_ocr: bool = True
    run_audit: bool = True
    run_form_audit: bool = True

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
    # Forms pipeline
    total_fields: int = 0
    form_audit_report: str | None = None
    form_audit_summary: dict | None = None
