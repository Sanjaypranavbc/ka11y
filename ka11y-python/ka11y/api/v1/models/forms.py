from pydantic import BaseModel, HttpUrl

class FormsRequest(BaseModel):
    url: HttpUrl = "https://www.kao.com/global/en/"
    max_depth: int = 0
    run_audit: bool = True

class FormsResponse(BaseModel):
    status: str
    output_dir: str
    url: str
    max_depth: int
    total_fields: int
    audit_report: str | None = None
    audit_summary: dict | None = None
