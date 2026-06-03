"""
tests/test_runner/runner/1.3.1_runner.py
========================================
Standalone accuracy runner for WCAG 1.3.1 ground-truth cases.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── project imports ──────────────────────────────────────────────────────────
from a11y.accessibility.pipeline.decisions.policies.policy_1_3_1 import Policy131
from a11y.accessibility.pipeline.models import (
    ElementContext, SemanticContext, VisualContext,
    InteractionContext, BoundingBox, AccessibleName, AccessibleNameSource,
)

# ── paths ────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_GT_DIR = _HERE.parent / "ground_truths"
_GROUND_TRUTH = _GT_DIR / "ground_truth_1_3_1.json"
_REPORT_DIR = _HERE.parent / "reports" / "1.3.1_report"


def _build_element_context(case: Dict[str, Any]) -> ElementContext:
    dom = case["dom_attributes"]
    sem = case.get("semantics", {})
    vis = case.get("visual", {})
    
    # Accessible name
    acc_name = None
    if dom.get("aria_label"):
        acc_name = AccessibleName(
            name=dom["aria_label"],
            source=AccessibleNameSource.ARIA_LABEL,
            is_visible=False,
        )
    elif sem.get("accessible_name"):
        acc_name = AccessibleName(
            name=sem["accessible_name"],
            source=AccessibleNameSource.TEXT_CONTENT,
            is_visible=True,
        )

    # VisualContext
    visual = VisualContext(
        is_visible=True,
        bounding_box=BoundingBox(x=0, y=0, width=100, height=30),
        computed_styles=vis.get("computed_styles", {}),
        resolved_background_color="rgb(255, 255, 255)",
        visible_label_text=vis.get("visible_label_text"),
    )

    # SemanticContext
    semantics = SemanticContext(
        tag_name=sem.get("tag_name") or dom.get("tag_name", "div"),
        role=dom.get("role"),
        is_in_data_table=sem.get("is_in_data_table", False),
        section_type=sem.get("section_type", "generic"),
        described_by_text=sem.get("described_by_text"),
        controls_elements=sem.get("controls_elements") or [],
        owns_elements=sem.get("owns_elements") or [],
        ancestor_roles=sem.get("ancestor_roles", []),
    )

    # InteractionContext
    interaction = InteractionContext(
        is_focusable=False,
        tab_index=-1,
    )

    return ElementContext(
        element_id=case["id"],
        html_snippet="",
        semantics=semantics,
        visual=visual,
        interaction=interaction,
        accessible_name=acc_name,
    )


def run_single(case: Dict[str, Any]) -> Dict[str, Any]:
    element = _build_element_context(case)
    verdict = Policy131().evaluate(element)
    
    expected = case["expected"]["wcag_1_3_1_status"]
    actual = verdict.status.value if hasattr(verdict.status, "value") else str(verdict.status)
    
    return {
        "id": case["id"],
        "description": case["description"],
        "expected_status": expected,
        "actual_status": actual,
        "match": actual == expected,
        "reason_code": verdict.reason_code,
        "expected_reason_code": case["expected"].get("reason_code"),
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

    print(f"\nTest Runner — WCAG 1.3.1 Ground Truth")
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
    report_path = _REPORT_DIR / "1.3.1_runner_report.json"
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
