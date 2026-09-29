"""
WCAG Situation/Technique tagging — map generation, finding enrichment, the
frontend strip boundary and the four-format report export.

Runs in-process: no browser, no Node service. The PDF format is exercised by
stubbing the Chromium renderer (a real render needs the crawler browser pool).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ka11y.accessibility.technique_map import (
    TECHNIQUE_FIELDS,
    TechniqueTable,
    annotate_finding,
    load_table,
    strip_failure_techniques,
)
from ka11y.api.v1.combined import _build_report, _make_finding
from ka11y.api.v1.combined.store import _jobs
from ka11y.main import app
from ka11y.utils.report_csv import EXPORT_CSV_HEADERS, build_export_csv
from ka11y.utils.report_pdf import build_report_html

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
import build_technique_map as btm  # noqa: E402

HEADER = [
    "SC", "Situation", "Technique", "Test Website URL", "Success Explaination",
    "Failure Explaination", "Status", "Technique Cover", "Technique ID", "Code Evidence",
]


def _row(sc, situation, technique, cover, tid, evidence):
    return [sc, situation, technique, None, None, None, "Not Started", cover, tid, evidence]


ROWS = [
    _row("2.4.2", "Sufficient", "G88: Providing descriptive titles for Web pages", "Implemented", "G88",
         "ka11y-node/src/custom-checks/page-titled.check.js:78\nImplemented 2026-09-23"),
    # Blank Situation → forward-filled from the row above.
    _row("2.4.2", None, "H25: Providing a title using the title element", "Implemented", "H25",
         "ka11y-node/src/utils/rulesGuide.js:5"),
    _row("2.4.2", "Advisory", "Techniques for identifying the site:", "No Status", None, None),  # placeholder
    _row("1.1.1", "A", "Technique G94: Providing short text alternative for non-text content ", "Partially Implemented",
         "G94", "ka11y-python/ka11y/accessibility/rules/non_text/alttext.py:583"),
    _row("1.1.1", "B", "G94: Providing short text alternative", "Partially Implemented", "G94",
         "ka11y-python/ka11y/accessibility/rules/non_text/alttext.py:583"),  # same technique, 2nd situation
    _row("1.1.1", "A", "H37: Using alt attributes on img elements", "Not Implemented", "H37",
         "ka11y-node/src/config/app.config.js:52"),
    _row("1.1.1", "C", "ARIA6: Using aria-label to provide labels for objects", "implemented", "ARIA6",
         "ka11y-node/src/custom-checks/non-text-content.check.js:6"),
]
GUIDE_INDEX = [(1, "accesskeys"), (4, "document-title"), (9, "image-alt")]


@pytest.fixture
def doc():
    return btm.build_map(HEADER, ROWS, guide_index=GUIDE_INDEX, source="test.xlsx")


RULES = {"rules": {
    "custom-page-titled": {"techniques": ["G88", "H25"], "by_issue_type": {"generic-title": ["G88"]}},
    "python_1_1_1_alt": {"techniques": ["G94"], "by_reason_code": {"labelledby_unresolved": ["ARIA6"]}},
    "custom-nothing": {"techniques": [], "note": "no technique exists"},
}}


@pytest.fixture
def table(doc):
    return TechniqueTable(doc, RULES)


# ── Step 1: map generation ───────────────────────────────────────────────────

class TestBuildMap:
    def test_groups_by_sc_and_skips_placeholders(self, doc):
        assert list(doc["by_sc"]) == ["1.1.1", "2.4.2"]  # numeric SC order
        assert doc["technique_count"] == 5  # G94 collapsed, placeholder dropped
        assert doc["skipped"] == 1
        assert [e["id"] for e in doc["by_sc"]["2.4.2"]] == ["G88", "H25"]

    def test_forward_fills_blank_situation(self, doc):
        h25 = doc["by_sc"]["2.4.2"][1]
        assert h25["situation"] == "Sufficient"

    def test_technique_name_strips_id_prefix(self, doc):
        g94 = doc["by_sc"]["1.1.1"][0]
        assert g94["name"] == "Providing short text alternative for non-text content"
        assert g94["also_situations"] == ["B"]

    def test_cover_is_canonicalised(self, doc):
        aria6 = next(e for e in doc["by_sc"]["1.1.1"] if e["id"] == "ARIA6")
        assert aria6["cover"] == "Implemented"
        assert doc["cover_counts"] == {"Implemented": 3, "Partially Implemented": 1, "Not Implemented": 1}

    def test_code_evidence_resolves_to_rules_and_engines(self, doc):
        by_id = {e["id"]: e for e in doc["by_sc"]["2.4.2"] + doc["by_sc"]["1.1.1"]}
        assert by_id["G88"]["rules"] == ["custom-page-titled"] and by_id["G88"]["engines"] == ["custom"]
        assert by_id["H25"]["rules"] == ["document-title"] and by_id["H25"]["engines"] == ["axe"]
        assert by_id["G94"]["rules"] == [] and by_id["G94"]["engines"] == ["python"]
        assert by_id["H37"]["rules"] == [] and by_id["H37"]["engines"] == ["axe"]
        assert by_id["G88"]["evidence"] == ["ka11y-node/src/custom-checks/page-titled.check.js"]

    def test_cli_end_to_end(self, tmp_path):
        openpyxl = pytest.importorskip("openpyxl")
        wb = openpyxl.Workbook()
        wb.active.title = "Summary"
        ws = wb.create_sheet("All Techniques")
        ws.append(HEADER)
        for r in ROWS:
            ws.append(r)
        xlsx = tmp_path / "WCAG_Testing_Report_CodeCoverage.xlsx"
        wb.save(xlsx)
        guide = tmp_path / "ka11y-node" / "src" / "utils" / "rulesGuide.js"
        guide.parent.mkdir(parents=True)
        guide.write_text(
            "const rulesGuide = {\n  'accesskeys': {\n    x: 1,\n  },\n  'document-title': {\n    x: 2,\n  },\n};\n"
        )
        out = tmp_path / "map.json"
        assert btm.main(["--xlsx", str(xlsx), "--out", str(out), "--repo-root", str(tmp_path), "--supplement", ""]) == 0
        data = json.loads(out.read_text())
        assert data["source"] == xlsx.name and data["technique_count"] == 5
        assert data["by_sc"]["2.4.2"][1]["rules"] == ["document-title"]
        # a supplement adds SCs the workbook lacks and never overrides its rows
        supp = tmp_path / "supp.json"
        supp.write_text(json.dumps({"by_sc": {
            "2.5.7": [{"id": "G219", "name": "Dragging alternative", "situation": "Sufficient", "cover": "Implemented", "rules": ["custom-dragging-movements"], "engines": ["custom"], "evidence": []}],
            "2.4.2": [{"id": "G88", "name": "OVERRIDE", "situation": "X", "cover": "Not Implemented", "rules": [], "engines": [], "evidence": []}],
        }}))
        assert btm.main(["--xlsx", str(xlsx), "--out", str(out), "--repo-root", str(tmp_path), "--supplement", str(supp)]) == 0
        data = json.loads(out.read_text())
        assert data["technique_count"] == 6 and data["supplement_count"] == 1
        assert data["by_sc"]["2.5.7"][0]["supplement"] is True
        assert data["by_sc"]["2.4.2"][0]["name"] != "OVERRIDE"

    def test_committed_map_is_current_shape(self):
        table = load_table()
        assert table.meta["schema_version"] == 1
        assert table.meta["technique_count"] > 400
        assert table.find("G88", "2.4.2")["rules"] == ["custom-page-titled"]
        assert table.find("H25", "2.4.2")["rules"] == ["document-title"]
        # WCAG 2.2 supplement merged in
        assert table.find("C43", "2.4.11")["supplement"] is True
        assert table.meta["supplement_count"] >= 13

    def test_rule_table_ids_all_resolve(self):
        table = load_table()
        assert table.rules, "rule-techniques.json loaded"
        unresolved = set()
        for rid, e in table.rules.items():
            groups = [e.get("techniques") or []]
            groups += list((e.get("by_reason_code") or {}).values())
            groups += list((e.get("by_issue_type") or {}).values())
            for tid in (t for g in groups for t in g):
                if table.find(tid) is None:
                    unresolved.add((rid, tid))
        assert not unresolved


# ── Step 3: enrichment tiers ─────────────────────────────────────────────────

def _f(**kw):
    base = {"wcag_sc": "2.4.2", "rule_id": "custom-page-titled", "source": "custom", "status": "fail"}
    base.update(kw)
    return base


class TestAnnotate:
    def test_exact_technique_id_from_check_wins(self, table):
        f = annotate_finding(_f(technique_id="H25"), table)
        assert f["technique_match"] == "exact"
        assert [t["id"] for t in f["techniques"]] == ["H25"]
        assert f["situations"] == ["Sufficient"]

    def test_exact_from_pdf_rule_id(self, table):
        real = load_table()
        f = annotate_finding({"wcag_sc": "1.4.10", "rule_id": "python_pdf_pdf1", "source": "python", "status": "pass"}, real)
        assert f["technique_match"] == "exact" and f["techniques"][0]["id"] == "PDF1"

    def test_issue_type_narrows_a_failure(self, table):
        f = annotate_finding(_f(issue_type="generic-title"), table)
        assert f["technique_match"] == "issue" and [t["id"] for t in f["techniques"]] == ["G88"]
        # an issue type the table does not know falls back to the check-level set
        f = annotate_finding(_f(issue_type="something-else"), table)
        assert f["technique_match"] == "rule" and [t["id"] for t in f["techniques"]] == ["G88", "H25"]

    def test_reason_code_narrows_a_failure(self, table):
        f = annotate_finding(_f(wcag_sc="1.1.1", rule_id="python_1_1_1_alt", source="python",
                               reason_code="labelledby_unresolved"), table)
        assert f["technique_match"] == "reason" and [t["id"] for t in f["techniques"]] == ["ARIA6"]
        f = annotate_finding(_f(wcag_sc="1.1.1", rule_id="python_1_1_1_alt", source="python", status="pass"), table)
        assert f["technique_match"] == "rule" and [t["id"] for t in f["techniques"]] == ["G94"]
        assert f["techniques"][0]["situations"] == ["A", "B"] and f["situations"] == ["A", "B"]

    def test_sub_rule_falls_back_to_base_entry(self, table):
        f = annotate_finding(_f(rule_id="custom-page-titled-review"), table)
        assert f["technique_match"] == "rule" and [t["id"] for t in f["techniques"]] == ["G88", "H25"]

    def test_code_evidence_when_no_table_entry(self, table):
        axe = annotate_finding(_f(rule_id="document-title", source="axe"), table)
        assert axe["technique_match"] == "evidence" and axe["techniques"][0]["id"] == "H25"

    def test_explicit_empty_entry_and_unknown_rule_are_unmapped(self, table):
        f = annotate_finding(_f(wcag_sc="1.1.1", rule_id="custom-nothing", source="custom"), table)
        assert f["technique_match"] == "none" and f["techniques"] == [] and f["situations"] == []
        # no engine-wide / SC-wide fallback any more
        f = annotate_finding(_f(wcag_sc="1.1.1", rule_id="python_1_1_1_other", source="python"), table)
        assert f["technique_match"] == "none" and f["techniques"] == []
        f = annotate_finding(_f(wcag_sc="9.9.9"), table)
        assert f["technique_match"] == "rule"  # table entry exists; SC missing is irrelevant

    def test_committed_tables_narrow_the_known_wide_cases(self):
        real = load_table()
        alt = annotate_finding({"wcag_sc": "1.1.1", "rule_id": "python_1_1_1_alt", "source": "python",
                                "status": "fail", "reason_code": "missing_alt"}, real)
        assert [t["id"] for t in alt["techniques"]] == ["H37"]
        contrast = annotate_finding({"wcag_sc": "1.4.3", "rule_id": "python_1_4_3_contrast", "source": "python",
                                     "status": "fail"}, real)
        assert [t["id"] for t in contrast["techniques"]] == ["G145"] and contrast["situations"] == ["B"]
        reflow = annotate_finding({"wcag_sc": "1.4.10", "rule_id": "custom-reflow", "source": "custom",
                                   "status": "fail", "issue_type": "sticky-consumes-viewport"}, real)
        assert [t["id"] for t in reflow["techniques"]] == ["C34"]
        aria = annotate_finding({"wcag_sc": "4.1.2", "rule_id": "aria-valid-attr", "source": "axe", "status": "fail"}, real)
        assert [t["id"] for t in aria["techniques"]] == ["ARIA5"]
        wcag22 = annotate_finding({"wcag_sc": "2.5.7", "rule_id": "custom-dragging-movements", "source": "custom",
                                   "status": "fail"}, real)
        assert [t["id"] for t in wcag22["techniques"]] == ["G219"]

    def test_public_entry_shape(self, table):
        t = annotate_finding(_f(), table)["techniques"][0]
        assert set(t) == {"id", "name", "situations", "cover"}


# ── Steps 3 + 4 through the real report builder ──────────────────────────────

def _report():
    findings = [
        _make_finding(source="python", rule_id="python_1_1_1_alt", wcag_sc="1.1.1", status="fail",
                      severity="high", reason="missing alt", element_html="<img src='a.png'>",
                      element_selector="img#a", page_url="https://example.com/"),
        _make_finding(source="python", rule_id="python_1_1_1_alt", wcag_sc="1.1.1", status="needs_review",
                      severity="medium", reason="check alt", element_selector="img#b",
                      page_url="https://example.com/"),
        _make_finding(source="python", rule_id="python_1_1_1_alt", wcag_sc="1.1.1", status="pass",
                      severity=None, reason="alt ok", element_selector="img#c", page_url="https://example.com/"),
    ]
    findings.append({**findings[0], "source": "custom", "rule_id": "custom-page-titled", "wcag_sc": "2.4.2",
                     "technique_id": "G88", "element": {**findings[0]["element"], "selector": "title"}})
    return _build_report("https://example.com", findings, lang="en")


class TestReportEnrichment:
    def test_every_status_is_tagged(self):
        report = _report()
        for bucket in ("violations", "needs_review", "passes"):
            for f in report[bucket]:
                assert f["techniques"], (bucket, f["rule_id"])
                assert f["situations"]
        exact = next(f for f in report["violations"] if f["rule_id"] == "custom-page-titled")
        assert exact["technique_match"] == "exact" and exact["techniques"][0]["id"] == "G88"

    def test_strip_keeps_passes_only_and_leaves_source_intact(self):
        report = _report()
        stripped = strip_failure_techniques(report)
        for bucket in ("violations", "needs_review"):
            for f in stripped[bucket]:
                assert not any(k in f for k in TECHNIQUE_FIELDS), bucket
            for f in stripped["pages"][0][bucket]:
                assert "techniques" not in f
        assert all(f["techniques"] for f in stripped["passes"])
        assert all(f["techniques"] for f in stripped["pages"][0]["passes"])
        # the original (hot cache / run store) still carries everything
        assert all(f["techniques"] for f in report["violations"])
        assert all("technique_id" in f or f["techniques"] for f in report["needs_review"])


# ── Steps 4 + 5 over HTTP ────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def hot_job():
    job_id = "technique-test-job"
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


class TestFrontendBoundary:
    def test_get_job_strips_failures_keeps_passes(self, client, hot_job):
        data = client.get(f"/api/v1/combined/{hot_job}").json()
        result = data["result"]
        for f in result["violations"] + result["needs_review"]:
            assert "techniques" not in f and "situations" not in f and "technique_id" not in f
        assert all(f["techniques"] and f["situations"] for f in result["passes"])
        # the hot-cache copy is untouched, so the export still has everything
        assert all(f["techniques"] for f in _jobs[hot_job]["result"]["violations"])


class TestExport:
    def test_json_has_techniques_on_every_finding(self, client, hot_job):
        r = client.get(f"/api/v1/combined/{hot_job}/export", params={"format": "json"})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/json")
        assert 'filename="example.com-accessibility-audit.json"' in r.headers["content-disposition"]
        report = json.loads(r.text)
        for bucket in ("violations", "needs_review", "passes"):
            assert all(f["techniques"] and f["situations"] for f in report[bucket])

    def test_csv_one_row_per_technique(self, client, hot_job):
        r = client.get(f"/api/v1/combined/{hot_job}/export", params={"format": "csv"})
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
        lines = r.text.rstrip("\n").split("\n")
        assert lines[0].split(",") == list(EXPORT_CSV_HEADERS)
        report = _jobs[hot_job]["result"]
        expected = sum(max(1, len(f["techniques"])) for b in ("violations", "needs_review", "passes") for f in report[b])
        assert len(lines) - 1 == expected
        idx = {h: i for i, h in enumerate(EXPORT_CSV_HEADERS)}
        import csv, io
        rows = list(csv.reader(io.StringIO(r.text)))[1:]
        g88 = next(row for row in rows if row[idx["Technique ID"]] == "G88")
        assert g88[idx["Status"]] == "fail" and g88[idx["Situation"]] == "Sufficient"
        assert g88[idx["Technique Cover"]] == "Implemented" and g88[idx["Technique Match"]] == "exact"
        assert {row[idx["Status"]] for row in rows} == {"fail", "needs_review", "pass"}

    def test_html_lists_techniques_and_legend(self, client, hot_job):
        r = client.get(f"/api/v1/combined/{hot_job}/export", params={"format": "html"})
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
        assert "<th>Techniques</th>" in r.text and "<th>Situations</th>" in r.text
        assert "Techniques referenced" in r.text
        assert ">G88</span>" in r.text

    def test_pdf_streams_renderer_output(self, client, hot_job, monkeypatch):
        import ka11y.utils.report_pdf as report_pdf

        async def fake_pdf(report):
            assert all(f["techniques"] for f in report["violations"])
            return b"%PDF-1.4 fake"

        monkeypatch.setattr(report_pdf, "build_report_pdf", fake_pdf)
        r = client.get(f"/api/v1/combined/{hot_job}/export", params={"format": "pdf"})
        assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
        assert r.content.startswith(b"%PDF")

    def test_pdf_unavailable_is_503(self, client, hot_job, monkeypatch):
        import ka11y.utils.report_pdf as report_pdf

        async def no_pdf(report):
            return None

        monkeypatch.setattr(report_pdf, "build_report_pdf", no_pdf)
        assert client.get(f"/api/v1/combined/{hot_job}/export", params={"format": "pdf"}).status_code == 503

    def test_bad_format_and_unknown_job(self, client, hot_job):
        assert client.get(f"/api/v1/combined/{hot_job}/export", params={"format": "xlsx"}).status_code == 422
        assert client.get("/api/v1/combined/no-such-job/export", params={"format": "json"}).status_code == 404


class TestBuilders:
    def test_export_csv_blank_technique_row_when_unmatched(self):
        report = {"url": "https://x.test", "violations": [{"wcag_sc": "9.9.9", "status": "fail", "techniques": [],
                                                           "technique_match": "none", "reason": "r, with comma"}]}
        text = build_export_csv(report)
        lines = text.rstrip("\n").split("\n")
        assert len(lines) == 2 and '"r, with comma"' in lines[1]

    def test_html_max_rows_none_renders_everything(self):
        report = _report()
        report["passes"] = report["passes"] * 250
        capped = build_report_html(report, {}, max_rows=200)
        full = build_report_html(report, {}, max_rows=None)
        assert "Showing the first 200 of 250" in capped
        assert "Showing the first" not in full
