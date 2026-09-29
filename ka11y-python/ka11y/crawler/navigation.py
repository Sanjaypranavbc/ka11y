from __future__ import annotations

import asyncio
import socket
import logging
from urllib.parse import urlparse
from playwright.async_api import Page

logger = logging.getLogger("KAC.navigation")

# Standard retryable tokens
_RETRYABLE_NAVIGATION_TOKENS = [
    "ERR_CONNECTION_REFUSED",
    "ERR_CONNECTION_RESET",
    "ERR_CONNECTION_ABORTED",
    "ERR_CONNECTION_CLOSED",
    "ERR_NAME_NOT_RESOLVED",
    "ERR_NETWORK_CHANGED",
    "ERR_TIMED_OUT",
    "ERR_EMPTY_RESPONSE",
    "NS_ERROR_UNKNOWN_HOST",
    "NS_ERROR_NET_TIMEOUT",
    "NS_ERROR_CONNECTION_REFUSED",
    "NS_ERROR_NET_RESET",
    "TIMEOUT",
    "ERR_INTERNET_DISCONNECTED",
    "ERR_ADDRESS_UNREACHABLE",
]

# Browser error token → the code the caller reports. Ordered: the first match
# wins, so the specific tokens come before the ones that are substrings of
# them. Anything unmatched stays "page_navigation_failed".
_CODE_BY_TOKEN = [
    ("ERR_NAME_NOT_RESOLVED", "dns_resolution_failed"),
    ("NS_ERROR_UNKNOWN_HOST", "dns_resolution_failed"),
    ("ERR_CONNECTION_REFUSED", "connection_refused"),
    ("NS_ERROR_CONNECTION_REFUSED", "connection_refused"),
    ("ERR_TOO_MANY_REDIRECTS", "too_many_redirects"),
    ("ERR_INTERNET_DISCONNECTED", "network_unavailable"),
    ("ERR_ADDRESS_UNREACHABLE", "network_unavailable"),
    ("ERR_NETWORK_CHANGED", "network_unavailable"),
    ("ERR_TIMED_OUT", "navigation_timeout"),
    ("NS_ERROR_NET_TIMEOUT", "navigation_timeout"),
    ("TIMEOUT", "navigation_timeout"),
]

# A redirect loop, a bad certificate or a blocked address cannot succeed on a
# second attempt; retrying only spends the raised 60s timeout twice over.
_PERMANENT_NAVIGATION_TOKENS = [
    "ERR_TOO_MANY_REDIRECTS",
    "ERR_CERT_",
    "ERR_SSL_",
    "ERR_BLOCKED_BY_CLIENT",
    "ERR_UNKNOWN_URL_SCHEME",
]

_DNS_PRECHECK_ATTEMPTS = 3
_NAVIGATION_ATTEMPTS = 3
_NAVIGATION_BACKOFF_SECONDS = [1.0, 2.5, 5.0]


class NavigationError(Exception):
    def __init__(
        self,
        code: str,
        url: str,
        host: str | None,
        original_message: str,
        attempts: int,
    ):
        self.code = code
        self.url = url
        self.host = host
        self.original_message = original_message
        self.attempts = attempts
        super().__init__(self._build_message())

    def _build_message(self) -> str:
        host_part = f" host={self.host}" if self.host else ""
        return (
            f"{self.code}{host_part} url={self.url}; navigation failed after "
            f"{self.attempts} attempt(s). Original error: {self.original_message}"
        )


def _host_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    return parsed.hostname or None


def _is_retryable_navigation_error(message: str) -> bool:
    upper = str(message or "").upper()
    if any(token in upper for token in _PERMANENT_NAVIGATION_TOKENS):
        return False
    return any(token in upper for token in _RETRYABLE_NAVIGATION_TOKENS)


def classify_navigation_error(error: object) -> str:
    """The reporting code for a navigation failure.

    The browser already says which of the S2-03 conditions this is; without
    this the caller collapses all of them into "page_navigation_failed" and
    the user is told only that something went wrong.
    """
    upper = str(error or "").upper()
    for token, code in _CODE_BY_TOKEN:
        if token in upper:
            return code
    return "page_navigation_failed"


async def dns_preflight(url: str) -> None:
    host = _host_from_url(url)
    if not host:
        return

    last_error: Exception | None = None
    for attempt in range(1, _DNS_PRECHECK_ATTEMPTS + 1):
        try:
            await asyncio.to_thread(
                socket.getaddrinfo,
                host,
                443,
                0,
                socket.SOCK_STREAM,
            )
            return
        except socket.gaierror as exc:
            last_error = exc
            if attempt >= _DNS_PRECHECK_ATTEMPTS:
                break
            delay = _NAVIGATION_BACKOFF_SECONDS[
                min(attempt - 1, len(_NAVIGATION_BACKOFF_SECONDS) - 1)
            ]
            logger.warning(
                "DNS preflight failed for %s on attempt %s/%s: %s. Retrying in %.1fs",
                host,
                attempt,
                _DNS_PRECHECK_ATTEMPTS,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
        except Exception as exc:
            last_error = exc
            break

    raise NavigationError(
        code="dns_resolution_failed",
        url=url,
        host=host,
        original_message=str(last_error or "unknown DNS resolution error"),
        attempts=_DNS_PRECHECK_ATTEMPTS,
    )


async def navigate_with_resilience(
    page: Page,
    url: str,
    *,
    wait_until: str = "domcontentloaded",
    timeout_ms: int = 30000,
):
    await dns_preflight(url)
    last_error: Exception | None = None
    attempts_used = 0

    for attempt in range(1, _NAVIGATION_ATTEMPTS + 1):
        attempts_used = attempt
        current_timeout = timeout_ms if attempt == 1 else max(timeout_ms, 60000)
        try:
            # The response is returned rather than discarded so the caller can
            # see the HTTP status. A seed page answering 404 or 503 is why an
            # audit has nothing to report, and that was previously invisible.
            return await page.goto(
                url,
                wait_until=wait_until,
                timeout=current_timeout,
            )
        except Exception as exc:
            last_error = exc
            if attempt >= _NAVIGATION_ATTEMPTS:
                break
            if not _is_retryable_navigation_error(str(exc)):
                # Permanent: a second and third attempt cost up to 60s each
                # and cannot change the outcome.
                break

            delay = _NAVIGATION_BACKOFF_SECONDS[
                min(attempt - 1, len(_NAVIGATION_BACKOFF_SECONDS) - 1)
            ]
            logger.warning(
                "Page load failed for %s on attempt %s/%s: %s. Retrying in %.1fs",
                url,
                attempt,
                _NAVIGATION_ATTEMPTS,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
            # Only retryable errors reach here, so the preflight always runs.
            try:
                await dns_preflight(url)
            except Exception:
                pass

    message = str(last_error)
    raise NavigationError(
        code=classify_navigation_error(last_error),
        url=url,
        host=_host_from_url(url),
        original_message=message,
        attempts=attempts_used or 1,
    )
