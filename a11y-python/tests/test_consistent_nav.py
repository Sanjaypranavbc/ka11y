import pytest
from bs4 import BeautifulSoup
from unittest.mock import AsyncMock, MagicMock, patch
from a11y.accessibility.rules.navigation import consistent_nav
from a11y.api.v1.combined.findings import _consistent_navigation_to_findings

def test_normalize_url():
    assert consistent_nav.normalize_url("https://example.com/page?query=1#frag") == "https://example.com/page"
    assert consistent_nav.normalize_url("http://test.com/path/") == "http://test.com/path"
    assert consistent_nav.normalize_url("http://test.com/") == "http://test.com"

def test_is_excluded():
    assert consistent_nav.is_excluded("https://example.com/login") is True
    assert consistent_nav.is_excluded("https://example.com/checkout/payment") is True
    assert consistent_nav.is_excluded("https://example.com/about-us") is False

def test_get_accessible_name():
    soup = BeautifulSoup('<a href="#" aria-label="Aria Label">Standard Link</a>', "lxml")
    link = soup.find("a")
    # standard text first
    assert consistent_nav.get_accessible_name(link) == "Standard Link"

    soup2 = BeautifulSoup('<a href="#" aria-label="Aria Label"></a>', "lxml")
    link2 = soup2.find("a")
    assert consistent_nav.get_accessible_name(link2) == "Aria Label"

    soup3 = BeautifulSoup('<a href="#" title="Link Title"></a>', "lxml")
    link3 = soup3.find("a")
    assert consistent_nav.get_accessible_name(link3) == "Link Title"

    soup4 = BeautifulSoup('<a href="#"><img src="x.png" alt="Image Alt"/></a>', "lxml")
    link4 = soup4.find("a")
    assert consistent_nav.get_accessible_name(link4) == "Image Alt"

def test_relative_order_match():
    nav1 = ["Home", "About", "Services", "Contact"]
    nav2 = ["Home", "Services", "Contact"]
    nav3 = ["Services", "Home", "Contact"]

    # In nav2, Home, Services, Contact are in the same relative order as nav1
    matched, seq1, seq2 = consistent_nav.relative_order_match(nav1, nav2)
    assert matched is True
    assert seq1 == ["Home", "Services", "Contact"]
    assert seq2 == ["Home", "Services", "Contact"]

    # In nav3, Services is before Home, which mismatches nav1
    matched, seq1, seq2 = consistent_nav.relative_order_match(nav1, nav3)
    assert matched is False

def test_extract_navigation():
    html = """
    <html>
      <body>
        <nav>
          <a href="/home">Home</a>
          <a href="/about">About</a>
          <a href="/services">Services</a>
          <a href="/contact">Contact</a>
        </nav>
      </body>
    </html>
    """
    navs = consistent_nav.extract_navigation(html)
    assert len(navs) == 1
    assert navs[0]["items"] == ["Home", "About", "Services", "Contact"]

def test_discover_links():
    html = """
    <html>
      <body>
        <a href="/page1">Page 1</a>
        <a href="https://otherdomain.com/page2">External Page</a>
        <a href="/login">Excluded Login</a>
        <a href="/document.pdf">PDF File</a>
        <a href="/page3">Page 3</a>
      </body>
    </html>
    """
    links = consistent_nav.discover_links(html, "https://example.com/home")
    # Base URL should be included first, then discovered internal links (not excluded/files)
    assert "https://example.com/home" in links
    assert "https://example.com/page1" in links
    assert "https://example.com/page3" in links
    assert "https://otherdomain.com/page2" not in links
    assert "https://example.com/login" not in links
    assert "https://example.com/document.pdf" not in links

def test_findings_converter_pass():
    report = {
        "status": "PASS",
        "reason": "All good",
        "details": {}
    }
    findings = _consistent_navigation_to_findings(report, "https://example.com")
    assert len(findings) == 1
    assert findings[0]["status"] == "pass"
    assert findings[0]["wcag_sc"] == "3.2.3"
    assert findings[0]["rule_id"] == "python_3_2_3_navigation"

def test_findings_converter_fail():
    report = {
        "status": "FAIL",
        "reason": "Navigation order mismatch",
        "details": {
            "comparisons": [
                {
                    "url1": "https://example.com/page1",
                    "url2": "https://example.com/page2",
                    "seq1": ["Home", "About", "Services"],
                    "seq2": ["About", "Home", "Services"],
                    "pass": False
                }
            ]
        }
    }
    findings = _consistent_navigation_to_findings(report, "https://example.com")
    assert len(findings) == 1
    assert findings[0]["status"] == "fail"
    assert "Mismatch" in findings[0]["reason"] or "mismatch" in findings[0]["reason"]

@pytest.mark.asyncio
async def test_analyze_wcag_323_needs_review_on_no_pages():
    with patch("a11y.accessibility.rules.navigation.consistent_nav.leased_context") as mock_lease:
        mock_ctx = AsyncMock()
        mock_page = AsyncMock()
        mock_page.content = AsyncMock(return_value="")
        mock_ctx.new_page = AsyncMock(return_value=mock_page)
        mock_lease.return_value.__aenter__.return_value = mock_ctx

        res = await consistent_nav.analyze_wcag_323("https://example.com")
        assert res["status"] == "NEEDS_REVIEW"
