"""Unit tests for the hardened SSRF guard.

Covers the encoded-IP bypass class that the previous regex-based guard
missed: decimal, hexadecimal, octal IPv4 forms, and IPv4-mapped IPv6.
"""

from __future__ import annotations

import pytest

from ka11y.crawler import _ssrf_guard as guard


class TestParseLiteralIp:
    @pytest.mark.parametrize(
        "host,expected",
        [
            ("127.0.0.1", "127.0.0.1"),
            ("10.0.0.1", "10.0.0.1"),
            ("169.254.169.254", "169.254.169.254"),  # AWS metadata
            ("::1", "::1"),
            ("[::1]", "::1"),
            # Decimal-encoded IPv4 (the classic SSRF bypass)
            ("2130706433", "127.0.0.1"),
            ("3232235521", "192.168.0.1"),
            # Hex-encoded
            ("0x7f000001", "127.0.0.1"),
            ("0X7F000001", "127.0.0.1"),
            # Octal-encoded (single integer; per-octet octal is too platform-
            # dependent to support here — Python's int(_, 0) handles 0o.. only).
            ("0o17700000001", "127.0.0.1"),
        ],
    )
    def test_recognises_literal_forms(self, host, expected):
        result = guard._parse_literal_ip(host)
        assert result is not None, f"Failed to parse {host!r} as IP"
        assert str(result) == expected

    @pytest.mark.parametrize(
        "host",
        ["example.com", "cdn.cloudflare.com", "internal.corp", ""],
    )
    def test_returns_none_for_hostnames(self, host):
        assert guard._parse_literal_ip(host) is None


class TestClassifyBlocked:
    @pytest.mark.parametrize(
        "ip",
        [
            "127.0.0.1",  # loopback
            "10.0.0.1",  # RFC-1918 A
            "172.16.0.1",  # RFC-1918 B
            "192.168.0.1",  # RFC-1918 C
            "169.254.169.254",  # link-local / AWS metadata
            "100.64.0.1",  # CGNAT
            "0.0.0.0",  # unspecified
            "224.0.0.1",  # multicast
            "::1",  # IPv6 loopback
            "fe80::1",  # IPv6 link-local
            "fc00::1",  # IPv6 unique-local
            # IPv4-mapped IPv6: must NOT escape via the v6 form
            "::ffff:127.0.0.1",
            "::ffff:10.0.0.1",
            "::ffff:169.254.169.254",
        ],
    )
    def test_blocks_private_and_reserved(self, ip):
        assert guard._ip_is_blocked(ip), f"{ip} should be blocked"

    @pytest.mark.parametrize(
        "ip",
        [
            "8.8.8.8",
            "1.1.1.1",
            "93.184.216.34",  # example.com at the time of writing
            "2606:4700:4700::1111",  # public Cloudflare IPv6
        ],
    )
    def test_allows_public(self, ip):
        assert not guard._ip_is_blocked(ip), f"{ip} should be allowed"


class TestHostIsBlocked:
    def test_localhost_aliases_blocked(self):
        for h in ("localhost", "Localhost", "LOCALHOST", "ip6-localhost"):
            assert guard._host_is_blocked(h), h

    def test_decimal_encoded_loopback_blocked(self):
        # The exact bypass that the old regex missed.
        assert guard._host_is_blocked("2130706433")

    def test_hex_encoded_loopback_blocked(self):
        assert guard._host_is_blocked("0x7f000001")

    def test_aws_metadata_literal_blocked(self):
        assert guard._host_is_blocked("169.254.169.254")

    def test_ipv4_mapped_ipv6_loopback_blocked(self):
        assert guard._host_is_blocked("::ffff:127.0.0.1")

    def test_empty_host_not_blocked(self):
        # Empty / missing host is rejected by the URL parser separately;
        # this guard should not crash on it.
        assert not guard._host_is_blocked("")
