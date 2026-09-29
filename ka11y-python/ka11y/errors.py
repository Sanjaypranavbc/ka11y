"""
ka11y/errors.py
================
The reporting codes a failed audit may return to a client.

The codes are the whole contract. The wording lives in the UI
(``ka11y-ui/src/lib/i18n/translations.ts``), next to the sign-in errors that
already work this way, so English and Japanese stay in one place and the API
never ships user-facing text.

``AUDIT_ERROR_CODES`` is also an allow-list. The runner reads ``.code`` off
whatever was raised — ``NavigationError``, ``ImageCrawlerNavigationError`` and
``CrawlFailedError`` all carry one — and an unrecognised value is replaced with
``internal_error`` rather than forwarded. Without that, any exception that
happens to have a ``.code`` attribute would put its contents in a response.
"""

from __future__ import annotations

import re
from typing import Any, Optional

# Input validation — the caller sent something unusable.
URL_EMPTY = "url_empty"
URL_MALFORMED = "url_malformed"
URL_MISSING_SCHEME = "url_missing_scheme"
URL_UNSUPPORTED_SCHEME = "url_unsupported_scheme"
URL_INVALID_PORT = "url_invalid_port"
URL_NOT_ALLOWED = "url_not_allowed"

# Network — the target could not be reached.
DNS_RESOLUTION_FAILED = "dns_resolution_failed"
CONNECTION_REFUSED = "connection_refused"
NAVIGATION_TIMEOUT = "navigation_timeout"
NETWORK_UNAVAILABLE = "network_unavailable"

# Redirect / browser.
TOO_MANY_REDIRECTS = "too_many_redirects"
PAGE_NAVIGATION_FAILED = "page_navigation_failed"

# HTTP — the target answered, with an error.
HTTP_NOT_FOUND = "http_not_found"
HTTP_FORBIDDEN = "http_forbidden"
HTTP_SERVER_ERROR = "http_server_error"
HTTP_UNAVAILABLE = "http_unavailable"

# Crawl produced nothing, and no page recorded why.
ZERO_PAGES_CRAWLED = "zero_pages_crawled"

# Fallback.
INTERNAL_ERROR = "internal_error"

AUDIT_ERROR_CODES = frozenset(
    {
        URL_EMPTY,
        URL_MALFORMED,
        URL_MISSING_SCHEME,
        URL_UNSUPPORTED_SCHEME,
        URL_INVALID_PORT,
        URL_NOT_ALLOWED,
        DNS_RESOLUTION_FAILED,
        CONNECTION_REFUSED,
        NAVIGATION_TIMEOUT,
        NETWORK_UNAVAILABLE,
        TOO_MANY_REDIRECTS,
        PAGE_NAVIGATION_FAILED,
        HTTP_NOT_FOUND,
        HTTP_FORBIDDEN,
        HTTP_SERVER_ERROR,
        HTTP_UNAVAILABLE,
        ZERO_PAGES_CRAWLED,
        INTERNAL_ERROR,
    }
)

# Status code → reporting code, for the page the caller actually asked for.
# A sub-page returning 404 is a finding; the seed URL returning 404 is why the
# audit has nothing to report.
HTTP_STATUS_CODES = {
    403: HTTP_FORBIDDEN,
    404: HTTP_NOT_FOUND,
    500: HTTP_SERVER_ERROR,
    503: HTTP_UNAVAILABLE,
}


def code_for_status(status: Optional[int]) -> str:
    """The reporting code for a seed-page HTTP status."""
    if status is None:
        return PAGE_NAVIGATION_FAILED
    if status in HTTP_STATUS_CODES:
        return HTTP_STATUS_CODES[status]
    if 500 <= status <= 599:
        return HTTP_SERVER_ERROR
    if 400 <= status <= 499:
        return HTTP_FORBIDDEN if status == 401 else HTTP_NOT_FOUND
    return PAGE_NAVIGATION_FAILED


def code_of(exc: Any) -> str:
    """The reporting code carried by an exception, or ``internal_error``.

    Only values in ``AUDIT_ERROR_CODES`` pass through. Anything else — an
    unrelated library's ``.code``, a number, an object — is discarded, so a
    response can never carry text this module did not define.
    """
    code = getattr(exc, "code", None)
    return code if code in AUDIT_ERROR_CODES else INTERNAL_ERROR


# Pydantic's own message for a bad URL. Two of the five leaves — a malformed
# value and a value with no scheme — produce the identical text
# "relative URL without a base", so the leaf is settled by looking at the
# input rather than the message.
_URL_CTX_CODES = {
    "input is empty": URL_EMPTY,
    "empty host": URL_MALFORMED,
    "invalid port number": URL_INVALID_PORT,
    "invalid international domain name": URL_MALFORMED,
}

_BARE_HOST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z]{2,}(?::\d+)?(?:/.*)?$")


def classify_validation_error(errors: Any) -> Optional[str]:
    """The code for a FastAPI request-validation failure on a URL field.

    Returns ``None`` when the failure is not about a URL, so unrelated
    endpoints keep FastAPI's default behaviour instead of being given a
    misleading ``url_*`` code.
    """
    for err in errors or []:
        loc = err.get("loc") or ()
        if "url" not in [str(part) for part in loc]:
            continue

        err_type = str(err.get("type", ""))
        if err_type == "missing":
            return URL_EMPTY
        if err_type == "url_scheme":
            return URL_UNSUPPORTED_SCHEME

        raw = err.get("input")
        if isinstance(raw, str) and not raw.strip():
            return URL_EMPTY

        ctx_error = str((err.get("ctx") or {}).get("error", ""))
        for needle, code in _URL_CTX_CODES.items():
            if needle in ctx_error:
                return code

        # "relative URL without a base" covers both leaves. A value that reads
        # as a bare host only lacks the scheme; anything else is malformed.
        if isinstance(raw, str) and _BARE_HOST.match(raw.strip()):
            return URL_MISSING_SCHEME
        return URL_MALFORMED
    return None


# English fallback text for the `error` field. The UI translates `error_code`
# itself; this is only what a client without the code map falls back to, and
# what appears in a raw API response.
VALIDATION_MESSAGES_EN = {
    URL_EMPTY: "A target URL is required.",
    URL_MALFORMED: "The supplied value is not a valid absolute URL.",
    URL_MISSING_SCHEME: (
        "The URL must specify a scheme. An absolute http or https URL is required."
    ),
    URL_UNSUPPORTED_SCHEME: (
        "The URL scheme is not supported. Only http and https are permitted."
    ),
    URL_INVALID_PORT: (
        "The port specified in the URL is outside the permitted range 1-65535."
    ),
}
