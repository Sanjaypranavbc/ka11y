"""
Smoke tests for the FastAPI app and combined.py pure-Python helpers.

These tests run entirely in-process — no Playwright, no Docker, no Node service.
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ka11y.main import app
from ka11y.api.v1.combined import (
    _make_finding,
    _build_report,
    _alt_text_to_findings,
    _form_to_findings,
    _lin_to_findings,
    _psh_to_findings,
    _ts_to_findings,
)
from ka11y.api.v1.combined.findings import _lang_ctx


# ─────────────────────────────────────────────────────────────────────────────
# App startup / routing smoke tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


class TestAppStartup:
    def test_docs_endpoint_returns_200(self, client):
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_openapi_json_is_valid(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        data = resp.json()
        assert "openapi" in data
        assert data["info"]["title"] == "ka11y"

    def test_pipeline_post_requires_url(self, client):
        resp = client.post("/api/v1/pipeline/", json={})
        # Missing required field → 422 Unprocessable Entity
        assert resp.status_code == 422

    def test_combined_get_unknown_job_returns_404(self, client):
        resp = client.get("/api/v1/combined/nonexistent-job-id")
        assert resp.status_code == 404

    def test_combined_post_requires_url(self, client):
        resp = client.post("/api/v1/combined/", json={})
        assert resp.status_code == 422

    def test_combined_post_accepts_valid_url(self, client):
        """POST returns 202 immediately and a job_id — does NOT run the full pipeline."""
        resp = client.post(
            "/api/v1/combined/",
            json={"url": "https://example.com"},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert "job_id" in body
        assert body["status"] in ("pending", "running")
        assert body["url"] == "https://example.com/"

    def test_combined_get_known_job_returns_200(self, client):
        # Submit a job, then immediately poll it
        post = client.post("/api/v1/combined/", json={"url": "https://example.com"})
        job_id = post.json()["job_id"]
        get = client.get(f"/api/v1/combined/{job_id}")
        assert get.status_code == 200
        assert get.json()["job_id"] == job_id

    def test_combined_post_rejects_invalid_success_criteria_id(self, client):
        resp = client.post(
            "/api/v1/combined/",
            json={"url": "https://example.com", "success_criteria_id": "bad-id"},
        )
        assert resp.status_code == 422

    def test_combined_request_rejects_disabled_required_stage_for_filtered_rule(self):
        from ka11y.api.v1.combined.models import CombinedRequest

        with pytest.raises(ValidationError):
            CombinedRequest(
                url="https://example.com",
                success_criteria_id="1.4.3",
                run_ocr=False,
            )


# ─────────────────────────────────────────────────────────────────────────────
# _make_finding
# ─────────────────────────────────────────────────────────────────────────────

class TestMakeFinding:
    def _fail(self, **kw):
        defaults = dict(
            source="python",
            rule_id="python_1_1_1_alt",
            wcag_sc="1.1.1",
            status="fail",
            reason="Missing alt text",
            severity="critical",
            element_html="<img src='x.png'>",
            element_id=None,
            element_tag="IMG",
            page_url="https://example.com",
        )
        defaults.update(kw)
        return _make_finding(**defaults)

    def _pass(self, **kw):
        defaults = dict(
            source="python",
            rule_id="python_1_1_1_alt",
            wcag_sc="1.1.1",
            status="pass",
            reason="Image has alt text",
            severity=None,
            page_url="https://example.com",
        )
        defaults.update(kw)
        return _make_finding(**defaults)

    def test_fail_finding_has_element(self):
        f = self._fail()
        assert f["element"] is not None
        assert f["element"]["tag"] == "IMG"

    def test_pass_finding_has_no_element(self):
        f = self._pass()
        assert f["element"] is None

    def test_pass_finding_severity_is_none(self):
        f = self._pass()
        assert f["severity"] is None

    def test_fail_finding_has_suggested_fix(self):
        f = self._fail()
        assert f["suggested_fix"] is not None
        assert len(f["suggested_fix"]) > 0

    def test_pass_finding_has_no_suggested_fix(self):
        f = self._pass()
        assert f["suggested_fix"] is None

    def test_criterion_name_populated(self):
        f = self._fail()
        assert f["criterion_name"] == "Non-text Content"

    def test_level_populated(self):
        f = self._fail()
        assert f["level"] == "A"

    def test_html_truncated_at_600(self):
        long_html = "<img " + "a" * 700 + ">"
        f = self._fail(element_html=long_html)
        assert len(f["element"]["html"]) <= 600

    def test_unknown_wcag_sc_gives_none_criterion(self):
        f = _make_finding(
            source="python",
            rule_id="python_x",
            wcag_sc="9.9.9",
            status="fail",
            reason="Unknown",
            severity="low",
        )
        assert f["criterion_name"] is None

    def test_source_preserved(self):
        f = self._fail(source="axe")
        assert f["source"] == "axe"

    def test_rule_id_preserved(self):
        f = self._fail(rule_id="my_rule")
        assert f["rule_id"] == "my_rule"


# ─────────────────────────────────────────────────────────────────────────────
# _build_report
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildReport:
    def _findings(self):
        return [
            _make_finding(
                source="python", rule_id="python_1_1_1_alt", wcag_sc="1.1.1",
                status="fail", reason="No alt", severity="critical",
                element_html="<img>", page_url="https://x.com",
            ),
            _make_finding(
                source="axe", rule_id="axe_rule", wcag_sc="2.4.4",
                status="needs_review", reason="Possible issue", severity="medium",
                element_html="<a>", page_url="https://x.com",
            ),
            _make_finding(
                source="python", rule_id="python_1_1_1_alt", wcag_sc="1.1.1",
                status="pass", reason="OK", severity=None,
                page_url="https://x.com",
            ),
        ]

    def test_url_preserved(self):
        r = _build_report("https://x.com", self._findings())
        assert r["url"] == "https://x.com"

    def test_generated_at_present(self):
        r = _build_report("https://x.com", self._findings())
        assert "generated_at" in r
        assert r["generated_at"]  # non-empty

    def test_summary_counts(self):
        r = _build_report("https://x.com", self._findings())
        s = r["summary"]
        assert s["total_findings"] == 3
        assert s["violations"] == 1
        assert s["needs_review"] == 1
        assert s["passes"] == 1

    def test_violations_list_length(self):
        r = _build_report("https://x.com", self._findings())
        assert len(r["violations"]) == 1

    def test_passes_list_length(self):
        r = _build_report("https://x.com", self._findings())
        assert len(r["passes"]) == 1

    def test_by_severity_critical_count(self):
        r = _build_report("https://x.com", self._findings())
        assert r["summary"]["by_severity"]["critical"] == 1

    def test_by_severity_medium_count(self):
        r = _build_report("https://x.com", self._findings())
        assert r["summary"]["by_severity"]["medium"] == 1

    def test_by_source_counts(self):
        r = _build_report("https://x.com", self._findings())
        src = r["summary"]["by_source"]
        assert src["python"]["violations"] == 1
        assert src["axe"]["needs_review"] == 1

    def test_empty_findings_returns_zero_summary(self):
        r = _build_report("https://x.com", [])
        s = r["summary"]
        assert s["total_findings"] == 0
        assert s["violations"] == 0
        assert s["needs_review"] == 0
        assert s["passes"] == 0

    def test_by_wcag_sc_present(self):
        r = _build_report("https://x.com", self._findings())
        assert "1.1.1" in r["summary"]["by_wcag_sc"]

    def test_by_level_present(self):
        r = _build_report("https://x.com", self._findings())
        assert "A" in r["summary"]["by_level"]


# ─────────────────────────────────────────────────────────────────────────────
# Converter helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestConverterHelpers:
    PAGE = "https://example.com"

    # ── _alt_text_to_findings ──────────────────────────────────────────────

    def test_alt_text_failed_emits_fail_finding(self):
        records = [{"wcag_1_1_1_status": "FAILED", "wcag_1_1_1_violation": "No alt", "html_snippet": "<img>", "src": "x.png"}]
        findings = _alt_text_to_findings(records, self.PAGE)
        assert len(findings) == 1
        assert findings[0]["status"] == "fail"

    def test_alt_text_passed_emits_pass_finding(self):
        records = [{"wcag_1_1_1_status": "PASSED", "html_snippet": "<img alt='ok'>", "src": "x.png"}]
        findings = _alt_text_to_findings(records, self.PAGE)
        assert len(findings) == 1
        assert findings[0]["status"] == "pass"

    def test_alt_text_unknown_status_emits_nothing(self):
        records = [{"wcag_1_1_1_status": "SKIPPED"}]
        findings = _alt_text_to_findings(records, self.PAGE)
        assert findings == []

    def test_alt_text_fallback_reason_uses_localised_rule_description(self):
        token = _lang_ctx.set("ja")
        try:
            records = [{"wcag_1_1_1_status": "FAILED", "src": "x.png"}]
            findings = _alt_text_to_findings(records, self.PAGE)
            assert len(findings) == 1
            assert findings[0]["reason"].startswith("利用者に提示されるすべての非テキストコンテンツ")
        finally:
            _lang_ctx.reset(token)

    # ── _form_to_findings ─────────────────────────────────────────────────

    def test_form_failed_3_3_1_emits_fail(self):
        records = [{
            "wcag_3_3_1_status": "FAILED", "wcag_3_3_1_violations": "no aria-describedby",
            "wcag_3_3_2_status": "PASSED", "html_snippet": "<input>", "tag": "INPUT",
        }]
        findings = _form_to_findings(records, self.PAGE)
        fail_scs = [f["wcag_sc"] for f in findings if f["status"] == "fail"]
        assert "3.3.1" in fail_scs

    def test_form_failed_3_3_2_emits_fail(self):
        records = [{
            "wcag_3_3_1_status": "PASSED",
            "wcag_3_3_2_status": "FAILED", "wcag_3_3_2_violations": "no label",
            "html_snippet": "<input>", "tag": "INPUT",
        }]
        findings = _form_to_findings(records, self.PAGE)
        fail_scs = [f["wcag_sc"] for f in findings if f["status"] == "fail"]
        assert "3.3.2" in fail_scs

    def test_form_both_passed_emits_two_pass_findings(self):
        records = [{
            "wcag_3_3_1_status": "PASSED",
            "wcag_3_3_2_status": "PASSED",
            "html_snippet": "<input>", "tag": "INPUT",
        }]
        findings = _form_to_findings(records, self.PAGE)
        assert all(f["status"] == "pass" for f in findings)
        assert len(findings) == 2

    # ── _lin_to_findings ──────────────────────────────────────────────────

    def test_lin_failed_emits_fail(self):
        records = [{"wcag_2_5_3_status": "FAILED", "wcag_2_5_3_violation": "mismatch", "html_snippet": "<button>", "tag": "BUTTON"}]
        findings = _lin_to_findings(records, self.PAGE)
        assert len(findings) == 1
        assert findings[0]["status"] == "fail"

    def test_lin_na_status_skipped(self):
        records = [{"wcag_2_5_3_status": "N/A"}]
        findings = _lin_to_findings(records, self.PAGE)
        assert findings == []

    def test_lin_passed_emits_pass(self):
        records = [{"wcag_2_5_3_status": "PASSED", "html_snippet": "<button>", "tag": "BUTTON"}]
        findings = _lin_to_findings(records, self.PAGE)
        assert findings[0]["status"] == "pass"

    # ── _psh_to_findings ──────────────────────────────────────────────────

    def test_psh_failed_emits_fail(self):
        records = [{"wcag_2_2_2_status": "FAILED", "wcag_2_2_2_violation": "no pause", "html_snippet": "<video>", "tag": "VIDEO"}]
        findings = _psh_to_findings(records, self.PAGE)
        assert findings[0]["status"] == "fail"

    def test_psh_passed_emits_pass(self):
        records = [{"wcag_2_2_2_status": "PASSED", "html_snippet": "<video>", "tag": "VIDEO"}]
        findings = _psh_to_findings(records, self.PAGE)
        assert findings[0]["status"] == "pass"

    # ── _ts_to_findings ───────────────────────────────────────────────────

    def test_ts_failed_emits_fail(self):
        records = [{
            "wcag_2_5_8_status": "FAILED", "wcag_2_5_8_violation": "too small",
            "html_snippet": "<button>", "tag": "BUTTON",
            "rendered_width_px": 16, "rendered_height_px": 16,
        }]
        findings = _ts_to_findings(records, self.PAGE)
        assert findings[0]["status"] == "fail"

    def test_ts_na_status_skipped(self):
        records = [{"wcag_2_5_8_status": "N/A"}]
        findings = _ts_to_findings(records, self.PAGE)
        assert findings == []

    def test_ts_passed_emits_pass_with_size_in_reason(self):
        records = [{
            "wcag_2_5_8_status": "PASSED",
            "html_snippet": "<button>", "tag": "BUTTON",
            "rendered_width_px": 44, "rendered_height_px": 44,
        }]
        findings = _ts_to_findings(records, self.PAGE)
        assert findings[0]["status"] == "pass"
        assert "44" in findings[0]["reason"]
