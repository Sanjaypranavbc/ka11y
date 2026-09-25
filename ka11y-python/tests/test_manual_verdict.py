"""
Manual verdicts on needs_review findings: the overlay fields, the review
endpoint (transitions, guards, reviewer identity), and how the verdict shows
up in the frontend payload and the report exports.
"""

from __future__ import annotations

import csv
import io
import json

import pytest
from fastapi.testclient import TestClient

from ka11y.api.v1.combined import _build_report, _make_finding
from ka11y.api.v1.combined.report import REVIEW_FIELDS, apply_reviews, review_message
from ka11y.api.v1.combined.store import _jobs
from ka11y.main import app
from ka11y.store import repo
from ka11y.utils.report_csv import EXPORT_CSV_HEADERS


def _report(lang="en"):
    mk = lambda status, sel, **kw: _make_finding(  # noqa: E731
        source="python", rule_id="python_1_1_1_alt", wcag_sc="1.1.1", status=status,
        severity=None if status == "pass" else "medium", reason=f"{status} reason",
        element_selector=sel, page_url="https://example.com/", **kw,
    )
    findings = [mk("fail", "img#f"), mk("needs_review", "img#r1"), mk("needs_review", "img#r2"), mk("pass", "img#p")]
    return _build_report("https://example.com", findings, lang=lang)


class TestOverlay:
    def test_message_is_localized(self):
        assert review_message("pass", "en") == "Reviewed by user and manually changed to Pass."
        assert review_message("violation", "en") == "Reviewed by user and manually changed to Fail."
        assert review_message("violation", "ja") == "ユーザーがレビューし、手動で不合格に変更しました。"
        assert review_message("pass", "jp").endswith("合格に変更しました。")

    def test_apply_reviews_writes_audit_trail_and_clears_it(self):
        rep = _report()
        fid = rep["needs_review"][0]["finding_id"]
        apply_reviews(rep, {fid: {"status": "pass", "note": "fixed upstream", "reviewer": "qa@example.com",
                                  "updated_at": "2026-09-25T10:00:00+00:00"}})
        item = next(f for f in rep["passes"] if f["finding_id"] == fid)
        assert item["status"] == "needs_review"  # automated status untouched
        assert item["review_status"] == "pass" and item["reviewed"] is True
        assert item["verdict_source"] == "manual"
        assert item["reviewed_by"] == "qa@example.com"
        assert item["reviewed_at"] == "2026-09-25T10:00:00+00:00"
        assert item["review_message"] == "Reviewed by user and manually changed to Pass."
        assert item["review_note"] == "fixed upstream"
        # engine verdicts are marked as such and carry no review fields
        engine = [f for f in rep["violations"] + rep["passes"] + rep["needs_review"] if f["finding_id"] != fid]
        assert engine and all(f["verdict_source"] == "engine" for f in engine)
        assert all(not any(k in f for k in REVIEW_FIELDS) for f in engine)
        # clearing restores the item and drops every review field
        apply_reviews(rep, {})
        back = next(f for f in rep["needs_review"] if f["finding_id"] == fid)
        assert back["verdict_source"] == "engine" and not any(k in back for k in REVIEW_FIELDS)

    def test_japanese_report_gets_japanese_message(self):
        rep = _report(lang="ja")
        fid = rep["needs_review"][0]["finding_id"]
        apply_reviews(rep, {fid: {"status": "violation"}})
        item = next(f for f in rep["violations"] if f["finding_id"] == fid)
        assert item["review_message"] == "ユーザーがレビューし、手動で不合格に変更しました。"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def hot_job(client):
    job_id = "verdict-test-job"
    # finding_reviews has a FK to runs, so the run row must exist.
    client.portal.call(
        lambda: repo.create_run(
            run_id=job_id, url="https://example.com", status="completed", lang_requested="en",
            wcag_level="AA", params={}, max_depth=0, max_pages=1,
            submitted_at="2026-09-25T00:00:00+00:00",
        )
    )
    _jobs[job_id] = {
        "job_id": job_id, "status": "completed", "url": "https://example.com",
        "submitted_at": "2026-09-25T00:00:00+00:00", "lang": "en",
        "completed_at": "2026-09-25T00:01:00+00:00", "report_path": None,
        "result": _report(), "error": None, "stages": [], "warnings": [],
    }
    try:
        yield job_id
    finally:
        _jobs.pop(job_id, None)


def _get(client, job_id):
    return client.get(f"/api/v1/combined/{job_id}").json()["result"]


