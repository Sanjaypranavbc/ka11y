"""
tests/test_runner/runner/contrast_runner.py
============================================
Standalone accuracy runner for WCAG 1.4.3 | 1.4.6 | 1.4.11 ground-truth cases.

Usage:
    python -m tests.test_runner.runner.contrast_runner
    python -m tests.test_runner.runner.contrast_runner --threshold 90
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── project imports ───────────────────────────────────────────────────────────
from ka11y.accessibility.pipeline.runners.contrast_engine import ContrastEngine
from ka11y.accessibility.pipeline.config.thresholds import (
    CONTRAST_NORMAL_AA,
    CONTRAST_LARGE_AA,
    CONTRAST_NORMAL_AAA,
    CONTRAST_LARGE_AAA,
)

# ── paths ─────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_GT_DIR = _HERE.parent / "ground_truths"
_GROUND_TRUTH = _GT_DIR / "ground_truth_contrast.json"

# ── WCAG large-text thresholds (px, as used by ContrastEngine) ────────────────
# 1.4.3 / 1.4.6 large text = ≥24 px regular  OR  ≥18.5 px bold (≈14pt bold)
_LARGE_TEXT_PX = 24.0
_LARGE_TEXT_BOLD_PX = 18.5

# ── transparent colour sentinel ───────────────────────────────────────────────
_TRANSPARENT = {"rgba(0, 0, 0, 0)", "rgba(0,0,0,0)", "transparent"}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _parse_font_size(font_size_str: Optional[str]) -> float:
    """Return font size in px (float).  Falls back to 16.0 on any parse error."""
    if not font_size_str:
        return 16.0
    try:
        return float(font_size_str.replace("px", "").strip())
    except ValueError:
        return 16.0


def _is_bold(font_weight: Optional[str]) -> bool:
    if not font_weight:
        return False
    fw = font_weight.strip()
    return fw == "bold" or (fw.isdigit() and int(fw) >= 700)


def _is_large_text(font_size_px: float, bold: bool) -> bool:
    return font_size_px >= _LARGE_TEXT_PX or (bold and font_size_px >= _LARGE_TEXT_BOLD_PX)


def _is_transparent(color: Optional[str]) -> bool:
    if not color:
        return True
    return color.strip() in _TRANSPARENT


# ─────────────────────────────────────────────────────────────────────────────
# 1.4.3 audit  (WCAG AA normal text contrast)
# ─────────────────────────────────────────────────────────────────────────────

_EXEMPT_CV = {"logo", "decorative"}


def _audit_1_4_3(case: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluate a single ground-truth element for WCAG 1.4.3.

    Returns a result dict with:
        id, rule, description, expected_status, actual_status, match,
        actual_ratio, expected_ratio, reason
    """
    dom = case["dom_attributes"]
    visual = case["visual_attributes"]
    expected = case["expected"]

    expected_status = expected["wcag_1_4_3_status"]  # "pass" | "fail"

    # 1. Exemptions (logo, decorative, disabled)
    cv = (dom.get("cv_classification") or "").lower()
    is_disabled = dom.get("is_disabled", False)

    if cv in _EXEMPT_CV:
        actual_status = "pass"
        reason = f"contrast_exempt — cv_classification='{cv}'"
        ratio = ContrastEngine.calculate_ratio(visual["fg_color"], visual["bg_color"])
        return _result(case, expected_status, actual_status, ratio, reason)

    if is_disabled:
        actual_status = "pass"
        reason = "contrast_exempt — disabled element"
        ratio = ContrastEngine.calculate_ratio(visual["fg_color"], visual["bg_color"])
        return _result(case, expected_status, actual_status, ratio, reason)

    # 2. OCR text-over-image path
    ocr = case.get("ocr_result")
    if visual.get("has_bg_image") and ocr and ocr.get("has_text"):
        fg = visual["fg_color"]
        bg = visual["bg_color"]
        ratio = ContrastEngine.calculate_ratio(fg, bg)
        font_size = _parse_font_size(visual.get("font_size"))
        bold = _is_bold(visual.get("font_weight"))
        large = _is_large_text(font_size, bold)
        threshold = CONTRAST_LARGE_AA if large else CONTRAST_NORMAL_AA
        actual_status = "pass" if ratio >= threshold else "fail"
        reason = f"OCR path — ratio={ratio:.2f}, threshold={threshold}"
        return _result(case, expected_status, actual_status, ratio, reason)

    # 3. Normal AA evaluation
    fg = visual["fg_color"]
    bg = visual["bg_color"]
    ratio = ContrastEngine.calculate_ratio(fg, bg)
    font_size = _parse_font_size(visual.get("font_size"))
    bold = _is_bold(visual.get("font_weight"))
    large = _is_large_text(font_size, bold)
    threshold = CONTRAST_LARGE_AA if large else CONTRAST_NORMAL_AA
    actual_status = "pass" if ratio >= threshold else "fail"
    reason = (
        f"{'large' if large else 'normal'} text — "
        f"ratio={ratio:.2f}, threshold={threshold}"
    )
    return _result(case, expected_status, actual_status, ratio, reason)


