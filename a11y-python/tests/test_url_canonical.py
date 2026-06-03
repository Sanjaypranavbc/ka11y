from __future__ import annotations

import pytest

from a11y.utils.url_canonical import canonicalize_url


class TestCanonicalizeUrl:
    def test_idempotent(self):
        # Running canonicalisation twice must produce the same string —
        # otherwise dedup keys would shift between merge passes.
        canon = canonicalize_url("HTTPS://Example.com:443/About/#section")
        assert canonicalize_url(canon) == canon

    def test_strips_fragment(self):
        assert canonicalize_url("https://example.com/a#section") == "https://example.com/a"

    def test_lowercases_host_only(self):
        # Host is case-insensitive; path is not.
        assert (
            canonicalize_url("https://Example.com/About") == "https://example.com/About"
        )

    def test_drops_default_https_port(self):
        assert canonicalize_url("https://example.com:443/x") == "https://example.com/x"

    def test_drops_default_http_port(self):
        assert canonicalize_url("http://example.com:80/x") == "http://example.com/x"

    def test_keeps_non_default_port(self):
        assert (
            canonicalize_url("https://example.com:8443/x") == "https://example.com:8443/x"
        )

    def test_strips_trailing_slash_on_non_root(self):
        assert canonicalize_url("https://example.com/a/") == "https://example.com/a"

    def test_keeps_trailing_slash_on_root(self):
        # Root "/" is meaningful — stripping it would create the empty path
        # which urlunsplit then serialises as no slash at all.
        assert canonicalize_url("https://example.com/") == "https://example.com/"

    def test_strips_index_html(self):
        assert (
            canonicalize_url("https://example.com/dir/index.html")
            == "https://example.com/dir"
        )

    def test_strips_index_htm(self):
        assert (
            canonicalize_url("https://example.com/dir/index.htm")
            == "https://example.com/dir"
        )

    def test_does_not_strip_arbitrary_html(self):
        # /about and /about.html are *different* resources on most servers.
        # The kao.com worldwide vs worldwide.html collision needs a per-page
        # <link rel="canonical"> scrape — see module docstring.
        assert (
            canonicalize_url("https://example.com/about.html")
            == "https://example.com/about.html"
        )

    def test_preserves_query(self):
        assert (
            canonicalize_url("https://example.com/x?a=1&b=2")
            == "https://example.com/x?a=1&b=2"
        )

    def test_leaves_non_http_scheme_alone(self):
        # Don't touch mailto:, tel:, data: — they have their own grammar.
        assert canonicalize_url("mailto:x@y.z") == "mailto:x@y.z"

    def test_returns_input_for_malformed(self):
        # Empty string / None — never raise.
        assert canonicalize_url("") == ""
        # The function is typed for str but defensive on non-str too.
        assert canonicalize_url(None) is None  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "url,expected",
        [
            # The pair that started this whole investigation. Even after
            # canonicalisation these stay distinct — the .html-vs-extensionless
            # ambiguity needs canonical-tag scraping, not URL normalisation.
            (
                "https://www.kao.com/global/en/worldwide.html",
                "https://www.kao.com/global/en/worldwide.html",
            ),
            (
                "https://www.kao.com/global/en/worldwide",
                "https://www.kao.com/global/en/worldwide",
            ),
            # Trailing-slash pair — these *do* unify, which is the main win
            # for the page-wise report tab grouping.
            ("https://www.kao.com/jp", "https://www.kao.com/jp"),
            ("https://www.kao.com/jp/", "https://www.kao.com/jp"),
        ],
    )
    def test_kao_url_examples(self, url, expected):
        assert canonicalize_url(url) == expected
