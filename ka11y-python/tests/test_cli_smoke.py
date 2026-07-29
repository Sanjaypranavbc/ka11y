"""
tests/test_cli_smoke.py
========================
End-to-end integration and CLI smoke tests, verifying that the entire enrich_audit.py tool
can be executed on real JSON files, creating the correct output files and tables.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import enrich_audit


def test_cli_smoke_end_to_end(tmp_path):
    """Smoke test running the entire enrich_audit workflow end-to-end with mocked API."""
    # 1. Create a mock combined_report.json input
    input_report = {
        "url": "https://www.kao.com/global/en",
        "generated_at": "2026-07-29T05:42:00Z",
        "summary": {
            "total_findings": 3,
            "violations": 2,
            "needs_review": 1,
            "passes": 0,
        },
        "violations": [
            {
                "finding_id": "violation1",
                "rule_id": "python_1_4_3_contrast",
                "wcag_sc": "1.4.3",
                "criterion_name": "Contrast (Minimum)",
                "level": "AA",
                "severity": "high",
                "status": "fail",
                "reason": "Contrast is 2.85:1, which is below 4.5:1",
                "suggested_fix": "Increase contrast",
                "element": {
                    "html": "<img-text fg=\"#fdfefe\" bg=\"#00ac8f\">Kao</img-text>",
                    "tag": "img",
                    "image_text": "Kao",
                    "page_url": "https://www.kao.com/global/en"
                }
            },
            {
                "finding_id": "violation2",
                "rule_id": "python_1_1_1_alt",
                "wcag_sc": "1.1.1",
                "criterion_name": "Non-text Content",
                "level": "A",
                "severity": "critical",
                "status": "fail",
                "reason": "Missing alt text",
                "suggested_fix": "Add alt",
                "element": {
                    "html": "<img src='logo.png'>",
                    "tag": "img",
                    "page_url": "https://www.kao.com/global/en"
                }
            }
        ],
        "needs_review": [
            {
                "finding_id": "review1",
                "rule_id": "python_1_2_1_audio",
                "wcag_sc": "1.2.1",
                "criterion_name": "Audio-only and Video-only (Prerecorded)",
                "level": "A",
                "severity": "medium",
                "status": "needs_review",
                "reason": "Auditor found video without clear transcript indicator",
                "suggested_fix": "Provide descriptive transcripts",
                "element": {
                    "html": "<video src='promo.mp4'></video>",
                    "tag": "video",
                    "page_url": "https://www.kao.com/global/en"
                }
            }
        ],
        "passes": []
    }
    
    input_file = tmp_path / "combined_report.json"
    with open(input_file, "w", encoding="utf-8") as f:
        json.dump(input_report, f, indent=2)
        
    # 2. Setup mock for google.generativeai response
    mock_response_violations = MagicMock()
    mock_response_violations.text = json.dumps([
        {
            "finding_id": "violation1",
            "wcag_sc": "1.4.3",
            "dynamic_reason": "The contrast ratio of 2.85:1 for 'Kao' is insufficient. It must be at least 4.5:1.",
            "dynamic_suggested_fix": "Change the background color to #007762 to meet contrast ratio of 4.58:1.",
            "user_impact": "Users with low vision will be unable to read this text.",
            "confidence": "high"
        },
        {
            "finding_id": "violation2",
            "wcag_sc": "1.1.1",
            "dynamic_reason": "The header image is missing alternative text which is functional.",
            "dynamic_suggested_fix": "Add alt='Kao Logo' to specify the image function.",
            "user_impact": "Screen reader users will not understand the header image's purpose.",
            "confidence": "high"
        }
    ])
    # Add usage metadata mock
    mock_usage_violations = MagicMock()
    mock_usage_violations.prompt_token_count = 1500
    mock_usage_violations.candidates_token_count = 500
    mock_usage_violations.total_token_count = 2000
    mock_response_violations.usage_metadata = mock_usage_violations

    mock_response_review = MagicMock()
    mock_response_review.text = json.dumps([
        {
            "finding_id": "review1",
            "wcag_sc": "1.2.1",
            "dynamic_reason": "This prerecorded video has no linked text transcript or audio description.",
            "dynamic_suggested_fix": "Create and link a text transcript describing the visual content.",
            "user_impact": "",
            "confidence": "medium"
        }
    ])
    mock_usage_review = MagicMock()
    mock_usage_review.prompt_token_count = 800
    mock_usage_review.candidates_token_count = 250
    mock_usage_review.total_token_count = 1050
    mock_response_review.usage_metadata = mock_usage_review

    # We mock generate_content to return the violations response first, then the review response
    mock_generate = MagicMock(side_effect=[mock_response_violations, mock_response_review])

    # 3. Invoke main with mocked arguments and environments
    test_args = [
        "enrich_audit.py",
        "--input", str(input_file),
        "--output-dir", str(tmp_path),
        "--batch-size", "5"
    ]
    
    with patch.object(sys, "argv", test_args), \
         patch.dict(os.environ, {"GEMINI_API_KEY": "fake-api-key"}), \
         patch("google.generativeai.GenerativeModel") as mock_model_class, \
         patch("time.sleep") as mock_sleep:
        
        # Configure model instance
        mock_model_instance = MagicMock()
        mock_model_instance.generate_content = mock_generate
        mock_model_class.return_value = mock_model_instance
        
        exit_code = enrich_audit.main()
        
        assert exit_code == 0
        
    # 4. Verify enriched_report.json was created and matches specifications
    enriched_report_file = tmp_path / "enriched_report.json"
    assert enriched_report_file.is_file()
    
    with open(enriched_report_file, "r", encoding="utf-8") as f:
        enriched_data = json.load(f)
        
    # Check that original metadata is preserved
    assert enriched_data["url"] == "https://www.kao.com/global/en"
    assert enriched_data["generated_at"] == "2026-07-29T05:42:00Z"
    
    # Check that violations are enriched correctly
    v1 = enriched_data["violations"][0]
    assert v1["finding_id"] == "violation1"
    assert "dynamic_reason" in v1
    assert "The contrast ratio of 2.85:1" in v1["dynamic_reason"]
    assert "Change the background color to" in v1["dynamic_suggested_fix"]
    assert "Users with low vision" in v1["user_impact"]
    assert v1["confidence"] == "high"
    
    v2 = enriched_data["violations"][1]
    assert v2["finding_id"] == "violation2"
    assert "The header image is missing" in v2["dynamic_reason"]
    assert "Add alt='Kao Logo'" in v2["dynamic_suggested_fix"]
    assert "Screen reader users" in v2["user_impact"]
    
    # Check that needs_review is enriched correctly
    nr1 = enriched_data["needs_review"][0]
    assert nr1["finding_id"] == "review1"
    assert "linked text transcript" in nr1["dynamic_reason"]
    assert nr1["user_impact"] == ""
    assert nr1["confidence"] == "medium"
    
    # 5. Verify token_usage.json matches expected schema
    token_usage_file = tmp_path / "token_usage.json"
    assert token_usage_file.is_file()
    
    with open(token_usage_file, "r", encoding="utf-8") as f:
        usage_data = json.load(f)
        
    assert usage_data["report_file"] == "combined_report.json"
    assert usage_data["model"] == "gemini-3.1"
    assert usage_data["violations_enriched"] == 3
    assert len(usage_data["batches"]) == 2
    
    totals = usage_data["totals"]
    assert totals["api_calls"] == 2
    assert totals["input_tokens"] == 1500 + 800
    assert totals["output_tokens"] == 500 + 250
    assert totals["total_tokens"] == 2000 + 1050
    assert totals["avg_tokens_per_violation"] == totals["total_tokens"] / 3.0
    
    # Check estimated cost ($0.075/1M input and $0.30/1M output)
    expected_cost = (2300 * 0.075 / 1_000_000.0) + (750 * 0.30 / 1_000_000.0)
    assert totals["estimated_cost_usd"] == pytest.approx(expected_cost)


def test_enrich_report_in_pipeline_interface(tmp_path):
    """Verify that enrich_report_in_pipeline function can be called directly and handles key absence."""
    report = {
        "url": "https://example.com",
        "violations": [{"finding_id": "v1", "rule_id": "r1", "wcag_sc": "1.1.1"}],
    }
    
    # 1. Call with missing API key — should complete gracefully
    with patch("enrich_audit.load_dotenv") as mock_load_dotenv, \
         patch.dict(os.environ, {}, clear=True):
        # Cleared API key and blocked dotenv load
        enrich_audit.enrich_report_in_pipeline(report, tmp_path)
        
        # Files should NOT be written because it skipped
        assert not (tmp_path / "enriched_report.json").is_file()
        assert not (tmp_path / "token_usage.json").is_file()
        
    # 2. Call with mocked API success — should write both files
    mock_response = MagicMock()
    mock_response.text = json.dumps([
        {
            "finding_id": "v1",
            "wcag_sc": "1.1.1",
            "dynamic_reason": "fail",
            "dynamic_suggested_fix": "fix",
            "user_impact": "",
            "confidence": "high"
        }
    ])
    mock_usage = MagicMock()
    mock_usage.prompt_token_count = 100
    mock_usage.candidates_token_count = 50
    mock_usage.total_token_count = 150
    mock_response.usage_metadata = mock_usage
    
    with patch.dict(os.environ, {"GEMINI_API_KEY": "some-key"}), \
         patch("google.generativeai.GenerativeModel") as mock_model_class, \
         patch("time.sleep") as mock_sleep:
         
        mock_model_instance = MagicMock()
        mock_model_instance.generate_content.return_value = mock_response
        mock_model_class.return_value = mock_model_instance
        
        enrich_audit.enrich_report_in_pipeline(report, tmp_path)
        
        # Files SHOULD be written
        assert (tmp_path / "enriched_report.json").is_file()
        assert (tmp_path / "token_usage.json").is_file()
        
        # Verify saved data structure
        with open(tmp_path / "enriched_report.json") as f:
            saved = json.load(f)
            assert saved["violations"][0]["dynamic_reason"] == "fail"

