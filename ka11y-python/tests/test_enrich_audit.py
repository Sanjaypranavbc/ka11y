"""
tests/test_enrich_audit.py
===========================
Unit tests for the enrich_audit.py CLI tool, verifying report loading, validation,
trimming, batching, retry behaviors, token counting, and merge success.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from enrich_audit import (
    call_gemini_with_retry,
    chunk_list,
    enrich_report_list,
    find_audit_root_dir,
    trim_finding,
    validate_report,
)


def test_validate_report_valid():
    """Verify that a valid report does not raise any exceptions."""
    valid_report = {
        "url": "https://example.com",
        "violations": [],
        "needs_review": []
    }
    # Should not raise
    validate_report(valid_report)


def test_validate_report_invalid_type():
    """Verify that a non-dict report raises a ValueError."""
    with pytest.raises(ValueError, match="Report must be a JSON object"):
        validate_report([])


def test_validate_report_missing_violations():
    """Verify that a report missing the violations key raises a ValueError."""
    with pytest.raises(ValueError, match="missing the required 'violations' key"):
        validate_report({"url": "https://example.com"})


def test_validate_report_non_list_violations():
    """Verify that a report with a non-list violations key raises a ValueError."""
    with pytest.raises(ValueError, match="'violations' must be a JSON array"):
        validate_report({"violations": "not-a-list"})


def test_validate_report_non_list_needs_review():
    """Verify that a report with a non-list needs_review key raises a ValueError."""
    with pytest.raises(ValueError, match="'needs_review' must be a JSON array"):
        validate_report({"violations": [], "needs_review": "not-a-list"})


def test_trim_finding():
    """Verify that finding payloads are trimmed to exactly what Gemini expects."""
    finding = {
        "finding_id": "find1",
        "rule_id": "rule_1_4_3",
        "wcag_sc": "1.4.3",
        "criterion_name": "Contrast",
        "level": "AA",
        "severity": "high",
        "status": "fail",
        "reason": "Existing static reason text",
        "suggested_fix": "Existing fix text",
        "element": {
            "html": "<span>Kao</span>",
            "tag": "span",
            "image_text": "Kao",
            "page_url": "https://example.com/page",
            "selector": "ignored",  # Should be omitted in trimmed finding
        },
        "manual_review": False,
    }
    
    trimmed = trim_finding(finding)
    
    assert trimmed == {
        "finding_id": "find1",
        "rule_id": "rule_1_4_3",
        "wcag_sc": "1.4.3",
        "criterion_name": "Contrast",
        "level": "AA",
        "severity": "high",
        "existing_reason": "Existing static reason text",
        "existing_suggested_fix": "Existing fix text",
        "element": {
            "html": "<span>Kao</span>",
            "tag": "span",
            "image_text": "Kao",
            "page_url": "https://example.com/page",
        }
    }


def test_trim_finding_missing_element():
    """Verify trim_finding works robustly when element is missing or None."""
    finding = {
        "finding_id": "find2",
        "rule_id": "rule_1_1_1",
        "wcag_sc": "1.1.1",
        "element": None,
    }
    
    trimmed = trim_finding(finding)
    assert trimmed["element"] == {}


def test_chunk_list():
    """Verify list chunking logic slices lists into exact chunk sizes."""
    lst = [1, 2, 3, 4, 5, 6, 7, 8]
    assert chunk_list(lst, 3) == [[1, 2, 3], [4, 5, 6], [7, 8]]
    assert chunk_list(lst, 10) == [[1, 2, 3, 4, 5, 6, 7, 8]]
    assert chunk_list([], 3) == []


@patch("time.sleep")  # Avoid sleeping during tests
def test_call_gemini_with_retry_success(mock_sleep):
    """Verify success path with no retries when Gemini returns valid JSON."""
    mock_model = MagicMock()
    mock_response = MagicMock()
    
    mock_response.text = json.dumps([
        {
            "finding_id": "f1",
            "wcag_sc": "1.1.1",
            "dynamic_reason": "Fails because of lack of alt",
            "dynamic_suggested_fix": "Add alt",
            "user_impact": "Blind users blocked",
            "confidence": "high"
        }
    ])
    mock_model.generate_content.return_value = mock_response
    
    response, parsed, attempt = call_gemini_with_retry(
        model=mock_model,
        trimmed_batch=[{"finding_id": "f1"}],
        max_retries=1
    )
    
    assert attempt == 0
    assert len(parsed) == 1
    assert parsed[0]["finding_id"] == "f1"
    assert parsed[0]["dynamic_reason"] == "Fails because of lack of alt"
    assert not mock_sleep.called


@patch("time.sleep")
def test_call_gemini_with_retry_one_retry_success(mock_sleep):
    """Verify that a single failure is retried and succeeds on attempt 1."""
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps([{"finding_id": "f1"}])
    
    # First call raises an error, second returns mock_response
    mock_model.generate_content.side_effect = [RuntimeError("API Overloaded"), mock_response]
    
    response, parsed, attempt = call_gemini_with_retry(
        model=mock_model,
        trimmed_batch=[{"finding_id": "f1"}],
        max_retries=1,
        backoff_seconds=0.1
    )
    
    assert attempt == 1
    assert len(parsed) == 1
    assert parsed[0]["finding_id"] == "f1"
    assert mock_sleep.call_count == 1


def test_call_gemini_with_retry_complete_failure():
    """Verify that if both attempts fail, the error is propagated."""
    mock_model = MagicMock()
    mock_model.generate_content.side_effect = RuntimeError("API Overloaded")
    
    with pytest.raises(RuntimeError, match="API Overloaded"):
        call_gemini_with_retry(
            model=mock_model,
            trimmed_batch=[{"finding_id": "f1"}],
            max_retries=1,
            backoff_seconds=0.01
        )


@patch("time.sleep")
def test_enrich_report_list_success(mock_sleep):
    """Verify that findings are updated correctly upon successful Gemini completion."""
    original_list = [
        {"finding_id": "f1", "status": "fail", "reason": "old", "suggested_fix": "old"},
        {"finding_id": "f2", "status": "fail", "reason": "old", "suggested_fix": "old"},
    ]
    trimmed_items = [
        {"finding_id": "f1", "existing_reason": "old"},
        {"finding_id": "f2", "existing_reason": "old"},
    ]
    
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps([
        {
            "finding_id": "f1",
            "wcag_sc": "1.1.1",
            "dynamic_reason": "new reason 1",
            "dynamic_suggested_fix": "new fix 1",
            "user_impact": "impact 1",
            "confidence": "high"
        },
        {
            "finding_id": "f2",
            "wcag_sc": "1.1.1",
            "dynamic_reason": "new reason 2",
            "dynamic_suggested_fix": "new fix 2",
            "user_impact": "",
            "confidence": "medium"
        }
    ])
    mock_model.generate_content.return_value = mock_response
    
    batches_log = []
    totals = {
        "api_calls": 0,
        "retries": 0,
        "failures": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
    
    enrich_report_list(
        original_list=original_list,
        trimmed_items=trimmed_items,
        model=mock_model,
        batch_size=10,
        batches_log=batches_log,
        totals_tracker=totals,
    )
    
    assert len(batches_log) == 1
    assert batches_log[0]["status"] == "success"
    assert totals["api_calls"] == 1
    assert totals["failures"] == 0
    
    # Check if mutated original findings are enriched correctly
    assert original_list[0]["dynamic_reason"] == "new reason 1"
    assert original_list[0]["dynamic_suggested_fix"] == "new fix 1"
    assert original_list[0]["user_impact"] == "impact 1"
    assert original_list[0]["confidence"] == "high"
    assert "dynamic_enrichment_failed" not in original_list[0]
    
    assert original_list[1]["dynamic_reason"] == "new reason 2"
    assert original_list[1]["dynamic_suggested_fix"] == "new fix 2"
    assert original_list[1]["user_impact"] == ""
    assert original_list[1]["confidence"] == "medium"


@patch("time.sleep")
def test_enrich_report_list_failure_fallback(mock_sleep):
    """Verify that a batch failure leaves elements intact and flags dynamic_enrichment_failed."""
    original_list = [
        {"finding_id": "f1", "status": "fail", "reason": "old", "suggested_fix": "old"},
        {"finding_id": "f2", "status": "fail", "reason": "old", "suggested_fix": "old"},
    ]
    trimmed_items = [
        {"finding_id": "f1", "existing_reason": "old"},
        {"finding_id": "f2", "existing_reason": "old"},
    ]
    
    mock_model = MagicMock()
    mock_model.generate_content.side_effect = RuntimeError("Service Unavailable")
    
    batches_log = []
    totals = {
        "api_calls": 0,
        "retries": 0,
        "failures": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
    
    enrich_report_list(
        original_list=original_list,
        trimmed_items=trimmed_items,
        model=mock_model,
        batch_size=10,
        batches_log=batches_log,
        totals_tracker=totals,
    )
    
    assert len(batches_log) == 1
    assert batches_log[0]["status"] == "failed"
    assert totals["api_calls"] == 1
    assert totals["failures"] == 1
    
    # Verify that original values are preserved and failed flag is set
    assert original_list[0]["reason"] == "old"
    assert original_list[0]["suggested_fix"] == "old"
    assert original_list[0]["dynamic_enrichment_failed"] is True
    assert "dynamic_reason" not in original_list[0]
    
    assert original_list[1]["reason"] == "old"
    assert original_list[1]["suggested_fix"] == "old"
    assert original_list[1]["dynamic_enrichment_failed"] is True
    assert "dynamic_reason" not in original_list[1]


def test_find_audit_root_dir(tmp_path):
    """Verify that find_audit_root_dir finds the audit root folder under crawled_images."""
    # Scenario 1: Inside crawled_images
    crawled_images_dir = tmp_path / "output" / "crawled_images"
    audit_root_dir = crawled_images_dir / "kao_com_0729_0542"
    raw_dir = audit_root_dir / "_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    
    input_file = raw_dir / "53b4bee0825b7263.json"
    
    # Run helper
    detected_root = find_audit_root_dir(input_file)
    assert detected_root == audit_root_dir.resolve()
    
    # Scenario 2: Outside crawled_images
    other_dir = tmp_path / "other_folder"
    other_dir.mkdir(parents=True, exist_ok=True)
    other_file = other_dir / "report.json"
    
    detected_other_root = find_audit_root_dir(other_file)
    assert detected_other_root == other_dir.resolve()

