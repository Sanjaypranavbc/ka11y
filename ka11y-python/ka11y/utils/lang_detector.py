"""
ka11y/utils/lang_detector.py
=============================
Auto-detect the primary language of a web page by reading the ``<html lang="">``
attribute.  Used by the combined audit runner to set the correct i18n context
when the user selects "auto" language mode.

Falls back to ``"en"`` when:
  - The page cannot be fetched (network error, timeout, etc.)
  - No ``<html>`` tag is found
  - No ``lang`` attribute is present
  - The detected language is not in the supported set (currently ``en``, ``ja``)
"""

from __future__ import annotations

import logging
from typing import Set

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Languages for which we have full i18n bundles (reason_templates, UI labels).
# Extend this set when new locale files are added to i18n/locales/.
_SUPPORTED_LANGS: Set[str] = {"en", "ja"}

_DEFAULT_LANG = "en"

# We only need the <html> tag, so limit the download to the first 16 KB.
_MAX_BYTES = 16_384
_TIMEOUT = 10.0


async def detect_page_language(url: str) -> str:
    """
    Fetch the first bytes of *url* and return the normalised language code.

    Returns
    -------
    str
        ``"en"`` or ``"ja"`` (or ``_DEFAULT_LANG`` on failure).
    """
    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            },
        ) as client:
            # Stream so we can cut off after _MAX_BYTES
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                chunks = []
                total = 0
                async for chunk in resp.aiter_bytes(chunk_size=4096):
                    chunks.append(chunk)
                    total += len(chunk)
                    if total >= _MAX_BYTES:
                        break
                html_bytes = b"".join(chunks)

        soup = BeautifulSoup(html_bytes, "html.parser")
        html_tag = soup.find("html")

        if not html_tag or not html_tag.get("lang"):
            logger.info(
                "[lang_detector] No <html lang> attribute found for %s — "
                "defaulting to '%s'",
                url,
                _DEFAULT_LANG,
            )
            return _DEFAULT_LANG

        raw_lang = html_tag["lang"].strip().lower()

        # Normalise BCP-47 subtags: "ja-JP" → "ja", "en-US" → "en"
        primary = raw_lang.split("-")[0]

        if primary in _SUPPORTED_LANGS:
            logger.info(
                "[lang_detector] Detected language '%s' for %s", primary, url
            )
            return primary

        logger.info(
            "[lang_detector] Unsupported language '%s' for %s — "
            "defaulting to '%s'",
            raw_lang,
            url,
            _DEFAULT_LANG,
        )
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
