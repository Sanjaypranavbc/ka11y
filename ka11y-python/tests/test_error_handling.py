"""
S2-03 error handling — classifier and retry behaviour.

Every test states the required behaviour. They fail before the fix; that is
the point. Offline: no browser, no network, no external host.

The API-level half (validation codes, the error_code field, the SSRF
admission gate) lives in test_error_handling_api.py, which needs the app.
"""
import pytest

from ka11y.crawler import navigation


class _FakePage:
    """Minimal Page stand-in: every goto raises the supplied error."""

    def __init__(self, error: Exception):
        self._error = error
        self.goto_calls = 0

    async def goto(self, url, wait_until=None, timeout=None):
        self.goto_calls += 1
        raise self._error


@pytest.fixture()
def no_dns_no_sleep(monkeypatch):
    """Keep the tests offline and instant."""

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(navigation, "dns_preflight", _noop)
    monkeypatch.setattr(navigation.asyncio, "sleep", _noop)


# ── Classification (leaves 2.1–2.4, 4.1, 4.2, 4.4) ───────────────────────────

CLASSIFY_CASES = [
    ("net::ERR_NAME_NOT_RESOLVED at https://x.test", "dns_resolution_failed"),
    ("net::ERR_CONNECTION_REFUSED at https://x.test", "connection_refused"),
    ("Timeout 30000ms exceeded.", "navigation_timeout"),
    ("net::ERR_INTERNET_DISCONNECTED at https://x.test", "network_unavailable"),
    ("net::ERR_ADDRESS_UNREACHABLE at https://x.test", "network_unavailable"),
    ("net::ERR_TOO_MANY_REDIRECTS at https://x.test", "too_many_redirects"),
]


@pytest.mark.parametrize("message,expected_code", CLASSIFY_CASES)
async def test_navigation_error_carries_specific_code(
    no_dns_no_sleep, message, expected_code
):
    """Each network condition gets its own code, not one catch-all."""
    page = _FakePage(RuntimeError(message))
    with pytest.raises(navigation.NavigationError) as exc:
        await navigation.navigate_with_resilience(page, "https://x.test")
    assert exc.value.code == expected_code, (
        f"{message!r} classified as {exc.value.code!r}, expected {expected_code!r}"
    )


def test_network_unavailable_tokens_are_recognised():
    """Leaf 2.4 is undetectable without these two tokens."""
    for token in ("ERR_INTERNET_DISCONNECTED", "ERR_ADDRESS_UNREACHABLE"):
        assert token in navigation._RETRYABLE_NAVIGATION_TOKENS, (
            f"{token} missing from the token list"
        )


# ── Retry gate ───────────────────────────────────────────────────────────────

async def test_permanent_failure_is_not_retried(no_dns_no_sleep):
    """A redirect loop cannot succeed on attempt 2 or 3."""
    page = _FakePage(RuntimeError("net::ERR_TOO_MANY_REDIRECTS at https://x.test"))
    with pytest.raises(navigation.NavigationError):
        await navigation.navigate_with_resilience(page, "https://x.test")
    assert page.goto_calls == 1, (
        f"permanent failure retried {page.goto_calls} times; expected 1"
    )


async def test_transient_failure_is_still_retried(no_dns_no_sleep):
    """PRESERVE: genuine transient errors keep their three attempts."""
    page = _FakePage(RuntimeError("net::ERR_CONNECTION_RESET at https://x.test"))
    with pytest.raises(navigation.NavigationError):
        await navigation.navigate_with_resilience(page, "https://x.test")
    assert page.goto_calls == 3


# ── Item I: seed-page HTTP status (leaves 3.1–3.4) ───────────────────────────

@pytest.mark.parametrize(
    "status,expected",
    [
        (404, "http_not_found"),
        (403, "http_forbidden"),
        (500, "http_server_error"),
        (503, "http_unavailable"),
    ],
)
def test_http_status_maps_to_its_own_code(status, expected):
    """A seed page answering 4xx/5xx is why the audit has nothing to report."""
    from ka11y.errors import code_for_status

    assert code_for_status(status) == expected


