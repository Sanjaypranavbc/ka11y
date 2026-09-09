"""Tests for enrich_audit.py — the Gemini enrichment step that adds a dynamic
reason and suggested fix to each violation.

Every test stubs out call_gemini_batch(); nothing here touches the network.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# enrich_audit.py sits beside the `ka11y` package rather than inside it, so it
# is importable only once ka11y-python/ itself is on sys.path — the same thing
# runner._ensure_ka11y_python_root_on_sys_path() does at runtime.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import enrich_audit  # noqa: E402
from enrich_audit import (  # noqa: E402
    build_system_instruction,
    chunk_list,
    trim_finding,
    validate_report,
)


class _FakeItem:
    """Stand-in for an EnrichedFinding returned by the model."""

    def __init__(self, finding_id: str):
        self.finding_id = finding_id
        self.dynamic_reason = f"dynamic reason for {finding_id}"
        self.dynamic_suggested_fix = f"dynamic fix for {finding_id}"
        self.user_impact = "impact"
        self.confidence = "high"


def _finding(fid: str = "f1") -> dict:
    return {
        "finding_id": fid,
        "rule_id": "image-text",
        "wcag_sc": "1.4.5",
        "severity": "medium",
        "reason": "static reason",
        "suggested_fix": "static fix",
        "element": {"tag": "img", "html": "<img alt=''>", "image_src": "/a.png"},
    }


# ── validation ────────────────────────────────────────────────────────────────
def test_validate_report_accepts_valid_report():
    validate_report({"violations": []})


@pytest.mark.parametrize(
    "report, message",
    [
        ([], "must be a JSON object"),
        ({"url": "https://example.com"}, "missing the required 'violations' key"),
        ({"violations": "not-a-list"}, "'violations' must be a JSON array"),
    ],
)
def test_validate_report_rejects_bad_shapes(report, message):
    with pytest.raises(ValueError, match=message):
        validate_report(report)


# ── prompt / batching helpers ────────────────────────────────────────────────
def test_trim_finding_drops_fields_the_model_does_not_need():
    trimmed = trim_finding(_finding())
    assert trimmed["existing_reason"] == "static reason"
    assert trimmed["existing_suggested_fix"] == "static fix"
    # `image_src` is a local path with no meaning to the model — only the four
    # whitelisted element keys survive, keeping input tokens down.
    assert set(trimmed["element"]) == {"tag", "html"}


def test_chunk_list_splits_on_batch_size():
    assert chunk_list([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_build_system_instruction_adds_language_directive_only_for_non_english():
    assert "OUTPUT LANGUAGE" not in build_system_instruction("en")
    ja = build_system_instruction("ja")
    assert "OUTPUT LANGUAGE" in ja and "Japanese" in ja


# ── enrichment ───────────────────────────────────────────────────────────────
def test_enrich_report_in_pipeline_mutates_caller_findings_in_place(tmp_path, monkeypatch):
    """The pipeline entry point must enrich the caller's own dicts: the runner
    hands the same `report` on to the DB save, the websocket broadcast and the
    API response, so a deepcopy would strand the dynamic fields in the file."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    finding = _finding()
    # report["pages"] holds the *same* finding objects as the flat arrays (see
    # combined/report.py::_build_report), so enriching once must show up in both.
    report = {"violations": [finding], "pages": [{"page_url": "https://x.test/", "violations": [finding]}]}

    with patch.object(enrich_audit.genai, "Client"), patch.object(
        enrich_audit, "call_gemini_batch", return_value=([_FakeItem("f1")], None, 0)
    ):
        usage = enrich_audit.enrich_report_in_pipeline(report, tmp_path)

    assert finding["dynamic_reason"] == "dynamic reason for f1"
    assert finding["dynamic_suggested_fix"] == "dynamic fix for f1"
    assert report["pages"][0]["violations"][0]["dynamic_reason"] == "dynamic reason for f1"
    # The static fields stay put so consumers can fall back to them.
    assert finding["reason"] == "static reason"
    assert usage["violations_enriched"] == 1

    written = json.loads((tmp_path / "enriched_report.json").read_text(encoding="utf-8"))
    assert written["violations"][0]["dynamic_reason"] == "dynamic reason for f1"
    assert (tmp_path / "token_usage.json").is_file()
    assert (tmp_path / "pages" / "page_1_x-test.json").is_file()


def test_run_enrichment_without_mutate_in_place_leaves_caller_report_untouched(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    finding = _finding()
    report = {"violations": [finding]}

    with patch.object(enrich_audit.genai, "Client"), patch.object(
        enrich_audit, "call_gemini_batch", return_value=([_FakeItem("f1")], None, 0)
    ):
        enrich_audit.run_enrichment(report, tmp_path, print_table=False)

    assert "dynamic_reason" not in finding


def test_missing_api_key_writes_unenriched_report_instead_of_raising(tmp_path, monkeypatch):
    """The runner calls this best-effort, but it must not raise even so: a
    missing key should degrade to the static reason/fix, not fail the audit."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(enrich_audit, "load_dotenv", lambda *a, **k: None)
    report = {"violations": [_finding()]}

    usage = enrich_audit.run_enrichment(report, tmp_path, print_table=False)

    assert usage["totals"]["api_calls"] == 0
    assert (tmp_path / "enriched_report.json").is_file()


def test_batch_failure_marks_findings_rather_than_propagating(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    finding = _finding()
    report = {"violations": [finding]}

    with patch.object(enrich_audit.genai, "Client"), patch.object(
        enrich_audit, "call_gemini_batch", side_effect=RuntimeError("boom")
    ):
        usage = enrich_audit.run_enrichment(
            report, tmp_path, print_table=False, mutate_in_place=True
        )

    assert finding["dynamic_enrichment_failed"] is True
    assert "dynamic_reason" not in finding
    assert usage["totals"]["failures"] == 1