def _find(result, fid):
    for bucket in ("violations", "needs_review", "passes"):
        for f in result[bucket]:
            if f["finding_id"] == fid:
                return bucket, f
    raise AssertionError(fid)


class TestEndpoint:
    def test_pass_then_fail_then_reopen(self, client, hot_job):
        result = _get(client, hot_job)
        fid = result["needs_review"][0]["finding_id"]
        assert result["summary"]["needs_review"] == 2

        r = client.post(f"/api/v1/combined/{hot_job}/findings/{fid}/review", json={"status": "pass"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["verdict_source"] == "manual" and body["review_status"] == "pass"
        assert body["review_message"] == "Reviewed by user and manually changed to Pass."
        assert body["reviewed_by"] == "user" and body["reviewed_at"]  # anonymous in tests

        result = _get(client, hot_job)
        bucket, item = _find(result, fid)
        assert bucket == "passes"
        assert item["reviewed"] is True and item["verdict_source"] == "manual"
        assert item["review_message"].endswith("changed to Pass.")
        assert result["summary"] == {**result["summary"], "needs_review": 1, "passes": 2}
        # reviewed item is inside the page arrays too
        assert any(f["finding_id"] == fid for f in result["pages"][0]["passes"])

        # second verdict on the same item (it now sits in passes) must work
        r = client.post(f"/api/v1/combined/{hot_job}/findings/{fid}/review",
                        json={"status": "violation", "note": "contrast still 2.1:1"})
        assert r.status_code == 200, r.text
        bucket, item = _find(_get(client, hot_job), fid)
        assert bucket == "violations"
        assert item["review_status"] == "violation" and item["review_note"] == "contrast still 2.1:1"
        assert item["review_message"].endswith("changed to Fail.")

        # re-open
        r = client.post(f"/api/v1/combined/{hot_job}/findings/{fid}/review", json={"status": "needs_review"})
        assert r.status_code == 200 and r.json()["verdict_source"] == "engine"
        bucket, item = _find(_get(client, hot_job), fid)
        assert bucket == "needs_review" and not any(k in item for k in REVIEW_FIELDS)

    def test_engine_verdicts_cannot_be_overridden(self, client, hot_job):
        result = _get(client, hot_job)
        fail_id = next(f["finding_id"] for f in result["violations"] if f["status"] == "fail")
        pass_id = next(f["finding_id"] for f in result["passes"] if f["status"] == "pass")
        for fid in (fail_id, pass_id):
            r = client.post(f"/api/v1/combined/{hot_job}/findings/{fid}/review", json={"status": "pass"})
            assert r.status_code == 409, r.text
        r = client.post(f"/api/v1/combined/{hot_job}/findings/nope/review", json={"status": "pass"})
        assert r.status_code == 404
        r = client.post(f"/api/v1/combined/{hot_job}/findings/{fail_id}/review", json={"status": "maybe"})
        assert r.status_code == 422
        # untouched findings stay engine verdicts
        result = _get(client, hot_job)
        assert all(f["verdict_source"] == "engine" for f in result["violations"] + result["passes"])

    def test_verdict_flows_into_exports(self, client, hot_job):
        fid = _get(client, hot_job)["needs_review"][0]["finding_id"]
        assert client.post(f"/api/v1/combined/{hot_job}/findings/{fid}/review",
                           json={"status": "pass", "note": "checked by hand"}).status_code == 200

        js = json.loads(client.get(f"/api/v1/combined/{hot_job}/export", params={"format": "json"}).text)
        item = next(f for f in js["passes"] if f["finding_id"] == fid)
        assert item["verdict_source"] == "manual" and item["review_message"] and item["reviewed_by"]

        text = client.get(f"/api/v1/combined/{hot_job}/export", params={"format": "csv"}).text
        rows = list(csv.reader(io.StringIO(text)))
        idx = {h: i for i, h in enumerate(EXPORT_CSV_HEADERS)}
        manual = [r for r in rows[1:] if r[idx["Verdict Source"]] == "manual"]
        assert manual and manual[0][idx["Review Status"]] == "pass"
        assert manual[0][idx["Review Message"]] == "Reviewed by user and manually changed to Pass."
        assert manual[0][idx["Review Note"]] == "checked by hand" and manual[0][idx["Reviewed By"]] == "user"
        assert all(r[idx["Verdict Source"]] == "engine" for r in rows[1:] if r[idx["Rule ID"]] and r not in manual)

        html = client.get(f"/api/v1/combined/{hot_job}/export", params={"format": "html"}).text
        assert "<th>Review</th>" in html
        assert "Reviewed by user and manually changed to Pass." in html and "checked by hand" in html
