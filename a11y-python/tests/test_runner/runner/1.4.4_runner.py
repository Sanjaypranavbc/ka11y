"""
tests/test_runner/runner/1.4.4_runner.py
========================================
Standalone accuracy runner for WCAG 1.4.4 ground-truth cases.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

# ── project imports ──────────────────────────────────────────────────────────
from a11y.accessibility.rendered.evaluators import resize_text
from a11y.accessibility.rendered.models import PageSnapshot, ElementSnapshot, Rect

# ── paths ────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_GT_DIR = _HERE.parent / "ground_truths"
_GROUND_TRUTH = _GT_DIR / "ground_truth_1_4_4.json"
_REPORT_DIR = _HERE.parent / "reports" / "1.4.4_report"


def _build_rect(rect_dict: Dict[str, Any]) -> Rect:
    return Rect(
        x=rect_dict["x"],
        y=rect_dict["y"],
        width=rect_dict["width"],
        height=rect_dict["height"],
        top=rect_dict.get("top", rect_dict["y"]),
        right=rect_dict.get("right", rect_dict["x"] + rect_dict["width"]),
        bottom=rect_dict.get("bottom", rect_dict["y"] + rect_dict["height"]),
        left=rect_dict.get("left", rect_dict["x"]),
    )


def _build_snapshot(snap_dict: Dict[str, Any], scenario: str = "default") -> PageSnapshot:
    elements = []
    for el_dict in snap_dict.get("elements", []):
        elements.append(
            ElementSnapshot(
                tag=el_dict["tag"],
                element_id=el_dict.get("element_id"),
                text=el_dict.get("text", ""),
                html_snippet=el_dict.get("html_snippet", ""),
                rect=_build_rect(el_dict["rect"]),
                visible=el_dict.get("visible", True),
                text_clipped=el_dict.get("text_clipped", False),
                scroll_width=el_dict.get("scroll_width", el_dict["rect"]["width"]),
                client_width=el_dict.get("client_width", el_dict["rect"]["width"]),
                overflow_x=el_dict.get("overflow_x", "visible"),
                overflow_y=el_dict.get("overflow_y", "visible"),
            )
        )
    
    return PageSnapshot(
        scenario=scenario,
        page_url="https://www.kao.com/global/en/",
        viewport_width=snap_dict.get("viewport_width", 1280),
        viewport_height=snap_dict.get("viewport_height", 720),
        has_horizontal_scroll=snap_dict.get("has_horizontal_scroll", False),
        document_scroll_width=snap_dict.get("document_scroll_width", 1280),
        elements=elements,
    )


def run_single(case: Dict[str, Any]) -> Dict[str, Any]:
    baseline = _build_snapshot(case["baseline"], scenario="baseline")
    resized = _build_snapshot(case["resized"], scenario="resized")
    
    records = resize_text.evaluate(baseline, resized)
    
    expected_status = case["expected"]["status"]
    
    # ResizeTextEvaluator returns a list of records. 
    # If empty, it's PASSED.
    if not records:
        actual_status = "PASSED"
    else:
        # Check if any record is FAILED
        if any(r.status == "FAILED" for r in records):
            actual_status = "FAILED"
        else:
            actual_status = "PASSED"

    return {
        "id": case["id"],
        "description": case["description"],
        "expected_status": expected_status,
        "actual_status": actual_status,
        "match": actual_status == expected_status,
        "violations": [r.violation for r in records if r.status == "FAILED"],
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

    print(f"\nTest Runner — WCAG 1.4.4 Ground Truth")
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
    report_path = _REPORT_DIR / "1.4.4_runner_report.json"
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
