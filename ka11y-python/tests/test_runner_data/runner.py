"""
tests/test_runner/runner.py
============================
Standalone accuracy runner for WCAG 1.1.1 ground-truth cases.

Usage:
    python -m tests.test_runner.runner
    python -m tests.test_runner.runner --threshold 90
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── project imports ──────────────────────────────────────────────────────────
from ka11y.accessibility.rules.non_text.alttext import AltTextAccessibilityAuditor
from ka11y.crawler.models import ImageData

# ── paths ────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_GROUND_TRUTH = _HERE / "ground_truth_1_1_1.json"


# ── mock OCR result ──────────────────────────────────────────────────────────
class _MockDetection:
    def __init__(self, text: str):
        self.text = text
        self.contrast_info = None


class _MockOCRResult:
    def __init__(
        self,
        filename: str,
        has_text: bool = False,
        texts: Optional[List[str]] = None,
        contrast_violations_count: int = 0,
    ):
        self.filename = filename
        self.has_text = has_text
        self.detections = [_MockDetection(t) for t in (texts or [])]
        self.contrast_violations_count = contrast_violations_count


# ── core logic ───────────────────────────────────────────────────────────────


def _build_image_data(case: Dict[str, Any]) -> ImageData:
    """Reconstruct an ImageData from ground-truth DOM attributes + classifier output."""
    dom = case["dom_attributes"]
    ctx = case["context"]
    clf = case["classifier_output"]

    src = dom.get("src") or "https://example.com/img.png"
    filename = Path(src.split("?")[0]).name or "img.png"

    return ImageData(
        url="https://www.kao.com/global/en/",
        src=src,
        alt_text=dom.get("alt"),      # None = missing; "" = empty
        title=dom.get("title") or "",
        classification=clf["classification"],
        sub_type=clf.get("sub_type"),
        is_functional=clf.get("is_functional", False),
        is_decorative=clf.get("is_decorative", False),
        is_complex=False,
        is_text_image=False,
        is_logo=clf.get("is_logo", False),
        is_icon=clf.get("is_icon", False),
        is_button=clf.get("is_button", False),
        file_format=None,
        screenshot_path=f"/tmp/{filename}",
        filename=filename,
    )


def _build_ocr(case: Dict[str, Any]) -> Optional[_MockOCRResult]:
    """Build a mock OCR result from the ground-truth, or None."""
    ocr = case.get("ocr_result")
    if ocr is None:
        return None

    src = case["dom_attributes"].get("src") or "img.png"
    filename = Path(src.split("?")[0]).name or "img.png"
    return _MockOCRResult(
        filename=filename,
        has_text=ocr.get("has_text", False),
        texts=ocr.get("detected_texts", []),
    )


def run_single(case: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run the auditor on a single ground-truth case.

    Returns a dict with:
      - id, description
      - expected_status, actual_status
      - match (bool)
      - actual_reason
      - dom_alt (for diagnostics)
    """
    img = _build_image_data(case)
    ocr = _build_ocr(case)
    ocr_list = [ocr] if ocr else []

    with tempfile.TemporaryDirectory() as tmp:
        records = AltTextAccessibilityAuditor().generate_audit_report(
            images_data=[img],
            ocr_results=ocr_list,
            output_dir=tmp,
        )

    rec = records[0]
    expected = case["expected"]["wcag_1_1_1_status"]
    actual = rec["wcag_1_1_1_status"]

    return {
        "id": case["id"],
        "description": case["description"],
        "expected_status": expected,
        "actual_status": actual,
        "match": actual == expected,
        "actual_reason": rec.get("wcag_1_1_1_reason", ""),
        "dom_alt": case["dom_attributes"].get("alt"),
        "src": case["dom_attributes"].get("src", ""),
    }


def load_cases(path: Path = _GROUND_TRUTH) -> List[Dict[str, Any]]:
    """Load all ground-truth cases from the JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["cases"]


def run_all(cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Run every case and return results."""
    return [run_single(c) for c in cases]


def print_report(results: List[Dict[str, Any]]) -> float:
    """Print a formatted accuracy report and return accuracy %."""
    total = len(results)
    correct = sum(1 for r in results if r["match"])
    accuracy = (correct / total * 100) if total else 0.0

    print()
    print("Test Runner — WCAG 1.1.1 Ground Truth (kao.com)")
    print("═" * 90)
    print(f" {'#':>3}  {'Match':6}  {'ID':<12}  {'DOM alt':<25}  {'Actual':<8}  {'Expected':<8}")
    print("─" * 90)

    for i, r in enumerate(results, 1):
        alt_display = repr(r["dom_alt"]) if r["dom_alt"] is not None else "[MISSING]"
        if len(alt_display) > 23:
            alt_display = alt_display[:20] + "..."
        mark = "✓" if r["match"] else "✗"
        print(
            f" {i:>3}  {mark:<6}  {r['id']:<12}  {alt_display:<25}  "
            f"{r['actual_status']:<8}  {r['expected_status']:<8}"
        )

    print("─" * 90)
    print(f" Accuracy: {correct}/{total} ({accuracy:.1f}%)")
    print()

    # Detail for mismatches
    mismatches = [r for r in results if not r["match"]]
    if mismatches:
        print(f" {len(mismatches)} MISMATCH(ES):")
        print()
        for r in mismatches:
            src_short = r["src"].split("/")[-1][:40] if r["src"] else "?"
            print(f"   {r['id']}  ({src_short})")
            print(f"     alt       = {repr(r['dom_alt'])}")
            print(f"     Auditor   = {r['actual_status']}  ({r['actual_reason'][:80]})")
            print(f"     Expected  = {r['expected_status']}")
            print()

    return accuracy


def main():
    gt_path = _GROUND_TRUTH
    threshold = 100.0
    cases = load_cases(gt_path)
    results = run_all(cases)
    accuracy = print_report(results)

    report_path = _HERE / "runner_report.json"
    report_data = {
        "accuracy": accuracy,
        "results": results,
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
    print(f"Report saved to {report_path}")

    if accuracy < threshold:
        print(f" ❌  FAILED — accuracy {accuracy:.1f}% < threshold {threshold}%")
        sys.exit(1)
    else:
        print(f" ✅  PASSED — accuracy {accuracy:.1f}% >= threshold {threshold}%")
        sys.exit(0)


if __name__ == "__main__":
    main()
