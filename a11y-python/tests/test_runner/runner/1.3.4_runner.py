"""
tests/test_runner/runner/1.3.4_runner.py
========================================
Standalone accuracy runner for WCAG 1.3.4 ground-truth cases.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

# ── project imports ──────────────────────────────────────────────────────────
from a11y.accessibility.rendered.evaluators import orientation
from a11y.accessibility.rendered.models import PageSnapshot, ElementSnapshot

# ── paths ────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_GT_DIR = _HERE.parent / "ground_truths"
_GROUND_TRUTH = _GT_DIR / "ground_truth_1_3_4.json"
_REPORT_DIR = _HERE.parent / "reports" / "1.3.4_report"


def _build_snapshot(data: Dict[str, Any]) -> PageSnapshot:
    elements = [ElementSnapshot(**e) for e in data.get("elements", [])]
    return PageSnapshot(**{**data, "elements": elements})


def run_single(case: Dict[str, Any]) -> Dict[str, Any]:
    portrait = _build_snapshot(case["portrait"])
    landscape = _build_snapshot(case["landscape"])
    
    records = orientation.evaluate(portrait, landscape)
    
    # Orientation evaluate returns a list of RuleAuditRecord.
    # We take the "worst" status or PASSED if only PASSED records exist.
    status_priority = {"FAILED": 0, "NEEDS_REVIEW": 1, "PASSED": 2, "N/A": 3}
    actual_status = "PASSED"
    for r in records:
        if status_priority.get(r.status, 3) < status_priority.get(actual_status, 3):
            actual_status = r.status
            
    expected = case["expected"]["status"]
    
    return {
        "id": case["id"],
        "description": case["description"],
        "expected_status": expected,
        "actual_status": actual_status,
        "match": actual_status == expected,
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

    print(f"\nTest Runner — WCAG 1.3.4 Ground Truth")
    print("═" * 80)
    print(f"{'ID':<15} {'Match':<6} {'Actual':<15} {'Expected':<15}")
    print("─" * 80)
    for r in results:
        mark = "✓" if r["match"] else "✗"
        print(f"{r['id']:<15} {mark:<6} {r['actual_status']:<15} {r['expected_status']:<15}")
    print("─" * 80)
    print(f"Accuracy: {correct}/{total} ({accuracy:.1f}%)")

    # Save report
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = _REPORT_DIR / "1.3.4_runner_report.json"
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