def test_unknown_status_falls_back_not_crashes():
    from ka11y.errors import code_for_status

    assert code_for_status(None) == "page_navigation_failed"
    assert code_for_status(418) == "http_not_found"
    assert code_for_status(502) == "http_server_error"


# ── Item F: only codes this project defines reach a client ───────────────────

def test_unknown_code_attribute_is_not_forwarded():
    """
    The runner reads `.code` off whatever was raised. Plenty of unrelated
    exceptions carry a `.code`, so an allow-list decides what a client sees;
    without it an arbitrary attribute value would land in a response body.
    """
    from ka11y.errors import code_of

    class _Sneaky(Exception):
        code = "/srv/secret/key.pem"

    class _Numeric(Exception):
        code = 500

    assert code_of(_Sneaky()) == "internal_error"
    assert code_of(_Numeric()) == "internal_error"
    assert code_of(Exception("no code at all")) == "internal_error"


def test_known_code_is_forwarded():
    from ka11y.crawler.navigation import NavigationError
    from ka11y.errors import code_of

    exc = NavigationError(
        code="dns_resolution_failed",
        url="https://x.test",
        host="x.test",
        original_message="net::ERR_NAME_NOT_RESOLVED",
        attempts=1,
    )
    assert code_of(exc) == "dns_resolution_failed"


# ── A10: every code the API can emit has EN and JA wording ───────────────────

def test_every_code_has_english_and_japanese_text():
    """A code with no entry renders as a blank message in the browser."""
    import re
    from pathlib import Path

    from ka11y.errors import AUDIT_ERROR_CODES

    ts = Path(__file__).resolve().parents[2] / "ka11y-ui/src/lib/i18n/translations.ts"
    if not ts.exists():                      # python-only checkout
        pytest.skip("ka11y-ui not present")

    source = ts.read_text(encoding="utf-8")
    blocks = re.findall(r"errorCodes:\s*\{(.*?)\n      \}", source, re.S)
    assert len(blocks) == 2, f"expected an EN and a JA errorCodes map, found {len(blocks)}"

    for lang, block in zip(("en", "ja"), blocks):
        present = set(re.findall(r"^\s{8}([a-z_]+):", block, re.M))
        missing = AUDIT_ERROR_CODES - present
        assert not missing, f"{lang} is missing wording for: {sorted(missing)}"


# ── Regression: _prepare_page must not short-circuit its own tail ────────────

def test_prepare_page_still_runs_cookie_handling():
    """
    _prepare_page gained a return value so the caller can read the HTTP
    status. Returning at the navigation site would silently skip cookie
    handling and DOM settling further down — the page would then be audited
    with a consent banner covering it, and no existing test would notice.
    """
    import inspect

    from ka11y.crawler.universal_page import UniversalPageLoader

    src = inspect.getsource(UniversalPageLoader._prepare_page)
    body = src[src.index("return response"):] if "return response" in src else ""
    assert "handle_cookies" in src, "cookie handling left the function entirely"
    assert "handle_cookies" not in body, (
        "cookie handling sits after `return response` and can never run"
    )
    assert "_wait_for_spa" not in body, "SPA settling is unreachable"


# ── Per-page failures must not carry raw exception text into the report ──────

def test_failed_page_entry_carries_a_code_not_exception_text():
    """
    A page that fails mid-extraction used to put `str(exc)` straight into the
    report the client downloads. Any exception message — including one holding
    a file path — reached the screen that way.
    """
    from ka11y.api.v1.combined.stages import page_failure_entry

    secret = "/srv/ka11y/internal/creds.pem"
    entry = page_failure_entry(
        {
            "page_url": "https://x.test/a",
            "code": "page_extract_failed",
            "message": f"OSError: cannot open {secret}",
        }
    )

    assert entry["error_code"] == "page_extract_failed"
    assert secret not in str(entry), f"raw exception text survived: {entry!r}"
    assert entry["error"], "a failed page still needs something readable"


def test_failed_page_entry_without_a_code_still_reports():
    from ka11y.api.v1.combined.stages import page_failure_entry

    entry = page_failure_entry({"page_url": "https://x.test/b", "message": "boom"})
    assert entry["error_code"] == "page_extract_failed"
    assert "boom" not in str(entry)
