"""
a11y/utils/url_canonical.py
============================
Conservative URL canonicalisation used at every site where a page_url is
stamped on a finding.

Why this exists
---------------
When the page-wise report UI groups findings by ``element.page_url``, two URLs
that the user considers identical (``https://example.com/about`` and
``https://example.com/about/``) must reduce to the same string — otherwise
they appear as two separate page tabs. The Python and Node engines, the
universal snapshot, and the image crawler all need to agree on that string.

What we normalise
-----------------
* Strip the fragment (``#section`` is never page-identifying)
* Lowercase the host (``Example.com`` → ``example.com``)
* Drop default ports (``:80`` for http, ``:443`` for https)
* Drop a trailing ``/`` on non-root paths (``/about/`` → ``/about``, root
  ``/`` stays)
* Drop a trailing ``/index.html`` / ``/index.htm`` from the path
  (``/about/index.html`` → ``/about``)

What we **don't** normalise (yet)
---------------------------------
* Trailing ``.html`` on arbitrary paths — ``/about`` and ``/about.html`` are
  *different* URLs on most servers, so stripping ``.html`` blindly is unsafe.
  The kao.com ``/worldwide`` vs ``/worldwide.html`` collision needs a
  per-page ``<link rel="canonical">`` scrape — deferred.
* Query parameter ordering — some sites use position-sensitive query strings.
* Percent-encoding case — case differs but encoded values match; treating
  them as identical needs full re-encoding which is the wrong default.

Safety
------
* No network calls.
* Never raises: a malformed URL is returned unchanged so callers can keep
  using it as an opaque key.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

_DEFAULT_PORTS = {
    "http": 80,
    "https": 443,
}

_INDEX_SUFFIXES = ("/index.html", "/index.htm")


def canonicalize_url(url: str) -> str:
    """
    Return a canonicalised form of ``url`` suitable for use as a page identity
    key. Idempotent — running it twice yields the same result.

    >>> canonicalize_url("HTTPS://Example.com:443/About/#contact")
    'https://example.com/About'
    >>> canonicalize_url("https://example.com/")
    'https://example.com/'
    >>> canonicalize_url("https://example.com/dir/index.html")
    'https://example.com/dir'
    """
    if not isinstance(url, str) or not url:
        return url

    try:
        parts = urlsplit(url)
    except ValueError:
        return url

    scheme = (parts.scheme or "").lower()
    if scheme not in ("http", "https"):
        # Leave non-http(s) URLs alone — e.g. ``mailto:``, ``tel:``, ``data:``.
        return url

    # Hostname: lowercase, strip default port, keep userinfo intact (rare in
    # crawled URLs but technically valid).
    hostname = (parts.hostname or "").lower()
    if not hostname:
        return url

    userinfo = ""
    if parts.username is not None:
        userinfo = parts.username
        if parts.password is not None:
            userinfo = f"{userinfo}:{parts.password}"
        userinfo = f"{userinfo}@"

    port_part = ""
    if parts.port is not None and parts.port != _DEFAULT_PORTS.get(scheme):
        port_part = f":{parts.port}"

    netloc = f"{userinfo}{hostname}{port_part}"

    # Path: strip /index.html or /index.htm; strip trailing slash on non-root.
    path = parts.path or "/"
    lower_path = path.lower()
    for suffix in _INDEX_SUFFIXES:
        if lower_path.endswith(suffix):
            path = path[: -len(suffix)] or "/"
            break
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]

    # Drop the fragment entirely; keep the query as-is.
    return urlunsplit((scheme, netloc, path, parts.query, ""))


__all__ = ["canonicalize_url"]
