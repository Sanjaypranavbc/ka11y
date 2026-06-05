from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl


class RuleRunRequest(BaseModel):
    url: HttpUrl
    # max_depth: 0 = single-page; capped at 5 to prevent exponential crawl DoS
    max_depth: int = Field(default=0, ge=0, le=5)
    # internal_links: True (default) confines the crawl to the exact base host
    # (domain-specific links only). Retained as a safeguard; the crawl never
    # leaves the audited domain regardless.
    internal_links: bool = True
    # max_pages: hard page budget that keeps a deep crawl memory/time bounded.
    max_pages: int = Field(default=50, ge=1, le=200)
    lang: str = "en"


class RuleUrlOnlyRequest(BaseModel):
    url: HttpUrl
    lang: str = "en"
