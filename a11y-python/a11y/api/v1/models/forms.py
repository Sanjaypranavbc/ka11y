from pydantic import BaseModel, Field, HttpUrl


class FormsRequest(BaseModel):
    url: HttpUrl = "https://www.kao.com/global/en/"
    max_depth: int = Field(default=0, ge=0, le=5)
    run_audit: bool = True


class FormsResponse(BaseModel):
    status: str
    output_dir: str
    url: str
    max_depth: int
    total_fields: int
    audit_report: str | None = None
    audit_summary: dict | None = None
