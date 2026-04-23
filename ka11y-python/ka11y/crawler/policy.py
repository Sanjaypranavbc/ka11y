from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Set, ClassVar
from urllib.parse import urlparse, urlunparse

class CrawlPolicy(BaseModel):
    max_depth: int = 0
    max_pages: int = 10
    max_links_per_page: int = 50
    same_origin: bool = True
    include_subdomains: bool = False
    
    # URL Normalization
    strip_fragments: bool = True
    strip_trailing_slash: bool = True
    
    # Query parameters
    query_allow_list: Set[str] = Field(default_factory=set)
    query_deny_list: Set[str] = Field(default_factory=set)
    canonical_query: bool = True # Sort query params and remove trackers
    
    # Retry budget
    max_retries: int = 3
    
    # Common tracker/junk parameters to strip by default
    TRACKER_PARAMS: ClassVar[Set[str]] = {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "fbclid", "gclid", "_ga", "msclkid", "mc_cid", "mc_eid"
    }

    def normalize_url(self, url: str) -> str:
        if not url:
            return ""
            
        parsed = urlparse(url)
        
        # 1. Scheme and netloc to lowercase
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path
        
        # 2. Strip fragments
        if self.strip_fragments:
            fragment = ""
        else:
            fragment = parsed.fragment
            
        # 3. Strip trailing slash
        if self.strip_trailing_slash and path.endswith("/") and len(path) > 1:
            path = path.rstrip("/")
            
        # 4. Handle query parameters
        query_parts = []
        if parsed.query:
            params = []
            for part in parsed.query.split("&"):
                if "=" in part:
                    key, val = part.split("=", 1)
                else:
                    key, val = part, ""
                
                # Strip tracker params
                if self.canonical_query and key.lower() in self.TRACKER_PARAMS:
                    continue
                
                # Allow/Deny lists
                if self.query_allow_list and key not in self.query_allow_list:
                    continue
                if self.query_deny_list and key in self.query_deny_list:
                    continue
                    
                params.append((key, val))
            
            if self.canonical_query:
                params.sort()
                
            query_parts = [f"{k}={v}" if v else k for k, v in params]
            
        query = "&".join(query_parts)
        
        return urlunparse((scheme, netloc, path, parsed.params, query, fragment))

    def is_allowed(self, url: str, base_url: str) -> bool:
        parsed = urlparse(url)
        base = urlparse(base_url)

        if self.same_origin:
            parsed_host = parsed.hostname
            base_host = base.hostname
            if not parsed_host or not base_host:
                return False
            if self.include_subdomains:
                return parsed_host == base_host or parsed_host.endswith(f".{base_host}")
            else:
                return parsed_host == base_host

        return True
