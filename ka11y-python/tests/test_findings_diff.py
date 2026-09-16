"""Unit tests for scripts/findings_diff.py normalisation + diff."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "findings_diff.py"


@pytest.fixture(scope="module")
def fd():
    spec = importlib.util.spec_from_file_location("findings_diff", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _finding(sc, page, status, **element):
    return {"wcag_sc": sc, "status": status, "element": {"page_url": page, **element}}


def test_normalise_keys_by_rule_page_and_element(fd):
    n = fd.normalise(
        [
            _finding("1.1.1", "https://a/", "fail", image_src="https://a/x.png"),
            _finding("1.1.1", "https://a/", "pass", selector="img.hero"),
            _finding("1.2.1", "https://a/", "needs_review", ref_id="media_abc"),
        ]
    )
    assert n == {
        "1.1.1\thttps://a/\timage_src=https://a/x.png": "fail",
        "1.1.1\thttps://a/\tselector=img.hero": "pass",
        "1.2.1\thttps://a/\tref_id=media_abc": "needs_review",
    }


def test_normalise_keeps_worst_status_on_duplicate_key(fd):
    n = fd.normalise(
        [
            _finding("1.4.3", "https://a/", "pass", selector="p"),
            _finding("1.4.3", "https://a/", "fail", selector="p"),
        ]
    )
    assert n == {"1.4.3\thttps://a/\tselector=p": "fail"}


def test_normalise_ignores_message_text(fd):
    a = _finding("1.1.1", "https://a/", "fail", selector="img")
    b = {**a, "message": "totally different wording", "reason": "x"}
    assert fd.normalise([a]) == fd.normalise([b])


def test_diff_reports_identical_and_differs(fd, tmp_path, capsys):
    golden = tmp_path / "golden"
    cand = tmp_path / "cand"
    golden.mkdir()
    cand.mkdir()
    base = fd.normalise([_finding("1.1.1", "https://a/", "fail", selector="img")])
    (golden / "site.json").write_text(json.dumps({"normalised": base}))
    (cand / "site.json").write_text(json.dumps({"normalised": base}))

    rc = fd.main(["diff", str(golden), str(cand)])
    assert rc == 0
    assert "identical" in capsys.readouterr().out

    changed = {**base, next(iter(base)): "pass"}
    (cand / "site.json").write_text(json.dumps({"normalised": changed}))
    rc = fd.main(["diff", str(golden), str(cand), "-v"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "DIFFERS" in out
    assert "fail → pass" in out


def test_report_findings_reads_the_real_report_shape(fd):
    """combined/report.py emits violations / needs_review / passes lists (no
    flat ``findings`` key). The capture step must see all three."""
    report = {
        "result": {
            "violations": [_finding("1.4.11", "https://a/", "fail", selector="button")],
            "needs_review": [_finding("1.1.1", "https://a/", "needs_review", selector="img")],
            "passes": [_finding("1.2.1", "https://a/", "pass", ref_id="m1")],
            "pages_scanned": [{"page_url": "https://a/", "status": "success"}],
        }
    }
    fs = fd._report_findings(report)
    assert {f["wcag_sc"] for f in fs} == {"1.4.11", "1.1.1", "1.2.1"}
    assert fd._report_pages(report) == [{"page_url": "https://a/", "status": "success"}]
    # flat shape still accepted
    assert fd._report_findings({"findings": [_finding("1.1.1", "https://a/", "pass")]})
