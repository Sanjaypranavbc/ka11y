import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from a11y.accessibility.rules.navigation import consistent_id
from a11y.api.v1.combined.findings import _consistent_id_to_findings

def test_normalize():
    assert consistent_id.normalize("  Some   weird \u3000 spacing  ") == "some weird spacing"
    assert consistent_id.normalize(None) == ""

def test_clean_label():
    assert consistent_id.clean_label("click here to search") == "here to search"
    assert consistent_id.clean_label("navigate to Login") == "login"
    assert consistent_id.clean_label("tap to sign in") == "to sign in"

def test_detect_function():
    assert consistent_id.detect_function("search") == "search"
    assert consistent_id.detect_function("find") == "search"
    assert consistent_id.detect_function("log in") == "login"
    assert consistent_id.detect_function("sign in") == "login"
    assert consistent_id.detect_function("sign out") == "logout"
    assert consistent_id.detect_function("create account") == "register"
    assert consistent_id.detect_function("contact us") == "contact"
    assert consistent_id.detect_function("shopping cart") == "cart"
    assert consistent_id.detect_function("random label") is None

def test_normalize_url():
    assert consistent_id.normalize_url("https://example.com/path/?a=1#section") == "https://example.com/path"

def test_analyze_pass():
    collected = [
        {"function": "search", "label": "search", "region": "header", "url": "https://example.com/page1"},
        {"function": "search", "label": "search", "region": "header", "url": "https://example.com/page2"},
        {"function": "login", "label": "login", "region": "header", "url": "https://example.com/page1"},
        {"function": "login", "label": "login", "region": "header", "url": "https://example.com/page2"},
    ]
    res = consistent_id.analyze(collected)
    assert res["status"] == "PASS"
    assert "search (header)" in res["details"]
    assert "login (header)" in res["details"]

def test_analyze_fail():
    collected = [
        {"function": "search", "label": "search", "region": "header", "url": "https://example.com/page1"},
        # Different label "find" for same function in same region!
        {"function": "search", "label": "find", "region": "header", "url": "https://example.com/page2"},
    ]
    res = consistent_id.analyze(collected)
    assert res["status"] == "FAIL"
    assert "search (header)" in res["details"]

def test_findings_converter_pass():
    report = {
        "status": "PASS",
        "reason": "All good",
        "details": {}
    }
    findings = _consistent_id_to_findings(report, "https://example.com")
    assert len(findings) == 1
    assert findings[0]["status"] == "pass"
    assert findings[0]["wcag_sc"] == "3.2.4"
    assert findings[0]["rule_id"] == "python_3_2_4_consistent_id"

def test_findings_converter_fail():
    report = {
        "status": "FAIL",
        "reason": "Inconsistent labels",
        "details": {
            "search (header)": {
                "search": ["https://example.com/page1"],
                "find": ["https://example.com/page2"]
            }
        }
    }
    findings = _consistent_id_to_findings(report, "https://example.com")
    assert len(findings) == 1
    assert findings[0]["status"] == "fail"
    assert "Inconsistent" in findings[0]["reason"] or "inconsistent" in findings[0]["reason"]

@pytest.mark.asyncio
async def test_analyze_wcag_324_crawls_and_analyzes():
    with patch("a11y.accessibility.rules.navigation.consistent_id.leased_context") as mock_lease:
        mock_ctx = AsyncMock()
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[
            {"label": "search", "region": "header", "role": "button"}
        ])
        mock_page.content = AsyncMock(return_value="")
        mock_page.title = AsyncMock(return_value="Home")
        mock_ctx.new_page = AsyncMock(return_value=mock_page)
        mock_lease.return_value.__aenter__.return_value = mock_ctx

        # We also need to mock get_links to return no links so crawl stops quickly
        with patch("a11y.accessibility.rules.navigation.consistent_id.get_links", return_value=[]):
            res = await consistent_id.analyze_wcag_324("https://example.com")
            # With only 1 crawled page there is nothing to compare against
            # (MIN_REPEAT_PAGES = 2), so 3.2.4 cannot be violated — failing here
            # would be a false positive. A component seen on a single page is
            # skipped and the check PASSES.
            assert res["status"] == "PASS"
