from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field, HttpUrl

class RuleRunRequest(BaseModel):
    url: HttpUrl
    # max_depth: 0 = single-page; capped at 5 to prevent exponential crawl DoS
    max_depth: int = Field(default=0, ge=0, le=5)
    lang: str = "en"