# ─────────────────────────────────────────────────────────────────────────────
# 1.4.6 audit  (WCAG AAA enhanced contrast)
# ─────────────────────────────────────────────────────────────────────────────


def _audit_1_4_6(case: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate a single ground-truth element for WCAG 1.4.6 (AAA)."""
    dom = case["dom_attributes"]
    visual = case["visual_attributes"]
    expected = case["expected"]

    expected_status = expected["wcag_1_4_6_status"]

    cv = (dom.get("cv_classification") or "").lower()
    is_disabled = dom.get("is_disabled", False)

    # 1. Exemptions
    if cv in _EXEMPT_CV:
        actual_status = "pass"
        reason = f"contrast_exempt — cv_classification='{cv}'"
        ratio = ContrastEngine.calculate_ratio(visual["fg_color"], visual["bg_color"])
        return _result(case, expected_status, actual_status, ratio, reason)

    if is_disabled:
        actual_status = "pass"
        reason = "contrast_exempt — disabled element"
        ratio = ContrastEngine.calculate_ratio(visual["fg_color"], visual["bg_color"])
        return _result(case, expected_status, actual_status, ratio, reason)

    # 2. OCR path
    ocr = case.get("ocr_result")
    if visual.get("has_bg_image") and ocr and ocr.get("has_text"):
        fg = visual["fg_color"]
        bg = visual["bg_color"]
        ratio = ContrastEngine.calculate_ratio(fg, bg)
        font_size = _parse_font_size(visual.get("font_size"))
        bold = _is_bold(visual.get("font_weight"))
        large = _is_large_text(font_size, bold)
        threshold = CONTRAST_LARGE_AAA if large else CONTRAST_NORMAL_AAA
        actual_status = "pass" if ratio >= threshold else "fail"
        reason = f"OCR path (AAA) — ratio={ratio:.2f}, threshold={threshold}"
        return _result(case, expected_status, actual_status, ratio, reason)

    # 3. AAA evaluation
    fg = visual["fg_color"]
    bg = visual["bg_color"]
    ratio = ContrastEngine.calculate_ratio(fg, bg)
    font_size = _parse_font_size(visual.get("font_size"))
    bold = _is_bold(visual.get("font_weight"))
    large = _is_large_text(font_size, bold)
    threshold = CONTRAST_LARGE_AAA if large else CONTRAST_NORMAL_AAA
    actual_status = "pass" if ratio >= threshold else "fail"
    reason = (
        f"AAA {'large' if large else 'normal'} text — "
        f"ratio={ratio:.2f}, threshold={threshold}"
    )
    return _result(case, expected_status, actual_status, ratio, reason)


# ─────────────────────────────────────────────────────────────────────────────
# 1.4.11 audit  (Non-text contrast)
# ─────────────────────────────────────────────────────────────────────────────

_UI_TAGS = {"button", "input", "select", "textarea"}
_ICON_CV = {"icon"}

# 1.4.11 threshold: 3:1 for UI component boundaries / graphical objects
_NON_TEXT_THRESHOLD = 3.0


def _is_transparent_color(color: Optional[str]) -> bool:
    if not color:
        return True
    c = color.strip().lower().replace(" ", "")
    return c in {"rgba(0,0,0,0)", "transparent"}


def _audit_1_4_11(case: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluate a single ground-truth element for WCAG 1.4.11.

    Decision tree (matches ContrastEngine / ground-truth expectations):
      1. not_ui_component  →  not_applicable
      2. disabled          →  pass (inactive_exempt)
      3. no explicit boundary (both bg + border transparent)  →  needs_review (no_explicit_boundary)
      4. has explicit boundary  →  needs_review (boundary_contrast_review)
         (static analysis cannot compute actual contrast without a screenshot)
    """
    dom = case["dom_attributes"]
    expected = case["expected"]
    expected_status = expected["wcag_1_4_11_status"]

    tag = (dom.get("tag_name") or "").lower()
    cv = (dom.get("cv_classification") or "").lower()
    is_disabled = dom.get("is_disabled", False)
    interaction = case.get("interaction", {})
    is_focusable = interaction.get("is_focusable", False)
    computed = case.get("computed_styles", {})

    bg_color = computed.get("background-color", "rgba(0, 0, 0, 0)")
    border_color = computed.get("border-top-color", "rgba(0, 0, 0, 0)")

    # 1. Is it a UI component?
    is_native_ui = tag in _UI_TAGS
    is_icon = cv in _ICON_CV
    is_interactive = is_focusable

    if not (is_native_ui or is_icon or is_interactive):
        actual_status = "not_applicable"
        reason = "not_ui_component — not interactive, not a native UI tag, not an icon"
        return _result(case, expected_status, actual_status, None, reason)

    # 2. Disabled → inactive_exempt
    if is_disabled:
        actual_status = "pass"
        reason = "inactive_exempt — disabled component"
        return _result(case, expected_status, actual_status, None, reason)

    # 3. Check whether there is an explicit boundary
    has_bg = not _is_transparent_color(bg_color)
    has_border = not _is_transparent_color(border_color)

    if not has_bg and not has_border:
        actual_status = "needs_review"
        reason = "no_explicit_boundary — both background and border are transparent"
        return _result(case, expected_status, actual_status, None, reason)

    # 4. Has explicit boundary — needs visual engine for full evaluation
    actual_status = "needs_review"
    reason = "boundary_contrast_review — explicit boundary found; screenshot analysis required"
    return _result(case, expected_status, actual_status, None, reason)


# ─────────────────────────────────────────────────────────────────────────────
# Shared result builder
# ─────────────────────────────────────────────────────────────────────────────


def _result(
    case: Dict[str, Any],
    expected_status: str,
    actual_status: str,
    ratio: Optional[float],
    reason: str,
) -> Dict[str, Any]:
    return {
        "id": case["id"],
        "rule": case["rule"],
        "description": case["description"],
        "expected_status": expected_status,
        "actual_status": actual_status,
        "match": actual_status == expected_status,
        "actual_ratio": round(ratio, 2) if ratio is not None else None,
        "reason": reason,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Load / run
# ─────────────────────────────────────────────────────────────────────────────

_AUDITORS = {
    "1.4.3": _audit_1_4_3,
    "1.4.6": _audit_1_4_6,
    "1.4.11": _audit_1_4_11,
}


def load_cases(path: Path = _GROUND_TRUTH) -> List[Dict[str, Any]]:
    """Load all ground-truth cases from the JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["cases"]


def run_single(case: Dict[str, Any]) -> Dict[str, Any]:
    """Route a case to the correct rule auditor and return a result dict."""
    rule = case.get("rule", "")
    auditor = _AUDITORS.get(rule)
    if auditor is None:
        return _result(
            case=case,
            expected_status="unknown",
            actual_status="error",
            ratio=None,
            reason=f"No auditor registered for rule '{rule}'",
        )
    return auditor(case)


def run_all(cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Run every case and return results."""
    return [run_single(c) for c in cases]


# ─────────────────────────────────────────────────────────────────────────────
# Report
# ─────────────────────────────────────────────────────────────────────────────


def print_report(results: List[Dict[str, Any]]) -> float:
    """Print a formatted accuracy report and return overall accuracy %."""
    total = len(results)
    correct = sum(1 for r in results if r["match"])
    accuracy = (correct / total * 100) if total else 0.0

    # Per-rule breakdown
    rules_seen: Dict[str, Tuple[int, int]] = {}
    for r in results:
        rule = r["rule"]
        cur = rules_seen.get(rule, (0, 0))
        rules_seen[rule] = (cur[0] + 1, cur[1] + (1 if r["match"] else 0))

    print()
    print("Test Runner — WCAG 1.4.3 | 1.4.6 | 1.4.11 Ground Truth (kao.com)")
    print("═" * 100)
    print(f" {'#':>3}  {'Rule':<8}  {'Match':6}  {'ID':<16}  {'Actual':<14}  {'Expected':<14}")
    print("─" * 100)

    for i, r in enumerate(results, 1):
        mark = "✓" if r["match"] else "✗"
        print(
            f" {i:>3}  {r['rule']:<8}  {mark:<6}  {r['id']:<16}  "
            f"{r['actual_status']:<14}  {r['expected_status']:<14}"
        )

    print("─" * 100)
    print(f" Overall accuracy: {correct}/{total} ({accuracy:.1f}%)")
    print()

    # Per-rule summary
    print(" Per-rule breakdown:")
    for rule, (n, ok) in sorted(rules_seen.items()):
        pct = ok / n * 100 if n else 0
        print(f"   {rule}:  {ok}/{n}  ({pct:.1f}%)")
    print()

    # Mismatch detail
    mismatches = [r for r in results if not r["match"]]
    if mismatches:
        print(f" {len(mismatches)} MISMATCH(ES):")
        print()
        for r in mismatches:
            print(f"   [{r['rule']}] {r['id']}")
            print(f"     Description : {r['description']}")
            print(f"     Actual      : {r['actual_status']}")
            print(f"     Expected    : {r['expected_status']}")
            ratio_str = f"{r['actual_ratio']:.2f}" if r["actual_ratio"] is not None else "n/a"
            print(f"     Ratio       : {ratio_str}")
            print(f"     Reason      : {r['reason']}")
            print()

    return accuracy


# ─────────────────────────────────────────────────────────────────────────────
# Audit report builder
# ─────────────────────────────────────────────────────────────────────────────


def build_audit_report(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build a structured audit_report dict matching the runner_report.json schema.

    Structure:
        {
          "accuracy": <float>,
          "per_rule": { "1.4.3": {...}, "1.4.6": {...}, "1.4.11": {...} },
          "results": [ <result_dict>, ... ]
        }
    """
    total = len(results)
    correct = sum(1 for r in results if r["match"])
    accuracy = (correct / total * 100) if total else 0.0

    per_rule: Dict[str, Any] = {}
    for r in results:
        rule = r["rule"]
        if rule not in per_rule:
            per_rule[rule] = {"total": 0, "correct": 0, "accuracy": 0.0}
        per_rule[rule]["total"] += 1
        if r["match"]:
            per_rule[rule]["correct"] += 1

    for rule, stats in per_rule.items():
        n, ok = stats["total"], stats["correct"]
        stats["accuracy"] = round(ok / n * 100, 1) if n else 0.0

    return {
        "accuracy": round(accuracy, 1),
        "per_rule": per_rule,
        "results": results,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    threshold = 100.0

    # Simple --threshold flag support (no argparse dependency)
    args = sys.argv[1:]
    if "--threshold" in args:
        idx = args.index("--threshold")
        try:
            threshold = float(args[idx + 1])
        except (IndexError, ValueError):
            print("Warning: invalid --threshold value; using 100.0", file=sys.stderr)

    cases = load_cases(_GROUND_TRUTH)
    results = run_all(cases)
    accuracy = print_report(results)

    # Persist report
    report_path = _HERE / "contrast_runner_report.json"
    report_data = build_audit_report(results)
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report_data, fh, indent=2)
    print(f"Report saved to {report_path}")

    if accuracy < threshold:
        print(f" ❌  FAILED — accuracy {accuracy:.1f}% < threshold {threshold}%")
        sys.exit(1)
    else:
        print(f" ✅  PASSED — accuracy {accuracy:.1f}% >= threshold {threshold}%")
        sys.exit(0)


if __name__ == "__main__":
    main()
