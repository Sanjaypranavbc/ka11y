"""
tests/test_runner/runner/1.4.2_runner.py
========================================
Standalone accuracy runner for WCAG 1.4.2 ground-truth cases.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

# ── paths ────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_GT_DIR = _HERE.parent / "ground_truths"
_GROUND_TRUTH = _GT_DIR / "ground_truth_1_4_2.json"
_REPORT_DIR = _HERE.parent / "reports" / "1.4.2_report"


def _evaluate_1_4_2(case: Dict[str, Any]) -> tuple[str, str]:
    """
    Heuristic evaluation of WCAG 1.4.2 Audio Control.
    Logic implemented directly in runner as Policy142 is not available.
    """
    dom = case["dom_attributes"]
    ctx = case.get("context", {})
    
    tag = dom.get("tag_name", "").lower()
    autoplay = dom.get("autoplay", False)
    muted = dom.get("muted", False)
    controls = dom.get("controls", False)
    duration = ctx.get("duration", 0.0)
    
    # 1. No audio
    if not ctx.get("plays_audio", True) and tag not in ("audio", "video"):
        return "pass", "no_audio"

    # 2. Muted media
    if muted:
        return "pass", "muted_media"

    # 3. Not playing automatically
    if not autoplay and not ctx.get("plays_audio", False):
        return "pass", "no_autoplay"

    # 4. Short duration (< 3s)
    if duration <= 3.0:
        return "pass", "short_duration"

    # 5. Has controls (native)
    if controls:
        return "pass", "has_native_controls"

    # 6. Has external control
    if ctx.get("has_external_pause_button"):
        return "pass", "has_external_control"

    # 7. Fail cases
    if tag in ("audio", "video"):
        return "fail", "no_controls"
    
    if ctx.get("plays_audio"):
        return "fail", "hidden_audio_no_control"

    return "pass", "default_pass"


def run_single(case: Dict[str, Any]) -> Dict[str, Any]:
    status, reason = _evaluate_1_4_2(case)
    
    expected = case["expected"]["status"]
    
    return {
        "id": case["id"],
        "description": case["description"],
        "expected_status": expected,
        "actual_status": status,
        "match": status == expected,
        "reason_code": reason,
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

    print(f"\nTest Runner — WCAG 1.4.2 Ground Truth")
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
    report_path = _REPORT_DIR / "1.4.2_runner_report.json"
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
