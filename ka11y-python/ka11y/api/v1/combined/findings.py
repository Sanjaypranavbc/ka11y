"""
ka11y/api/v1/combined/findings.py
===================================
Finding factory, image classification helper, contrast report builder,
and all per-auditor finding converters.

HOW TO ADD A NEW CONVERTER
───────────────────────────
1. Add a function _myrule_to_findings(records, page_url) → List[Dict]
2. Use _make_finding() with the appropriate wcag_sc / rule_id / severity.
3. Import the function in stages.py and call it after the auditor.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ka11y.config.logger import setup_logger

from .constants import _PYTHON_SEVERITY, _SUGGESTED_FIX, _WCAG_LEVEL, _WCAG_NAMES

logger = setup_logger(name="KAC", tag="combined")


# ── Finding factory ───────────────────────────────────────────────────────────


def _make_finding(
    *,
    source: str,
    rule_id: str,
    wcag_sc: str,
    status: str,
    reason: str,
    severity: Optional[str],
    element_html: str = "",
    element_id: Optional[str] = None,
    element_tag: Optional[str] = None,
    page_url: str = "",
) -> Dict[str, Any]:
    is_pass = status == "pass"
    return {
        "source": source,
        "rule_id": rule_id,
        "wcag_sc": wcag_sc,
        "criterion_name": _WCAG_NAMES.get(wcag_sc),
        "level": _WCAG_LEVEL.get(wcag_sc),
        "severity": None if is_pass else severity,
        "status": status,
        "reason": reason,
        "suggested_fix": None if is_pass else _SUGGESTED_FIX.get(wcag_sc),
        "help_url": None,
        "element": (
            None
            if is_pass
            else {
                "html": element_html[:600],
                "element_id": element_id,
                "tag": element_tag,
                "page_url": page_url,
            }
        ),
    }


# ── Image classification inference ────────────────────────────────────────────


def _infer_classification(path: str) -> str:
    """Derive the image classification from its storage path."""
    p = path.replace("\\", "/").lower()
    if "/functional/buttons/" in p:
        return "button"
    if "/functional/icons/" in p:
        return "icon"
    if "/functional/logos/" in p or "/informative/logos/" in p:
        return "logo"
    if "/functional/images/" in p:
        return "image"
    if "/complex/charts/" in p:
        return "chart"
    if "/informative/icons/" in p:
        return "icon"
    if "/informative/" in p:
        return "informative"
    if "/decorative/" in p:
        return "decorative"
    return "other"


# ── Contrast report builder ───────────────────────────────────────────────────


def _build_contrast_report(ocr_results: list) -> Dict[str, Any]:
    """
    Extract contrast data from OCR results into a structured report.

    Returns
    -------
    {
        "summary": { total_regions_analysed, total_violations,
                     images_with_violations, pass_rate_pct },
        "table":   [ flat row per detected text region ],
        "images":  [ per-image nested detail ],
    }
    """
    table_rows: List[Dict[str, Any]] = []
    images_detail: List[Dict[str, Any]] = []
    total_violations = 0
    images_with_violations = 0

    for result in ocr_results:
        if not result.has_text:
            continue

        image_detections: List[Dict[str, Any]] = []
        image_has_violation = False

        for det in result.detections:
            ci = det.contrast_info or {}
            col = det.color_info or {}

            ratio: Optional[float] = None
            aa_n = aaa_n = None

            # Prefer dominant_contrast (same source as wcag_violations) so that
            # the displayed ratio is always in sync with the Pass/Fail verdict.
            # Fall back to the Otsu-segmentation compliance when color_info is absent.
            dom = col.get("dominant_contrast") or {}
            dom_compliance = dom.get("compliance") or {}
            if dom_compliance:
                ratio = dom_compliance.get("contrast_ratio")
                aa_n  = dom_compliance.get("AA_passes")
                aa_l  = dom_compliance.get("AA_large")
                aaa_n = dom_compliance.get("AAA_passes")
                aaa_l = dom_compliance.get("AAA_large")
            else:
                compliance = ci.get("compliance") or {}
                if compliance:
                    ratio = compliance.get("contrast_ratio")
                    aa_n  = compliance.get("AA_passes")
                    aa_l  = compliance.get("AA_large")
                    aaa_n = compliance.get("AAA_passes")
                    aaa_l = compliance.get("AAA_large")

            fg = col.get("foreground") or {}
            bg_pal = col.get("background_palette") or []
            checks = col.get("contrast_checks") or []
            # Use dominant_bg from dominant_contrast when available so that
            # the background hex shown is the one that triggered the violation.
            dom_bg_obj = dom.get("bg_color") or {}
            dominant_bg: Dict[str, Any] = dom_bg_obj if dom_bg_obj else (bg_pal[0] if bg_pal else {})

            table_rows.append(
                {
                    "image": result.filename,
                    "image_path": result.original_path,
                    "text": det.text,
                    "confidence": round(float(det.confidence), 3),
                    "foreground_hex": fg.get("hex"),
                    "foreground_lum": fg.get("luminance"),
                    "background_hex": dominant_bg.get("hex"),
                    "background_lum": dominant_bg.get("luminance"),
                    "contrast_ratio": ratio,
                    "AA_passes": aa_n,
                    "AAA_passes": aaa_n,
                    "violations": list(det.wcag_violations or []),
                }
            )

            if det.wcag_violations:
                total_violations += len(det.wcag_violations)
                image_has_violation = True

            image_detections.append(
                {
                    "text": det.text,
                    "confidence": round(float(det.confidence), 3),
                    "bbox": det.bbox,
                    "foreground": fg or None,
                    "background_palette": bg_pal,
                    "contrast_checks": checks,
                    "wcag_violations": list(det.wcag_violations or []),
                    "ratio": ratio,
                    "AA_passes": aa_n,
                    "AAA_passes": aaa_n
                }
            )

        if image_has_violation:
            images_with_violations += 1

        if image_detections:
            images_detail.append(
                {
                    "filename": result.filename,
                    "path": result.original_path,
                    "classification": _infer_classification(result.original_path),
                    "contrast_violations_count": result.contrast_violations_count,
                    "detections": image_detections,
                }
            )

    total = len(table_rows)
    pass_rate = round((total - total_violations) / total * 100, 1) if total else 0.0

    return {
        "summary": {
            "total_regions_analysed": total,
            "total_violations": total_violations,
            "images_with_violations": images_with_violations,
            "pass_rate_pct": pass_rate,
        },
        "table": table_rows,
        "images": images_detail,
    }


# ── Per-auditor finding converters ────────────────────────────────────────────


def _alt_text_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
    findings = []
    for r in records:
        status_raw = r.get("wcag_1_1_1_status", "")
        if status_raw not in ("FAILED", "PASSED"):
            continue

        reason = r.get("wcag_1_1_1_reason") or ""
        src = r.get("src", "")
        alt = r.get("alt_text", "")
        alt_attr = f' alt="{alt}"' if alt is not None else ""
        element_html = f'<img src="{src}"{alt_attr}>'
        element_id = r.get("src") or r.get("filename") or None

        if status_raw == "FAILED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_1_1_alt",
                    wcag_sc="1.1.1",
                    status="fail",
                    reason=reason or "Image missing adequate alt text.",
                    severity=_PYTHON_SEVERITY["1.1.1"],
                    element_html=element_html,
                    element_id=element_id,
                    element_tag="img",
                    page_url=r.get("url") or page_url,
                )
            )
        else:
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_1_1_alt",
                    wcag_sc="1.1.1",
                    status="pass",
                    reason=reason or "Image has adequate alt text.",
                    severity=None,
                    page_url=r.get("url") or page_url,
                )
            )
    return findings


def _contrast_to_findings(ocr_results: list, page_url: str) -> List[Dict]:
    """
    Convert per-detection contrast data from OCR results into WCAG 1.4.3 findings.

    Decision logic:
      aa_normal is False  → fail  (ratio < 4.5:1)
      aa_normal is True   → pass  (ratio >= 4.5:1)
      aa_normal is None   → skip  (no contrast data available)
    """
    findings: List[Dict] = []

    for result in ocr_results:
        if not result.has_text:
            continue

        for det in result.detections:
            ci = det.contrast_info or {}
            col = det.color_info or {}

            # Use dominant_contrast for ratio/compliance — same source as wcag_violations.
            dom = col.get("dominant_contrast") or {}
            dom_compliance = dom.get("compliance") or {}
            if dom_compliance:
                aa_normal = dom_compliance.get("AA_passes")
                ratio = dom_compliance.get("contrast_ratio")
            else:
                compliance = ci.get("compliance") or {}
                aa_normal = compliance.get("AA_passes")
                ratio = compliance.get("contrast_ratio")

            if aa_normal is None:
                logger.warning(
                    f"[combined] contrast_to_findings: no AA_passes for "
                    f'"{det.text[:40]!r}" in {result.filename} — skipping'
                )
                continue

            fg = col.get("foreground") or {}
            bg_pal = col.get("background_palette") or []
            dom_bg_obj = dom.get("bg_color") or {}
            dominant_bg = dom_bg_obj if dom_bg_obj else (bg_pal[0] if bg_pal else {})

            fg_hex = fg.get("hex") or ci.get("foreground_color") or "?"
            bg_hex = dominant_bg.get("hex") or ci.get("background_color") or "?"
            ratio_str = f"{ratio:.2f}:1" if ratio is not None else "unknown"
            text_snippet = (det.text or "")[:60].replace('"', "'")
            element_html = (
                f'<img-text fg="{fg_hex}" bg="{bg_hex}" '
                f'ratio="{ratio_str}">{text_snippet}</img-text>'
            )
            image_label = f'{result.filename} -- "{text_snippet}"'

            if not aa_normal:
                findings.append(
                    _make_finding(
                        source="python",
                        rule_id="python_1_4_3_contrast",
                        wcag_sc="1.4.3",
                        status="fail",
                        reason=(
                            f'Text in image "{result.filename}" fails WCAG 1.4.3 '
                            f"AA contrast. Ratio {ratio_str} "
                            f"(fg {fg_hex} on bg {bg_hex}). "
                            f"Required minimum: 4.5:1 for normal text."
                        ),
                        severity=_PYTHON_SEVERITY["1.4.3"],
                        element_html=element_html,
                        element_id=None,
                        element_tag="img",
                        page_url=page_url,
                    )
                )
            else:
                findings.append(
                    _make_finding(
                        source="python",
                        rule_id="python_1_4_3_contrast",
                        wcag_sc="1.4.3",
                        status="pass",
                        reason=(
                            f"Text in {image_label} passes WCAG 1.4.3 AA contrast. "
                            f"Ratio {ratio_str} (fg {fg_hex} on bg {bg_hex})."
                        ),
                        severity=None,
                        page_url=page_url,
                    )
                )

    return findings


def _images_of_text_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
    """Convert image-audit records to WCAG 1.4.5 (Images of Text) findings."""
    findings: List[Dict] = []
    sev = _PYTHON_SEVERITY.get("1.4.5")
    for r in records:
        status_raw = r.get("wcag_1_4_5_status", "N/A")
        if status_raw == "N/A":
            continue
        reason = r.get("wcag_1_4_5_reason") or ""
        src = r.get("src", "")
        alt = r.get("alt_text", "")
        alt_attr = f' alt="{alt}"' if alt is not None else ""
        element_html = f'<img src="{src}"{alt_attr}>'
        element_id = r.get("src") or r.get("filename") or None

        if status_raw == "FAILED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_4_5_images_of_text",
                    wcag_sc="1.4.5",
                    status="fail",
                    reason=reason
                    or "Image contains text — replace with real CSS-styled text.",
                    severity=sev,
                    element_html=element_html,
                    element_id=element_id,
                    element_tag="img",
                    page_url=r.get("url") or page_url,
                )
            )
        else:
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_4_5_images_of_text",
                    wcag_sc="1.4.5",
                    status="pass",
                    reason=reason
                    or "Image does not contain text (or logo exception applies).",
                    severity=None,
                    page_url=r.get("url") or page_url,
                )
            )
    return findings


def _non_text_contrast_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
    """Convert image-audit records to WCAG 1.4.11 (Non-text Contrast) findings."""
    findings: List[Dict] = []
    sev = _PYTHON_SEVERITY.get("1.4.11")
    for r in records:
        status_raw = r.get("wcag_1_4_11_status", "N/A")
        if status_raw in ("N/A", "INCOMPLETE"):
            continue
        reason = r.get("wcag_1_4_11_reason") or ""
        src = r.get("src", "")
        alt = r.get("alt_text", "")
        alt_attr = f' alt="{alt}"' if alt is not None else ""
        element_html = f'<img src="{src}"{alt_attr}>'
        element_id = r.get("src") or r.get("filename") or None

        if status_raw == "FAILED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_4_11_non_text_contrast",
                    wcag_sc="1.4.11",
                    status="fail",
                    reason=reason
                    or "UI component contrast ratio is below 3:1 minimum.",
                    severity=sev,
                    element_html=element_html,
                    element_id=element_id,
                    element_tag="img",
                    page_url=r.get("url") or page_url,
                )
            )
        else:
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_4_11_non_text_contrast",
                    wcag_sc="1.4.11",
                    status="pass",
                    reason=reason or "UI component meets 3:1 contrast ratio.",
                    severity=None,
                    page_url=r.get("url") or page_url,
                )
            )
    return findings


def _form_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
    findings = []
    for r in records:
        html = r.get("html_snippet", "")
        tag = r.get("tag", "INPUT")
        eid = r.get("element_id") or r.get("element_name")
        for sc, status_key in [
            ("3.3.1", "wcag_3_3_1_status"),
            ("3.3.2", "wcag_3_3_2_status"),
        ]:
            violation_key = status_key.replace("_status", "_violation")
            status_raw = r.get(status_key, "")
            rule_id = f"python_{sc.replace('.', '_')}"
            if status_raw == "FAILED":
                findings.append(
                    _make_finding(
                        source="python",
                        rule_id=rule_id,
                        wcag_sc=sc,
                        status="fail",
                        reason=r.get(violation_key)
                        or f"Form field violates WCAG {sc}.",
                        severity=_PYTHON_SEVERITY[sc],
                        element_html=html,
                        element_id=eid,
                        element_tag=tag,
                        page_url=page_url,
                    )
                )
            elif status_raw == "PASSED":
                findings.append(
                    _make_finding(
                        source="python",
                        rule_id=rule_id,
                        wcag_sc=sc,
                        status="pass",
                        reason=f"Form field meets WCAG {sc}.",
                        severity=None,
                        page_url=page_url,
                    )
                )
    return findings


def _lin_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
    findings = []
    for r in records:
        status_raw = r.get("wcag_2_5_3_status", "")
        if status_raw == "N/A":
            continue
        if status_raw == "FAILED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_2_5_3_label_in_name",
                    wcag_sc="2.5.3",
                    status="fail",
                    reason=r.get("wcag_2_5_3_violation")
                    or "Accessible name does not contain visible label.",
                    severity=_PYTHON_SEVERITY["2.5.3"],
                    element_html=r.get("html_snippet", ""),
                    element_id=r.get("element_id"),
                    element_tag=r.get("tag", ""),
                    page_url=page_url,
                )
            )
        elif status_raw == "PASSED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_2_5_3_label_in_name",
                    wcag_sc="2.5.3",
                    status="pass",
                    reason="Accessible name contains the visible label.",
                    severity=None,
                    page_url=page_url,
                )
            )
    return findings


def _psh_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
    findings = []
    for r in records:
        status_raw = r.get("wcag_2_2_2_status", "")
        if status_raw == "FAILED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_2_2_2_pause_stop_hide",
                    wcag_sc="2.2.2",
                    status="fail",
                    reason=r.get("wcag_2_2_2_violation")
                    or "Auto-playing content has no pause/stop mechanism.",
                    severity=_PYTHON_SEVERITY["2.2.2"],
                    element_html=r.get("html_snippet", ""),
                    element_id=r.get("element_id"),
                    element_tag=r.get("tag", ""),
                    page_url=page_url,
                )
            )
        elif status_raw == "PASSED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_2_2_2_pause_stop_hide",
                    wcag_sc="2.2.2",
                    status="pass",
                    reason="Moving content has a pause/stop mechanism or exception applies.",
                    severity=None,
                    page_url=page_url,
                )
            )
    return findings


def _ts_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
    findings = []
    for r in records:
        status_raw = r.get("wcag_2_5_8_status", "")
        if status_raw == "N/A":
            continue
        w = r.get("rendered_width_px", 0)
        h = r.get("rendered_height_px", 0)
        if status_raw == "FAILED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_2_5_8_target_size",
                    wcag_sc="2.5.8",
                    status="fail",
                    reason=r.get("wcag_2_5_8_violation")
                    or f"Target size {w:.0f}×{h:.0f} px is below 24×24 px minimum.",
                    severity=_PYTHON_SEVERITY["2.5.8"],
                    element_html=r.get("html_snippet", ""),
                    element_id=r.get("element_id"),
                    element_tag=r.get("tag", ""),
                    page_url=page_url,
                )
            )
        elif status_raw == "PASSED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_2_5_8_target_size",
                    wcag_sc="2.5.8",
                    status="pass",
                    reason=f"Target size {w:.0f}×{h:.0f} px meets the 24×24 px minimum.",
                    severity=None,
                    page_url=page_url,
                )
            )
    return findings


# ── Rendered-layout finding converters ────────────────────────────────────────


def _rendered_rule_to_findings(
    records: List[Dict],
    page_url: str,
    rule_key: str,
    rule_id: str,
    wcag_sc: str,
    pass_reason: str,
) -> List[Dict]:
    """Generic converter for rendered-layout rule records."""
    findings: List[Dict] = []
    for r in records:
        status_raw = r.get(f"{rule_key}_status", "")
        if status_raw == "N/A":
            continue
        violation = r.get(f"{rule_key}_violation", "")
        sev = _PYTHON_SEVERITY.get(wcag_sc)

        if status_raw == "FAILED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id=rule_id,
                    wcag_sc=wcag_sc,
                    status="fail",
                    reason=violation or f"Page violates WCAG {wcag_sc}.",
                    severity=sev,
                    element_html=r.get("html_snippet", ""),
                    element_id=r.get("element_id"),
                    element_tag=r.get("tag", ""),
                    page_url=r.get("page_url") or page_url,
                )
            )
        elif status_raw == "NEEDS_REVIEW":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id=rule_id,
                    wcag_sc=wcag_sc,
                    status="needs_review",
                    reason=violation or f"WCAG {wcag_sc} requires manual review.",
                    severity=sev,
                    element_html=r.get("html_snippet", ""),
                    element_id=r.get("element_id"),
                    element_tag=r.get("tag", ""),
                    page_url=r.get("page_url") or page_url,
                )
            )
        elif status_raw == "PASSED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id=rule_id,
                    wcag_sc=wcag_sc,
                    status="pass",
                    reason=pass_reason,
                    severity=None,
                    page_url=r.get("page_url") or page_url,
                )
            )
    return findings


def _resize_text_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
    return _rendered_rule_to_findings(
        records,
        page_url,
        rule_key="wcag_1_4_4",
        rule_id="python_1_4_4_resize_text",
        wcag_sc="1.4.4",
        pass_reason="Text reflows correctly at 200% without loss of content.",
    )


def _reflow_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
    return _rendered_rule_to_findings(
        records,
        page_url,
        rule_key="wcag_1_4_10",
        rule_id="python_1_4_10_reflow",
        wcag_sc="1.4.10",
        pass_reason="Content reflows without horizontal scrolling at 320 CSS px.",
    )


def _crawler_text_spacing_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
    """Convert TextSpacingAuditor (static structural analysis) records to findings."""
    findings: List[Dict] = []
    sev = _PYTHON_SEVERITY.get("1.4.12")
    for r in records:
        status_raw = r.get("wcag_1_4_12_status", "")
        if status_raw in ("N/A", "INFO"):
            continue
        violation = r.get("wcag_1_4_12_violation", "")
        if status_raw == "FAILED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_4_12_text_spacing_static",
                    wcag_sc="1.4.12",
                    status="fail",
                    reason=violation or "Element clips text after spacing overrides.",
                    severity=sev,
                    element_html=r.get("html_snippet", ""),
                    element_id=r.get("element_id"),
                    element_tag=r.get("tag", ""),
                    page_url=r.get("page_url") or page_url,
                )
            )
        elif status_raw == "WARNING":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_4_12_text_spacing_static",
                    wcag_sc="1.4.12",
                    status="needs_review",
                    reason=violation
                    or "Fixed height with overflow hidden may clip text when spacing increases.",
                    severity=sev,
                    element_html=r.get("html_snippet", ""),
                    element_id=r.get("element_id"),
                    element_tag=r.get("tag", ""),
                    page_url=r.get("page_url") or page_url,
                )
            )
        elif status_raw == "PASSED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_4_12_text_spacing_static",
                    wcag_sc="1.4.12",
                    status="pass",
                    reason="No fixed-height/overflow-hidden clipping risk detected.",
                    severity=None,
                    page_url=r.get("page_url") or page_url,
                )
            )
    return findings


def _rendered_text_spacing_to_findings(
    records: List[Dict], page_url: str
) -> List[Dict]:
    return _rendered_rule_to_findings(
        records,
        page_url,
        rule_key="wcag_1_4_12",
        rule_id="python_1_4_12_text_spacing_rendered",
        wcag_sc="1.4.12",
        pass_reason="No content or functionality is lost after text spacing overrides.",
    )


def _orientation_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
    return _rendered_rule_to_findings(
        records,
        page_url,
        rule_key="wcag_1_3_4",
        rule_id="python_1_3_4_orientation",
        wcag_sc="1.3.4",
        pass_reason="Content is available in both portrait and landscape orientations.",
    )


def _hover_focus_content_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
    return _rendered_rule_to_findings(
        records,
        page_url,
        rule_key="wcag_1_4_13",
        rule_id="python_1_4_13_hover_or_focus_content",
        wcag_sc="1.4.13",
        pass_reason="Hover/focus-triggered content meets dismissible/hoverable/persistent requirements.",
    )


def _focus_not_obscured_min_to_findings(
    records: List[Dict], page_url: str
) -> List[Dict]:
    return _rendered_rule_to_findings(
        records,
        page_url,
        rule_key="wcag_2_4_11",
        rule_id="python_2_4_11_focus_not_obscured_minimum",
        wcag_sc="2.4.11",
        pass_reason="No focused element is entirely hidden by author-created content.",
    )


def _focus_not_obscured_enh_to_findings(
    records: List[Dict], page_url: str
) -> List[Dict]:
    return _rendered_rule_to_findings(
        records,
        page_url,
        rule_key="wcag_2_4_12",
        rule_id="python_2_4_12_focus_not_obscured_enhanced",
        wcag_sc="2.4.12",
        pass_reason="No focused element is obscured (even partially) by author-created content.",
    )
