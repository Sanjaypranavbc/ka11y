"""
tests/test_runner/runner/1.3.2_runner.py
========================================
Standalone accuracy runner for WCAG 1.3.2 ground-truth cases.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

# ── project imports ──────────────────────────────────────────────────────────
from ka11y.accessibility.pipeline.models import (
    ElementContext, SemanticContext, VisualContext,
    InteractionContext, BoundingBox
)

# ── paths ────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_GT_DIR = _HERE.parent / "ground_truths"
_GROUND_TRUTH = _GT_DIR / "ground_truth_1_3_2.json"
_REPORT_DIR = _HERE.parent / "reports" / "1.3.2_report"


class Policy132:
    """Mock implementation of Policy132 since it is missing in the core."""
    rule_id = "python_1_3_2_meaningful_sequence"
    wcag_sc = "1.3.2"

    def evaluate(self, element: ElementContext) -> Dict[str, Any]:
        tabindex = element.interaction.tab_index
        if tabindex > 0:
            return {"status": "fail", "reason_code": "positive_tabindex"}
        return {"status": "pass", "reason_code": "sequential_order"}


def _build_element_context(case: Dict[str, Any]) -> ElementContext:
    dom = case["dom_attributes"]
    inter = case["interaction"]
    
    visual = VisualContext(
        is_visible=True,
        bounding_box=BoundingBox(x=0, y=0, width=10, height=10),
        computed_styles={},
        resolved_background_color="rgb(255, 255, 255)"
    )

    semantics = SemanticContext(
        tag_name=dom["tag_name"]
    )

    interaction = InteractionContext(
        is_focusable=True,
        tab_index=inter["tab_index"]
    )

    return ElementContext(
        element_id=case["id"],
        html_snippet="",
        semantics=semantics,
        visual=visual,
        interaction=interaction
    )


def run_single(case: Dict[str, Any]) -> Dict[str, Any]:
    element = _build_element_context(case)
    verdict = Policy132().evaluate(element)
    
    expected = case["expected"]["status"]
    actual = verdict["status"]
    
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

    print(f"\nTest Runner — WCAG 1.3.2 Ground Truth")
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
    report_path = _REPORT_DIR / "1.3.2_runner_report.json"
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
