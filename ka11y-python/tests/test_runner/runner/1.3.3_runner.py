"""
tests/test_runner/runner/1.3.3_runner.py
========================================
Standalone accuracy runner for WCAG 1.3.3 ground-truth cases.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

# ── project imports ──────────────────────────────────────────────────────────
from ka11y.accessibility.rules.non_text.sensory_auditor import SensoryCharacteristicsAuditor
from ka11y.crawler.sensory_crawler import SensoryElementData

# ── paths ────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_GT_DIR = _HERE.parent / "ground_truths"
_GROUND_TRUTH = _GT_DIR / "ground_truth_1_3_3.json"
_REPORT_DIR = _HERE.parent / "reports" / "1.3.3_report"


def _build_sensory_data(case: Dict[str, Any]) -> SensoryElementData:
    d = case["data"]
    return SensoryElementData(
        page_url="https://www.kao.com/global/en/",
        tag=d["tag"],
        text=d["text"],
        element_id=case["id"],
        html=f'<{d["tag"]}>{d["text"]}</{d["tag"]}>'
    )


def run_single(case: Dict[str, Any]) -> Dict[str, Any]:
    el = _build_sensory_data(case)
    
    auditor = SensoryCharacteristicsAuditor(output_dir=str(_REPORT_DIR))
    records = auditor.generate_audit_report([el])
    
    # generate_audit_report might return an empty list if no instructional sentences found
    # but for ground truth, we expect it to find them or pass correctly.
    if not records:
        # If no violation found, it means it PASSED in the auditor's view
        actual = "PASSED"
    else:
        # Check if any record for this element failed
        actual = "FAILED" if any(r["wcag_1_3_3_status"] == "FAILED" for r in records) else "PASSED"
    
    expected = case["expected"]["wcag_1_3_3_status"]
    
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

    print(f"\nTest Runner — WCAG 1.3.3 Ground Truth")
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
    report_path = _REPORT_DIR / "1.3.3_runner_report.json"
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
