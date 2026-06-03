"""
a11y/utils/lang_detector.py
=============================
Auto-detect the primary language of a web page by reading the ``<html lang="">``
attribute.  Used by the combined audit runner to set the correct i18n context
when the user selects "auto" language mode.

Security (N-1): this module makes a server-side HTTP request to a user-supplied
URL *before* the Playwright browser (and its context-level SSRF guard) starts,
so it must do its own SSRF validation. Every hop — the initial URL **and** each
redirect target — is checked with the shared ``_host_is_blocked`` classifier
from :mod:`a11y.crawler._ssrf_guard`, and redirects are followed manually
(``follow_redirects=False``) so an attacker cannot 30x-redirect from a public
host into ``169.254.169.254`` / ``localhost`` / RFC-1918. Residual TOCTOU vs.
the OS resolver is the same documented gap as the browser guard (B-6).

Performance (N-3): results are memoised per host with a TTL so repeated audits
of the same site (or multiple pages on it) skip the extra pre-flight fetch.

Falls back to ``"en"`` when:
  - The host is non-public / fails SSRF validation
  - The page cannot be fetched (network error, timeout, too many redirects)
  - No ``<html>`` tag or no ``lang`` attribute is present
  - The detected language is not in the supported set (currently ``en``, ``ja``)
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Optional, Set
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from a11y.crawler._ssrf_guard import _host_is_blocked

logger = logging.getLogger(__name__)

# Languages for which we have full i18n bundles (reason_templates, UI labels).
# Extend this set when new locale files are added to i18n/locales/.
_SUPPORTED_LANGS: Set[str] = {"en", "ja"}

_DEFAULT_LANG = "en"

# We only need the <html> tag, so limit the download to the first 16 KB.
_MAX_BYTES = 16_384
_TIMEOUT = 10.0
_MAX_REDIRECTS = 5

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Per-host result cache (N-3). Language is a site-wide property in practice, so
# caching by host avoids a second full page fetch on every audit of the same
# domain. Bounded TTL keeps it correct if a site changes its declared language.
_LANG_CACHE_TTL_SECONDS = 600.0
_LANG_CACHE: dict[str, tuple[float, str]] = {}
_LANG_CACHE_LOCK = threading.Lock()


def _cache_get(host: str) -> Optional[str]:
    if not host:
        return None
    now = time.monotonic()
    with _LANG_CACHE_LOCK:
        entry = _LANG_CACHE.get(host)
        if entry is not None and (now - entry[0]) < _LANG_CACHE_TTL_SECONDS:
            return entry[1]
    return None


def _cache_put(host: str, lang: str) -> None:
    if not host:
        return
    with _LANG_CACHE_LOCK:
        if len(_LANG_CACHE) > 4096:
            _LANG_CACHE.clear()
        _LANG_CACHE[host] = (time.monotonic(), lang)


async def _safe_fetch_head(url: str) -> Optional[bytes]:
    """SSRF-guarded fetch of the first ``_MAX_BYTES`` of *url*.

    Redirects are followed **manually** so every hop's host is validated with
    ``_host_is_blocked`` before we connect. Returns the downloaded bytes, or
    ``None`` if the host is non-public, too many redirects occur, or the fetch
    fails.
    """
    current = url
    async with httpx.AsyncClient(
        timeout=_TIMEOUT, follow_redirects=False, headers=_HEADERS
    ) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            host = urlparse(current).hostname or ""
            # Run the (blocking) DNS classification off the event loop.
            if await asyncio.to_thread(_host_is_blocked, host):
                logger.warning(
                    "[lang_detector] refusing to fetch non-public host %r (%s) — "
                    "SSRF guard",
                    host,
                    current,
                )
                return None

            async with client.stream("GET", current) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        return None
                    current = urljoin(current, location)
                    continue

                resp.raise_for_status()
                chunks = []
                total = 0
                async for chunk in resp.aiter_bytes(chunk_size=4096):
                    chunks.append(chunk)
                    total += len(chunk)
                    if total >= _MAX_BYTES:
                        break
                return b"".join(chunks)

    logger.warning("[lang_detector] too many redirects for %s", url)
    return None


async def detect_page_language(url: str) -> str:
    """
    Fetch the first bytes of *url* and return the normalised language code.

    Returns
    -------
    str
        ``"en"`` or ``"ja"`` (or ``_DEFAULT_LANG`` on failure / blocked host).
    """
    host = urlparse(url).hostname or ""
    cached = _cache_get(host)
    if cached is not None:
        return cached

    try:
        html_bytes = await _safe_fetch_head(url)
        if html_bytes is None:
            _cache_put(host, _DEFAULT_LANG)
            return _DEFAULT_LANG

        soup = BeautifulSoup(html_bytes, "html.parser")
        html_tag = soup.find("html")

        if not html_tag or not html_tag.get("lang"):
            logger.info(
                "[lang_detector] No <html lang> attribute found for %s — "
                "defaulting to '%s'",
                url,
                _DEFAULT_LANG,
            )
            _cache_put(host, _DEFAULT_LANG)
            return _DEFAULT_LANG

        raw_lang = html_tag["lang"].strip().lower()

        # Normalise BCP-47 subtags: "ja-JP" → "ja", "en-US" → "en"
        primary = raw_lang.split("-")[0]

        if primary in _SUPPORTED_LANGS:
            logger.info(
                "[lang_detector] Detected language '%s' for %s", primary, url
            )
            _cache_put(host, primary)
            return primary

        logger.info(
            "[lang_detector] Unsupported language '%s' for %s — defaulting to '%s'",
            raw_lang,
            url,
            _DEFAULT_LANG,
        )
        _cache_put(host, _DEFAULT_LANG)
        return _DEFAULT_LANG

    except Exception as exc:
        logger.warning(
            "[lang_detector] Failed to detect language for %s: %s — "
            "defaulting to '%s'",
            url,
            exc,
            _DEFAULT_LANG,
        )
        return _DEFAULT_LANG
