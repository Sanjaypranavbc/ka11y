"""
tests/test_runner/runner/1.3.5_runner.py
========================================
Standalone accuracy runner for WCAG 1.3.5 ground-truth cases.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

# ── project imports ──────────────────────────────────────────────────────────
from a11y.accessibility.rules.forms.form_auditor import FormAccessibilityAuditor
from a11y.crawler.forms_crawler import FormInputData

# ── paths ────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_GT_DIR = _HERE.parent / "ground_truths"
_GROUND_TRUTH = _GT_DIR / "ground_truth_1_3_5.json"
_REPORT_DIR = _HERE.parent / "reports" / "1.3.5_report"


def _build_form_data(case: Dict[str, Any]) -> FormInputData:
    d = case["data"]
    return FormInputData(
        page_url="https://www.kao.com/global/en/",
        form_index=0,
        tag=d["tag"],
        type=d.get("type"),
        name=d.get("name"),
        autocomplete=d.get("autocomplete"),
        has_any_label=d.get("has_any_label", False),
        html=f'<{d["tag"]} type="{d.get("type","")}" name="{d.get("name","")}" autocomplete="{d.get("autocomplete","")}">'
    )


def run_single(case: Dict[str, Any]) -> Dict[str, Any]:
    f = _build_form_data(case)
    
    auditor = FormAccessibilityAuditor(output_dir=str(_REPORT_DIR))
    records = auditor.generate_audit_report([f])
    
    # 1.3.5 is checked as part of 3.3.2 in FormAccessibilityAuditor
    rec = records[0]
    actual = rec["wcag_1_3_2_status"] if "wcag_1_3_2_status" in rec else rec["wcag_3_3_2_status"]
    
    expected = case["expected"]["status"]
    
    return {
        "id": case["id"],
        "description": case["description"],
        "expected_status": expected,
        "actual_status": actual,
        "match": actual == expected,
    }


def load_cases(path: Path = _GROUND_TRUTH) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["cases"]


def main():
    if not _GROUND_TRUTH.exists():
        print(f"Error: Ground truth file not found at {_GROUND_TRUTH}")
        sys.exit(1)

    cases = load_cases(_GROUND_TRUTH)
    results = [run_single(c) for c in cases]
    
    total = len(results)
    correct = sum(1 for r in results if r["match"])
    accuracy = (correct / total * 100) if total else 0.0

    print(f"\nTest Runner — WCAG 1.3.5 Ground Truth")
    print("═" * 80)
    print(f"{'ID':<15} {'Match':<6} {'Actual':<10} {'Expected':<10}")
    print("─" * 80)
    for r in results:
        mark = "✓" if r["match"] else "✗"
        print(f"{r['id']:<15} {mark:<6} {r['actual_status']:<10} {r['expected_status']:<10}")
    print("─" * 80)
    print(f"Accuracy: {correct}/{total} ({accuracy:.1f}%)")

    # Save report
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = _REPORT_DIR / "1.3.5_runner_report.json"
    report_data = {
        "accuracy": accuracy,
        "results": results,
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
    print(f"\nReport saved to {report_path}")

    if accuracy < 100.0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
