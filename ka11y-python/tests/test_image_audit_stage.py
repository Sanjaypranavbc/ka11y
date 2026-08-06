from __future__ import annotations

from pathlib import Path

import pytest
from unittest.mock import patch


def test_image_crawler_navigation_error_dns_message_is_frontend_clear():
    from ka11y.crawler.optimized.optimized_crawler import ImageCrawlerNavigationError

    exc = ImageCrawlerNavigationError(
        code="dns_resolution_failed",
        url="https://www.kao.com/jp/",
        host="www.kao.com",
        original_message="Page.goto: net::ERR_NAME_NOT_RESOLVED at https://www.kao.com/jp/",
        attempts=3,
    )

    message = str(exc)
    assert "dns_resolution_failed" in message
    assert "host=www.kao.com" in message
    assert "OCR and image-audit checks were skipped" in message


def test_build_image_audit_report_surfaces_all_audited_images():
    from ka11y.api.v1.combined.findings import _build_image_audit_report

    report = _build_image_audit_report(
        [
            {
                "filename": "hero.png",
                "screenshot_path": "/tmp/hero.png",
                "src": "https://example.com/hero.png",
                "url": "https://example.com",
                "alt_text": "",
                "title": "",
                "classification": "informative",
                "sub_type": "",
                "overall_status": "FAILED",
                "has_ocr_text": True,
                "detected_text": "Sale now on",
                "contrast_violations_count": 2,
                "wcag_1_1_1_status": "FAILED",
                "wcag_4_1_2_status": "N/A",
                "wcag_1_4_5_status": "FAILED",
                "wcag_1_4_11_status": "FAILED",
                "wcag_1_1_1_reason": "Missing alt text",
                "wcag_4_1_2_reason": "N/A",
                "wcag_1_4_5_reason": "Text baked into image",
                "wcag_1_4_11_reason": "Insufficient contrast",
            },
            {
                "filename": "icon.png",
                "screenshot_path": "/tmp/icon.png",
                "src": "https://example.com/icon.png",
                "url": "https://example.com",
                "alt_text": "Search",
                "title": "",
                "classification": "functional",
                "sub_type": "icons",
                "overall_status": "PASSED",
                "has_ocr_text": False,
                "detected_text": "",
                "contrast_violations_count": 0,
                "wcag_1_1_1_status": "PASSED",
                "wcag_4_1_2_status": "PASSED",
                "wcag_1_4_5_status": "N/A",
                "wcag_1_4_11_status": "N/A",
                "wcag_1_1_1_reason": "Has alt text",
                "wcag_4_1_2_reason": "Accessible name present",
                "wcag_1_4_5_reason": "",
                "wcag_1_4_11_reason": "",
            },
        ]
    )

    assert report["summary"]["total_images"] == 2
    assert report["summary"]["failed"] == 1
    assert report["summary"]["passed"] == 1
    assert report["summary"]["with_ocr_text"] == 1
    assert report["summary"]["with_contrast_violations"] == 1
    assert report["summary"]["by_classification"]["informative"]["failed"] == 1
    assert report["summary"]["by_classification"]["functional"]["passed"] == 1
    assert [img["filename"] for img in report["images"]] == ["hero.png", "icon.png"]


@pytest.mark.asyncio
async def test_stage_image_audit_surfaces_dns_resolution_warning():
    from ka11y.api.v1.combined import store
    from ka11y.api.v1.combined.stages import _stage_image_audit
    from ka11y.crawler.optimized.optimized_crawler import ImageCrawlerNavigationError

    job_id = "image-audit-dns-warning"
    store._jobs[job_id] = {
        "job_id": job_id,
        "status": "running",
        "url": "https://www.kao.com/jp/",
        "submitted_at": "2026-04-13T10:00:00+00:00",
        "_created_at": 0,
        "completed_at": None,
        "report_path": None,
        "result": None,
        "error": None,
        "current_stage": None,
        "stages": [],
        "warnings": [],
        "step_log_path": None,
    }

    class DummyCrawler:
        def __init__(
            self,
            base_url: str,
            max_depth: int,
            max_pages: int = 50,
            internal_links: bool = True,
            job_id: str | None = None,
            output_dir: str | None = None,
        ):
            self.base_url = base_url
            self.max_depth = max_depth
            self.max_pages = max_pages
            self.internal_links = internal_links
            self.job_id = job_id
            self.images_data = []
            self.output_dir = output_dir or "/tmp/ka11y-image-audit-test"

        async def crawl_page(self, **kwargs):
            raise ImageCrawlerNavigationError(
                code="dns_resolution_failed",
                url=self.base_url,
                host="www.kao.com",
                original_message=(
                    "Page.goto: net::ERR_NAME_NOT_RESOLVED at https://www.kao.com/jp/"
                ),
                attempts=3,
            )

        def save_results(self):
            raise AssertionError("save_results() should not run after a DNS failure")

    class DummyAuditor:
        def generate_audit_report(self, **kwargs):
            raise AssertionError("image auditor should not run after a DNS failure")

    class DummyOCR:
        def __init__(self, *args, **kwargs):
            raise AssertionError("OCR should not start after a DNS failure")

    class DummyTextClassification:
        def __init__(self, *args, **kwargs):
            raise AssertionError(
                "text classification should not start after a DNS failure"
            )

    with patch("ka11y.crawler.optimized.optimized_crawler.OptimizedImageCrawler", DummyCrawler), patch(
        "ka11y.accessibility.rules.non_text.alttext.AltTextAccessibilityAuditor",
        DummyAuditor,
    ), patch(
        "ka11y.text_detector.text_detector.OCRPreprocessing",
        DummyOCR,
    ), patch(
        "ka11y.text_detector.text_detector.TextClassification",
        DummyTextClassification,
    ):
        findings, contrast_report, image_audit_report = await _stage_image_audit(
            url="https://www.kao.com/jp/",
            output_dir=Path("/tmp"),
            max_depth=0,
            run_ocr=True,
            run_image_audit=True,
            job_id=job_id,
            lang="ja",
            step_logger=None,
        )

    assert findings == []
    assert contrast_report is None
    assert image_audit_report is None
    assert store._jobs[job_id]["warnings"]
    assert any(
        "dns_resolution_failed" in warning
        and "OCR and image-audit checks were skipped" in warning
        for warning in store._jobs[job_id]["warnings"]
    )
    stage = next(s for s in store._jobs[job_id]["stages"] if s["name"] == "image_audit")
    assert stage["status"] == "error"

    store._jobs.pop(job_id, None)
