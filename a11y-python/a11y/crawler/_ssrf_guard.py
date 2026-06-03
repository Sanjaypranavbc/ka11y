"""
a11y/crawler/_ssrf_guard.py
==============================
Playwright route guard that blocks requests targeting non-public IPs.

Hardening (vs. the prior version):

1. **Encoded-IP coverage.** `http://2130706433/`, `http://0x7f000001/`,
   `http://0177.0.0.1/`, and IPv4-mapped IPv6 (`http://[::ffff:7f00:0001]/`)
   all resolve to ``127.0.0.1``. The earlier dotted-quad regex matched none
   of them. ``_resolve_host_to_ips`` now normalises every form via
   :func:`ipaddress.ip_address` and ``int(host, 0)``.

2. **Hostname resolution.** Even a perfectly innocuous hostname can resolve
   to an internal IP (DNS rebinding, internal-routed cloud DNS, etc.). The
   handler now performs a cached ``getaddrinfo`` for non-literal hosts and
   blocks if **any** answer is private/reserved.

3. **Single classification source.** ``_ip_is_blocked`` consults Python's
   own address attributes plus an explicit blocklist *and* recurses into
   ``ipv4_mapped`` for IPv6 forms, so attempts to launder via
   ``::ffff:10.0.0.1`` are caught.

The handler installed via ``install_ssrf_guard(context)`` runs for every
request issued by every page in the context — including redirect targets,
which Playwright dispatches as fresh requests.
"""

from __future__ import annotations

import ipaddress
import socket
import threading
import time
from typing import Optional
from urllib.parse import urlparse

# DNS answers are cached for at most this many seconds. A *bounded* TTL is a
# deliberate hardening choice: the prior implementation used an unbounded
# ``lru_cache``, so once a hostname resolved to a public IP it was trusted for
# the life of the process. An attacker controlling a domain could let it
# resolve public on first contact, then rebind it to ``169.254.169.254``; the
# guard would keep serving the stale "public" answer forever. Re-resolving on a
# short TTL shrinks that DNS-rebinding window to a few seconds.
#
# This does NOT fully close the time-of-check/time-of-use gap against
# Chromium's *own* resolver (Chromium resolves independently when it actually
# connects); fully closing that requires fetching via a pinned IP. It does
# prevent the guard itself from being permanently poisoned.
_DNS_CACHE_TTL_SECONDS = 30.0

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),  # IPv4 loopback
    ipaddress.ip_network("10.0.0.0/8"),  # RFC-1918 class A
    ipaddress.ip_network("172.16.0.0/12"),  # RFC-1918 class B
    ipaddress.ip_network("192.168.0.0/16"),  # RFC-1918 class C
    ipaddress.ip_network("169.254.0.0/16"),  # IPv4 link-local (incl. AWS metadata)
    ipaddress.ip_network("100.64.0.0/10"),  # Shared address space (RFC 6598)
    ipaddress.ip_network("192.0.0.0/24"),  # IETF protocol assignments
    ipaddress.ip_network("192.0.2.0/24"),  # TEST-NET-1
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),  # TEST-NET-3
    ipaddress.ip_network("0.0.0.0/8"),  # "This" network
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 unique-local
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]


def _classify_blocked(addr: ipaddress._BaseAddress) -> bool:
    if (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    ):
        return True
    if any(addr in net for net in _BLOCKED_NETWORKS):
        return True
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return _classify_blocked(addr.ipv4_mapped)
    return False


def _ip_is_blocked(ip_str: str) -> bool:
    """True if *ip_str* (any literal form) belongs to a blocked range."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return _classify_blocked(addr)


def _parse_literal_ip(host: str) -> Optional[ipaddress._BaseAddress]:
    """Return an IP address for any literal form of *host* — dotted quad,
    IPv6, IPv4-mapped, or pure-decimal/hex/octal integer (the encodings the
    old regex missed). Returns None if *host* is a hostname."""
    if not host:
        return None
    cleaned = host.strip("[]")
    try:
        return ipaddress.ip_address(cleaned)
    except ValueError:
        pass
    # Integer encodings: pure decimal (e.g. 2130706433) or explicit base
    # prefix (0x.., 0o.., 0b..). Only these two shapes are accepted so a
    # real hostname like ``cdn.example.com`` (which contains hex digits
    # like ``e``) never accidentally parses as an integer.
    is_pure_decimal = cleaned.isdigit()
    has_base_prefix = (
        len(cleaned) >= 2
        and cleaned[0] == "0"
        and cleaned[1] in "xXoObB"
    )
    if is_pure_decimal or has_base_prefix:
        try:
            value = int(cleaned, 0)
        except ValueError:
            return None
        try:
            return ipaddress.ip_address(value)
        except (ValueError, OverflowError):
            return None
    return None


_dns_cache: dict[str, tuple[float, tuple[str, ...]]] = {}
_dns_cache_lock = threading.Lock()


def _resolve_hostname(host: str) -> tuple[str, ...]:
    """TTL-bounded DNS lookup. Returns the tuple of IP-string answers.

    Entries expire after :data:`_DNS_CACHE_TTL_SECONDS` so a host that rebinds
    to a private IP after first contact is re-checked rather than trusted
    indefinitely (see module docstring on the TTL).
    """
    now = time.monotonic()
    with _dns_cache_lock:
        cached = _dns_cache.get(host)
        if cached is not None and (now - cached[0]) < _DNS_CACHE_TTL_SECONDS:
            return cached[1]

    try:
        infos = socket.getaddrinfo(host, None, 0, socket.SOCK_STREAM)
    except socket.gaierror:
        infos = []
    seen: list[str] = []
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        ip = sockaddr[0]
        if ip not in seen:
            seen.append(ip)
    answers = tuple(seen)

    with _dns_cache_lock:
        # Bound memory: drop the whole cache if it grows pathologically large
        # rather than carrying an LRU; the working set of audited hosts is small.
        if len(_dns_cache) > 4096:
            _dns_cache.clear()
        _dns_cache[host] = (now, answers)
    return answers


def _host_is_blocked(host: str) -> bool:
    """True if *host* (literal IP or hostname) resolves to any blocked IP."""
    if not host:
        return False
    if host.lower() in ("localhost", "ip6-localhost", "ip6-loopback"):
        return True
    literal = _parse_literal_ip(host)
    if literal is not None:
        return _classify_blocked(literal)
    # Hostname: resolve and block if ANY answer is non-public.
    for ip in _resolve_hostname(host):
        try:
            if _classify_blocked(ipaddress.ip_address(ip)):
                return True
        except ValueError:
            continue
    return False


async def _ssrf_route_handler(route, request) -> None:
    """Playwright route handler: abort requests to private/reserved IPs.

    Redirect targets are delivered to this handler as new requests, so a
    public page redirecting to ``http://169.254.169.254/`` is caught even
    though only the original URL passed the entry-point check.
    """
    parsed = urlparse(request.url)
    host = parsed.hostname or ""
    if _host_is_blocked(host):
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
