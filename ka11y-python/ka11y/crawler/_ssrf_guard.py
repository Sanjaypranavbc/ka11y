"""
ka11y/crawler/_ssrf_guard.py
==============================
Bug 1 fix: shared Playwright SSRF route guard for all crawlers.

``build_ssrf_route_handler`` is defined in routes.py but was never actually
wired into any Playwright page or browser context.  This module provides a
standalone async route handler and a helper ``install_ssrf_guard(context)``
that installs the guard on a Playwright browser context so it applies to every
page created from that context (including redirect-following page navigations).

Usage::

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(...)
        await install_ssrf_guard(context)   # ← one call per context
        page = await context.new_page()
        ...
"""

from __future__ import annotations

import ipaddress
import re

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),  # IPv4 loopback
    ipaddress.ip_network("10.0.0.0/8"),  # RFC-1918 class A
    ipaddress.ip_network("172.16.0.0/12"),  # RFC-1918 class B
    ipaddress.ip_network("192.168.0.0/16"),  # RFC-1918 class C
    ipaddress.ip_network("169.254.0.0/16"),  # IPv4 link-local
    ipaddress.ip_network("100.64.0.0/10"),  # Shared address space (RFC 6598)
    ipaddress.ip_network("192.0.0.0/24"),  # IETF protocol assignments
    ipaddress.ip_network("192.0.2.0/24"),  # TEST-NET-1
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),  # TEST-NET-3
    ipaddress.ip_network("0.0.0.0/8"),  # "This" network
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 unique-local
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
    ipaddress.ip_network("::ffff:127.0.0.1/128"),  # IPv4-mapped loopback
]

# Regex to quickly detect literal IP hostnames in URLs (avoids DNS lookup in hot-path)
_IP_HOST_RE = re.compile(r"https?://(\[?[0-9a-fA-F:.]+\]?)(?:[:/]|$)")


def _ip_is_blocked(ip_str: str) -> bool:
    """Return True if *ip_str* falls within any blocked private/reserved network."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    # Use Python's built-in address classification (covers multicast, reserved, etc.)
    # in addition to the explicit CIDR network list for comprehensive coverage.
    if (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    ):
        return True
    return any(addr in net for net in _BLOCKED_NETWORKS)


async def _ssrf_route_handler(route, request) -> None:
    """Playwright route handler: abort requests to private/reserved IPs."""
    url = request.url
    m = _IP_HOST_RE.match(url)
    if m:
        host = m.group(1).strip("[]")
        if _ip_is_blocked(host):
            await route.abort("addressunreachable")
            return
    await route.continue_()


async def install_ssrf_guard(context) -> None:
    """Install the SSRF route guard on a Playwright browser *context*.

    Installing on the context (rather than individual pages) means the guard
    applies automatically to every page created from this context, including
    pages opened via redirects or popup handling.
    """
    await context.route("**/*", _ssrf_route_handler)
