import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from a11y.accessibility.rules.rendered import section_headings
from a11y.api.v1.combined.findings import _section_headings_to_findings

def test_section_result_dataclass():
    sr = section_headings.SectionResult(
        url="https://example.com",
        section_index=0,
        tag="section",
        role=None,
        verdict="PASS",
        reason="Has heading",
        heading_tag="h2",
        heading_text="Heading Text",
        aria_label=None,
        aria_labelledby=None,
        content_length=100,
        outer_html_snippet="<section>...</section>",
        path_selector="body > section"
    )
    assert sr.tag == "section"
    assert sr.verdict == "PASS"

def test_page_report_dataclass():
    rep = section_headings.PageReport(
        url="https://example.com",
        timestamp="2026-06-01T12:00:00",
        title="Page Title",
        sections_found=1,
        pass_count=1,
        needs_review_count=0,
        fail_count=0,
        results=[]
    )
    assert rep.title == "Page Title"
    assert rep.sections_found == 1

def test_findings_converter_pass():
    report = {
        "status": "PASS",
        "reason": "All sections have headings",
        "details": {
            "summary": {
                "pages_crawled": 1,
                "pass_count": 1,
                "needs_review_count": 0,
                "fail_count": 0
            },
            "findings": []
        }
    }
    findings = _section_headings_to_findings(report, "https://example.com")
    assert len(findings) == 1
    assert findings[0]["status"] == "pass"
    assert findings[0]["wcag_sc"] == "2.4.10"
    assert findings[0]["rule_id"] == "python_2_4_10_section_headings"

def test_findings_converter_fail():
    report = {
        "status": "FAIL",
        "reason": "Missing headings",
        "details": {
            "findings": [
                {
                    "url": "https://example.com",
                    "section_index": 0,
                    "tag": "section",
                    "role": None,
                    "verdict": "FAIL",
                    "reason": "Section lacks heading",
                    "heading_tag": None,
                    "heading_text": None,
                    "aria_label": None,
                    "aria_labelledby": None,
                    "content_length": 500,
                    "outer_html_snippet": "<section>...</section>",
                    "path_selector": "body > section"
                }
            ]
        }
    }
    findings = _section_headings_to_findings(report, "https://example.com")
    assert len(findings) == 1
    assert findings[0]["status"] == "fail"
    assert findings[0]["element"]["tag"] == "section"
    assert findings[0]["element"]["selector"] == "body > section"

@pytest.mark.asyncio
async def test_check_page_evaluates_correctly():
    mock_page = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value={
        "title": "Page Title",
        "results": [
            {
                "idx": 0,
                "tag": "section",
                "role": None,
                "verdict": "PASS",
                "reason": "Direct heading",
                "headingTag": "h2",
                "headingText": "Hello",
                "ariaLabel": None,
                "ariaLabelledBy": None,
                "contentLength": 120,
                "outerSnippet": "<section><h2>Hello</h2></section>",
                "pathSelector": "body > section"
            }
        ]
    })

    rep = await section_headings.check_page(mock_page, "https://example.com")
    assert rep.title == "Page Title"
    assert rep.sections_found == 1
    assert rep.pass_count == 1
    assert len(rep.results) == 1
    assert rep.results[0].heading_text == "Hello"

@pytest.mark.asyncio
async def test_analyze_wcag_2410_crawls():
    with patch("a11y.accessibility.rules.rendered.section_headings.leased_context") as mock_lease:
        mock_ctx = AsyncMock()
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value={
            "title": "Page Title",
            "results": []
        })
        mock_page.eval_on_selector_all = AsyncMock(return_value=[])
        mock_ctx.new_page = AsyncMock(return_value=mock_page)
        mock_lease.return_value.__aenter__.return_value = mock_ctx

        res = await section_headings.analyze_wcag_2410("https://example.com")
        assert res["status"] == "PASS"
        assert res["details"]["summary"]["pages_crawled"] == 1
