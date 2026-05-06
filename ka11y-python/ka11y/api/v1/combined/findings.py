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

import contextvars
from typing import Any, Dict, List, Optional

from ka11y.config.logger import setup_logger
from ka11y.i18n.loader import (
    get_level_label,
    get_severity_label,
    get_status_label,
    get_suggested_fixes,
    get_wcag_names,
    render_reason,
)

from .constants import _PYTHON_SEVERITY, _WCAG_LEVEL

# Per-job language context — set in runner._run_job() before creating stage tasks.
# asyncio.create_task() copies the current Context, so child tasks automatically
# inherit the language without it being threaded through every function signature.
_lang_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "combined_lang", default="en"
)

logger = setup_logger(name="KAC", tag="combined")


# ── Finding factory ───────────────────────────────────────────────────────────


def _make_finding(
    *,
    source: str,
    rule_id: str,
    wcag_sc: str,
    status: str,
    severity: Optional[str],
    reason: Optional[str] = None,
    reason_code: Optional[str] = None,
    reason_params: Optional[Dict[str, Any]] = None,
    element_html: str = "",
    element_id: Optional[str] = None,
    element_tag: Optional[str] = None,
    element_target: Optional[List[str]] = None,
    element_selector: Optional[str] = None,
    element_ref_id: Optional[str] = None,
    frame_path: Optional[str] = None,
    image_src: Optional[str] = None,
    image_reference: Optional[str] = None,
    image_text: Optional[str] = None,
    page_url: str = "",
) -> Dict[str, Any]:
    is_pass = status == "pass"
    _lang = _lang_ctx.get()
    wcag_names = get_wcag_names(_lang)
    suggested_fixes = get_suggested_fixes(_lang)

    # Localize reason: prefer reason_code → YAML template, fall back to inline string.
    if reason_code:
        reason_text = render_reason(
            wcag_sc,
            reason_code,
            lang=_lang,
            fallback=reason or "",
            params=reason_params or {},
        )
    else:
        reason_text = reason or ""

    level_value = _WCAG_LEVEL.get(wcag_sc)
    severity_value = None if is_pass else severity
    target = element_target or ([element_selector] if element_selector else None)
    has_element_data = bool(
        (element_html or "").strip()
        or element_id
        or element_tag
        or target
        or element_ref_id
        or frame_path
        or image_src
        or image_reference
    )
    if is_pass:
        element = (
            {
                "html": element_html[:600] if element_html else "",
                "element_id": element_id,
                "tag": element_tag,
                "target": target,
                "selector": element_selector,
                "element_ref_id": element_ref_id,
                "frame_path": frame_path,
                "image_src": image_src,
                "image_reference": image_reference,
                "image_text": image_text,
                "page_url": page_url,
            }
            if has_element_data
            else None
        )
    else:
        element = {
            "html": element_html[:600] if element_html else "",
            "element_id": element_id,
            "tag": element_tag,
            "target": target,
            "selector": element_selector,
            "element_ref_id": element_ref_id,
            "frame_path": frame_path,
            "image_src": image_src,
            "image_reference": image_reference,
            "image_text": image_text,
            "page_url": page_url,
        }

    return {
        "source": source,
        "rule_id": rule_id,
        "wcag_sc": wcag_sc,
        "criterion_name": wcag_names.get(wcag_sc),
        "level": level_value,
        "level_label": get_level_label(level_value, _lang),
        "severity": severity_value,
        "severity_label": get_severity_label(severity_value, _lang),
        "status": status,
        "status_label": get_status_label(status, _lang),
        "reason": reason_text,
        "reason_code": reason_code,
        "suggested_fix": None if is_pass else suggested_fixes.get(wcag_sc),
        "help_url": None,
        "element": element,
    }


def _is_incomplete_reason(reason: str) -> bool:
    """Identify manual-review reasons that should surface as needs_review."""
    return reason.strip().upper().startswith("INCOMPLETE")


def _record_element_kwargs(
    record: Dict[str, Any],
    page_url: str,
    *,
    html_key: str = "html_snippet",
    element_id_keys: tuple[str, ...] = ("element_id",),
    tag_key: str = "tag",
) -> Dict[str, Any]:
    element_id = None
    for key in element_id_keys:
        value = record.get(key)
        if value:
            element_id = value
            break

    selector = record.get("selector")
    return {
        "element_html": record.get(html_key, ""),
        "element_id": element_id,
        "element_tag": record.get(tag_key, ""),
        "element_target": [selector] if selector else None,
        "element_selector": selector,
        "element_ref_id": record.get("element_ref_id"),
        "frame_path": record.get("frame_path"),
        "page_url": record.get("page_url") or page_url,
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
                aa_n = dom_compliance.get("AA_passes")
                aaa_n = dom_compliance.get("AAA_passes")
            else:
                compliance = ci.get("compliance") or {}
                if compliance:
                    ratio = compliance.get("contrast_ratio")
                    aa_n = compliance.get("AA_passes")
                    aaa_n = compliance.get("AAA_passes")

            fg = col.get("foreground") or {}
            bg_pal = col.get("background_palette") or []
            checks = col.get("contrast_checks") or []
            # Use dominant_bg from dominant_contrast when available so that
            # the background hex shown is the one that triggered the violation.
            dom_bg_obj = dom.get("bg_color") or {}
            dominant_bg: Dict[str, Any] = (
                dom_bg_obj if dom_bg_obj else (bg_pal[0] if bg_pal else {})
            )

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
                    "AAA_passes": aaa_n,
                }
            )

        if image_has_violation:
            images_with_violations += 1

        if image_detections:
            # Compute from actual detections — result.contrast_violations_count can be
            # stale or miscounted by the OCR pipeline, causing violations to disappear.
            local_violations_count = sum(
                1 for d in image_detections if d.get("wcag_violations")
            )
            images_detail.append(
                {
                    "filename": result.filename,
                    "path": result.original_path,
                    "classification": _infer_classification(result.original_path),
                    "contrast_violations_count": local_violations_count,
                    "detections": image_detections,
                }
            )

    total = len(table_rows)
    failing_regions = sum(1 for row in table_rows if row.get("violations"))
    pass_rate = round((total - failing_regions) / total * 100, 1) if total else 0.0

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


def _build_image_audit_report(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Surface the full Python image-audit result set in a frontend-friendly shape.

    Unlike contrast_report, this covers all audited images, including ones with
    no OCR text or no contrast data, so the UI can still show that image audit
    ran and what it concluded.
    """
    images: List[Dict[str, Any]] = []
    by_classification: Dict[str, Dict[str, int]] = {}
    passed = 0
    failed = 0
    with_ocr_text = 0
    with_contrast_violations = 0

    for record in records:
        classification = str(record.get("classification") or "other")
        overall_status = str(record.get("overall_status") or "FAILED")
        if overall_status == "PASSED":
            passed += 1
        else:
            failed += 1

        if record.get("has_ocr_text"):
            with_ocr_text += 1
        contrast_violations_count = int(record.get("contrast_violations_count") or 0)
        if contrast_violations_count > 0:
            with_contrast_violations += 1

        bucket = by_classification.setdefault(
            classification,
            {"passed": 0, "failed": 0, "total": 0},
        )
        bucket["total"] += 1
        if overall_status == "PASSED":
            bucket["passed"] += 1
        else:
            bucket["failed"] += 1

        images.append(
            {
                "filename": record.get("filename"),
                "path": record.get("screenshot_path"),
                "src": record.get("src"),
                "url": record.get("url"),
                "alt_text": record.get("alt_text"),
                "title": record.get("title"),
                "classification": classification,
                "sub_type": record.get("sub_type") or None,
                "overall_status": overall_status,
                "has_ocr_text": bool(record.get("has_ocr_text")),
                "detected_text": record.get("detected_text") or "",
                "contrast_violations_count": contrast_violations_count,
                "wcag_1_1_1_status": record.get("wcag_1_1_1_status"),
                "wcag_4_1_2_status": record.get("wcag_4_1_2_status"),
                "wcag_1_4_5_status": record.get("wcag_1_4_5_status"),
                "wcag_1_4_11_status": record.get("wcag_1_4_11_status"),
                "wcag_1_1_1_reason": record.get("wcag_1_1_1_reason") or "",
                "wcag_4_1_2_reason": record.get("wcag_4_1_2_reason") or "",
                "wcag_1_4_5_reason": record.get("wcag_1_4_5_reason") or "",
                "wcag_1_4_11_reason": record.get("wcag_1_4_11_reason") or "",
            }
        )

    return {
        "summary": {
            "total_images": len(records),
            "passed": passed,
            "failed": failed,
            "with_ocr_text": with_ocr_text,
            "with_contrast_violations": with_contrast_violations,
            "by_classification": by_classification,
        },
        "images": images,
    }


# ── Per-auditor finding converters ────────────────────────────────────────────


def _alt_text_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
    findings = []
    for r in records:
        status_raw = r.get("wcag_1_1_1_status", "")
        if status_raw not in ("FAILED", "PASSED", "INCOMPLETE"):
            continue

        reason = r.get("wcag_1_1_1_reason") or ""
        src = r.get("src", "")
        alt = r.get("alt_text", "")
        alt_attr = f' alt="{alt}"' if alt is not None else ""
        element_html = f'<img src="{src}"{alt_attr}>'
        element_id = r.get("src") or r.get("filename") or None

        path = r.get("screenshot_path")
        filename = r.get("filename")
        detected_text = r.get("detected_text")

        if status_raw == "PASSED" and "manual review" in reason.lower():
            status_raw = "INCOMPLETE"

        if status_raw == "INCOMPLETE":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_1_1_alt",
                    wcag_sc="1.1.1",
                    status="needs_review",
                    reason_code="capture_failed",
                    reason=reason or None,
                    severity=_PYTHON_SEVERITY["1.1.1"],
                    element_html=element_html,
                    element_id=element_id,
                    element_tag="img",
                    image_src=path,
                    image_reference=filename,
                    image_text=detected_text,
                    page_url=r.get("url") or page_url,
                )
            )
        elif status_raw == "FAILED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_1_1_alt",
                    wcag_sc="1.1.1",
                    status="fail",
                    reason_code="fail_missing_alt",
                    reason=reason or None,
                    severity=_PYTHON_SEVERITY["1.1.1"],
                    element_html=element_html,
                    element_id=element_id,
                    element_tag="img",
                    image_src=path,
                    image_reference=filename,
                    image_text=detected_text,
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
                    reason_code="pass",
                    reason=reason or None,
                    severity=None,
                    element_html=element_html,
                    element_id=element_id,
                    element_tag="img",
                    image_src=path,
                    image_reference=filename,
                    image_text=detected_text,
                    page_url=r.get("url") or page_url,
                )
            )
    return findings


def _name_role_value_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
    findings = []
    sev = _PYTHON_SEVERITY.get("4.1.2")
    for r in records:
        status_raw = r.get("wcag_4_1_2_status", "")
        if status_raw in ("N/A", ""):
            continue

        reason = r.get("wcag_4_1_2_reason") or ""
        src = r.get("src", "")
        alt = r.get("alt_text", "")
        alt_attr = f' alt="{alt}"' if alt is not None else ""
        element_html = f'<img src="{src}"{alt_attr}>'
        element_id = r.get("src") or r.get("filename") or None

        path = r.get("screenshot_path")
        filename = r.get("filename")
        detected_text = r.get("detected_text")

        if status_raw == "INCOMPLETE":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_4_1_2_name_role_value",
                    wcag_sc="4.1.2",
                    status="needs_review",
                    reason_code="capture_failed",
                    reason=reason or None,
                    severity=sev,
                    element_html=element_html,
                    element_id=element_id,
                    element_tag="img",
                    image_src=path,
                    image_reference=filename,
                    image_text=detected_text,
                    page_url=r.get("url") or page_url,
                )
            )
        elif status_raw == "FAILED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_4_1_2_name_role_value",
                    wcag_sc="4.1.2",
                    status="fail",
                    reason_code="fail",
                    reason=reason or None,
                    severity=sev,
                    element_html=element_html,
                    element_id=element_id,
                    element_tag="img",
                    image_src=path,
                    image_reference=filename,
                    image_text=detected_text,
                    page_url=r.get("url") or page_url,
                )
            )
        elif status_raw == "PASSED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_4_1_2_name_role_value",
                    wcag_sc="4.1.2",
                    status="pass",
                    reason_code="pass",
                    reason=reason or None,
                    severity=None,
                    element_html=element_html,
                    element_id=element_id,
                    element_tag="img",
                    image_src=path,
                    image_reference=filename,
                    image_text=detected_text,
                    page_url=r.get("url") or page_url,
                )
            )
    return findings


def _contrast_to_findings(ocr_results: list, page_url: str) -> List[Dict]:
    findings = []
    for result in ocr_results:
        if not result.has_text:
            continue

        # WCAG 1.4.3 Exception: Logos and decorative images have no contrast requirement
        classification = _infer_classification(result.original_path)
        if classification in ("logo", "decorative"):
            continue

        for det in result.detections:
            ci = det.contrast_info or {}
            col = det.color_info or {}
            dom = col.get("dominant_contrast") or {}
            dom_compliance = dom.get("compliance") or {}
            if dom_compliance:
                aa_normal = dom_compliance.get("AA_passes")
                ratio = dom_compliance.get("contrast_ratio")
                is_large = dom_compliance.get("is_large_text", False)
                threshold = dom_compliance.get("aa_threshold_used", 4.5)
            else:
                compliance = ci.get("compliance") or {}
                aa_normal = compliance.get("AA_passes")
                ratio = compliance.get("contrast_ratio")
                is_large = compliance.get("is_large_text", False)
                threshold = compliance.get("aa_threshold_used", 4.5)
            fg = col.get("foreground") or {}
            bg_pal = col.get("background_palette") or []
            dom_bg_obj = dom.get("bg_color") or {}
            dominant_bg = dom_bg_obj if dom_bg_obj else (bg_pal[0] if bg_pal else {})
            fg_hex = fg.get("hex") or ci.get("foreground_color") or "?"
            bg_hex = dominant_bg.get("hex") or ci.get("background_color") or "?"
            ratio_str = f"{ratio:.2f}:1" if ratio is not None else "unknown"
            text_snippet = (det.text or "")[:60].replace('"', "'")
            text_type = "large text" if is_large else "normal text"
            element_html = f'<img-text fg="{fg_hex}" bg="{bg_hex}" ratio="{ratio_str}">{text_snippet}</img-text>'
            image_label = f'{result.filename} -- "{text_snippet}"'

            common_params = {
                "filename": result.filename,
                "image_label": image_label,
                "ratio": ratio_str,
                "fg_hex": fg_hex,
                "bg_hex": bg_hex,
                "threshold": threshold,
                "text_type": text_type,
            }
            if aa_normal is None:
                findings.append(
                    _make_finding(
                        source="python",
                        rule_id="python_1_4_3_contrast",
                        wcag_sc="1.4.3",
                        status="needs_review",
                        reason_code="needs_review_unknown",
                        reason_params=common_params,
                        severity=_PYTHON_SEVERITY["1.4.3"],
                        element_html=element_html,
                        element_id=None,
                        element_tag="img",
                        image_src=result.original_path,
                        image_reference=result.filename,
                        image_text=det.text,
                        page_url=page_url,
                    )
                )
                continue
            if not aa_normal:
                findings.append(
                    _make_finding(
                        source="python",
                        rule_id="python_1_4_3_contrast",
                        wcag_sc="1.4.3",
                        status="fail",
                        reason_code="fail",
                        reason_params=common_params,
                        severity=_PYTHON_SEVERITY["1.4.3"],
                        element_html=element_html,
                        element_id=None,
                        element_tag="img",
                        image_src=result.original_path,
                        image_reference=result.filename,
                        image_text=det.text,
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
                        reason_code="pass",
                        reason_params=common_params,
                        severity=None,
                        element_html=element_html,
                        element_id=result.filename,
                        element_tag="img",
                        image_src=result.original_path,
                        image_reference=result.filename,
                        image_text=det.text,
                        page_url=page_url,
                    )
                )
    return findings


def _contrast_enhanced_to_findings(ocr_results: list, page_url: str) -> List[Dict]:
    findings = []
    for result in ocr_results:
        if not result.has_text:
            continue

        # WCAG 1.4.6 Exception: Logos and decorative images have no contrast requirement
        classification = _infer_classification(result.original_path)
        if classification in ("logo", "decorative"):
            continue

        for det in result.detections:
            ci = det.contrast_info or {}
            col = det.color_info or {}
            dom = col.get("dominant_contrast") or {}
            dom_compliance = dom.get("compliance") or {}
            if dom_compliance:
                aaa_passes = dom_compliance.get("AAA_passes")
                ratio = dom_compliance.get("contrast_ratio")
                is_large = dom_compliance.get("is_large_text", False)
                threshold = dom_compliance.get("aaa_threshold_used", 7.0)
            else:
                compliance = ci.get("compliance") or {}
                aaa_passes = compliance.get("AAA_passes")
                ratio = compliance.get("contrast_ratio")
                is_large = compliance.get("is_large_text", False)
                threshold = compliance.get("aaa_threshold_used", 7.0)
            fg = col.get("foreground") or {}
            bg_pal = col.get("background_palette") or []
            dom_bg_obj = dom.get("bg_color") or {}
            dominant_bg = dom_bg_obj if dom_bg_obj else (bg_pal[0] if bg_pal else {})
            fg_hex = fg.get("hex") or ci.get("foreground_color") or "?"
            bg_hex = dominant_bg.get("hex") or ci.get("background_color") or "?"
            ratio_str = f"{ratio:.2f}:1" if ratio is not None else "unknown"
            text_snippet = (det.text or "")[:60].replace('"', "'")
            text_type = "large text" if is_large else "normal text"
            element_html = f'<img-text fg="{fg_hex}" bg="{bg_hex}" ratio="{ratio_str}">{text_snippet}</img-text>'
            image_label = f'{result.filename} -- "{text_snippet}"'

            common_params = {
                "filename": result.filename,
                "image_label": image_label,
                "ratio": ratio_str,
                "fg_hex": fg_hex,
                "bg_hex": bg_hex,
                "threshold": threshold,
                "text_type": text_type,
            }
            if aaa_passes is None:
                findings.append(
                    _make_finding(
                        source="python",
                        rule_id="python_1_4_6_contrast_enhanced",
                        wcag_sc="1.4.6",
                        status="needs_review",
                        reason_code="needs_review_unknown",
                        reason_params=common_params,
                        severity=_PYTHON_SEVERITY.get("1.4.6"),
                        element_html=element_html,
                        element_id=None,
                        element_tag="img",
                        image_src=result.original_path,
                        image_reference=result.filename,
                        image_text=det.text,
                        page_url=page_url,
                    )
                )
                continue
            if not aaa_passes:
                findings.append(
                    _make_finding(
                        source="python",
                        rule_id="python_1_4_6_contrast_enhanced",
                        wcag_sc="1.4.6",
                        status="fail",
                        reason_code="fail",
                        reason_params=common_params,
                        severity=_PYTHON_SEVERITY.get("1.4.6"),
                        element_html=element_html,
                        element_id=None,
                        element_tag="img",
                        image_src=result.original_path,
                        image_reference=result.filename,
                        image_text=det.text,
                        page_url=page_url,
                    )
                )
            else:
                findings.append(
                    _make_finding(
                        source="python",
                        rule_id="python_1_4_6_contrast_enhanced",
                        wcag_sc="1.4.6",
                        status="pass",
                        reason_code="pass",
                        reason_params=common_params,
                        severity=None,
                        element_html=element_html,
                        element_id=result.filename,
                        element_tag="img",
                        image_src=result.original_path,
                        image_reference=result.filename,
                        image_text=det.text,
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

        path = r.get("screenshot_path")
        filename = r.get("filename")
        detected_text = r.get("detected_text")

        if status_raw == "INCOMPLETE":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_4_5_images_of_text",
                    wcag_sc="1.4.5",
                    status="needs_review",
                    reason_code="capture_failed",
                    reason=reason or None,
                    severity=sev,
                    element_html=element_html,
                    element_id=element_id,
                    element_tag="img",
                    image_src=path,
                    image_reference=filename,
                    image_text=detected_text,
                    page_url=r.get("url") or page_url,
                )
            )
        elif status_raw == "FAILED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_4_5_images_of_text",
                    wcag_sc="1.4.5",
                    status="fail",
                    reason_code="fail",
                    reason=reason or None,
                    severity=sev,
                    element_html=element_html,
                    element_id=element_id,
                    element_tag="img",
                    image_src=path,
                    image_reference=filename,
                    image_text=detected_text,
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
                    reason_code="pass",
                    reason=reason or None,
                    severity=None,
                    element_html=element_html,
                    element_id=element_id,
                    element_tag="img",
                    image_src=path,
                    image_reference=filename,
                    image_text=detected_text,
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
        reason = r.get("wcag_1_4_11_reason") or ""
        needs_review = status_raw == "INCOMPLETE" or (
            status_raw == "N/A" and _is_incomplete_reason(reason)
        )
        if status_raw == "N/A" and not needs_review:
            continue
        src = r.get("src", "")
        alt = r.get("alt_text", "")
        alt_attr = f' alt="{alt}"' if alt is not None else ""
        element_html = f'<img src="{src}"{alt_attr}>'
        element_id = r.get("src") or r.get("filename") or None

        path = r.get("screenshot_path")
        filename = r.get("filename")
        detected_text = r.get("detected_text")

        if needs_review:
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_4_11_non_text_contrast",
                    wcag_sc="1.4.11",
                    status="needs_review",
                    reason_code="needs_review",
                    reason=reason or None,
                    severity=sev,
                    element_html=element_html,
                    element_id=element_id,
                    element_tag="img",
                    image_src=path,
                    image_reference=filename,
                    image_text=detected_text,
                    page_url=r.get("url") or page_url,
                )
            )
        elif status_raw == "FAILED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_4_11_non_text_contrast",
                    wcag_sc="1.4.11",
                    status="fail",
                    reason_code="fail",
                    reason=reason or None,
                    severity=sev,
                    element_html=element_html,
                    element_id=element_id,
                    element_tag="img",
                    image_src=path,
                    image_reference=filename,
                    image_text=detected_text,
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
                    reason_code="pass",
                    reason=reason or None,
                    severity=None,
                    element_html=element_html,
                    element_id=element_id,
                    element_tag="img",
                    image_src=path,
                    image_reference=filename,
                    image_text=detected_text,
                    page_url=r.get("url") or page_url,
                )
            )
    return findings


def _form_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
    findings = []
    for r in records:
        element_kwargs = _record_element_kwargs(
            r,
            page_url,
            html_key="html_snippet",
            element_id_keys=("field_id", "element_id", "field_name", "element_name"),
            tag_key="field_tag",
        )
        if not element_kwargs["element_tag"]:
            element_kwargs["element_tag"] = r.get("tag", "INPUT")
        for sc, status_key in [
            ("3.3.1", "wcag_3_3_1_status"),
            ("3.3.2", "wcag_3_3_2_status"),
        ]:
            # form_auditor.py stores plural "wcag_3_3_1_violations" / "wcag_3_3_2_violations"
            violation_key = status_key.replace("_status", "_violations")
            status_raw = r.get(status_key, "")
            rule_id = f"python_{sc.replace('.', '_')}"
            if status_raw == "FAILED":
                findings.append(
                    _make_finding(
                        source="python",
                        rule_id=rule_id,
                        wcag_sc=sc,
                        status="fail",
                        reason_code="fail",
                        reason=r.get(violation_key) or None,
                        severity=_PYTHON_SEVERITY[sc],
                        **element_kwargs,
                    )
                )
            elif status_raw == "PASSED":
                findings.append(
                    _make_finding(
                        source="python",
                        rule_id=rule_id,
                        wcag_sc=sc,
                        status="pass",
                        reason_code="pass",
                        severity=None,
                        **element_kwargs,
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
                    reason_code="fail",
                    reason=r.get("wcag_2_5_3_violation") or None,
                    severity=_PYTHON_SEVERITY["2.5.3"],
                    **_record_element_kwargs(r, page_url),
                )
            )
        elif status_raw == "PASSED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_2_5_3_label_in_name",
                    wcag_sc="2.5.3",
                    status="pass",
                    reason_code="pass",
                    severity=None,
                    **_record_element_kwargs(r, page_url),
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
                    reason_code="fail",
                    reason=r.get("wcag_2_2_2_violation") or None,
                    severity=_PYTHON_SEVERITY["2.2.2"],
                    **_record_element_kwargs(r, page_url),
                )
            )
        elif status_raw == "NEEDS_REVIEW":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_2_2_2_pause_stop_hide",
                    wcag_sc="2.2.2",
                    status="needs_review",
                    reason_code="needs_review",
                    reason=r.get("wcag_2_2_2_violation") or None,
                    severity=_PYTHON_SEVERITY["2.2.2"],
                    **_record_element_kwargs(r, page_url),
                )
            )
        elif status_raw == "PASSED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_2_2_2_pause_stop_hide",
                    wcag_sc="2.2.2",
                    status="pass",
                    reason_code="pass",
                    severity=None,
                    **_record_element_kwargs(r, page_url),
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
        size_params = {"width": f"{w:.0f}", "height": f"{h:.0f}"}
        if status_raw == "FAILED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_2_5_8_target_size",
                    wcag_sc="2.5.8",
                    status="fail",
                    reason_code="fail",
                    reason_params=size_params,
                    reason=r.get("wcag_2_5_8_violation") or None,
                    severity=_PYTHON_SEVERITY["2.5.8"],
                    **_record_element_kwargs(r, page_url),
                )
            )
        elif status_raw == "PASSED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_2_5_8_target_size",
                    wcag_sc="2.5.8",
                    status="pass",
                    reason_code="pass",
                    reason_params=size_params,
                    severity=None,
                    **_record_element_kwargs(r, page_url),
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
    pass_code: str = "pass",
    fail_code: str = "fail_unknown",
    needs_review_code: str = "needs_review_unknown",
    emit_synthetic_pass: bool = False,
) -> List[Dict]:
    """Generic converter for rendered-layout rule records.

    Reason text is rendered from the localized YAML templates. The auditor's
    raw English `*_violation` string is passed as the fallback so a finding
    never ships with a blank reason if no template is found.

    When `emit_synthetic_pass` is True and records is empty, a page-level pass
    is emitted so the rule still appears in reports.
    """
    if not records and emit_synthetic_pass:
        return [
            _make_finding(
                source="python",
                rule_id=rule_id,
                wcag_sc=wcag_sc,
                status="pass",
                reason_code="pass_no_records",
                severity=None,
                element_html="",
                element_id=None,
                element_tag=None,
                page_url=page_url,
            )
        ]

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
                    reason_code=fail_code,
                    reason=violation or None,
                    severity=sev,
                    **_record_element_kwargs(r, page_url),
                )
            )
        elif status_raw == "NEEDS_REVIEW":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id=rule_id,
                    wcag_sc=wcag_sc,
                    status="needs_review",
                    reason_code=needs_review_code,
                    reason=violation or None,
                    severity=sev,
                    **_record_element_kwargs(r, page_url),
                )
            )
        elif status_raw == "PASSED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id=rule_id,
                    wcag_sc=wcag_sc,
                    status="pass",
                    reason_code=pass_code,
                    severity=None,
                    **_record_element_kwargs(r, page_url),
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
        emit_synthetic_pass=True,
    )


def _reflow_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
    return _rendered_rule_to_findings(
        records,
        page_url,
        rule_key="wcag_1_4_10",
        rule_id="python_1_4_10_reflow",
        wcag_sc="1.4.10",
        emit_synthetic_pass=True,
    )


def _crawler_text_spacing_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
    """Convert TextSpacingAuditor (static structural analysis) records to findings."""
    findings: List[Dict] = []
    sev = _PYTHON_SEVERITY.get("1.4.12")
    for r in records:
        status_raw = r.get("wcag_1_4_12_status", "")
        if status_raw == "N/A":
            continue
        violation = r.get("wcag_1_4_12_violation", "")
        if status_raw == "FAILED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_4_12_text_spacing_static",
                    wcag_sc="1.4.12",
                    status="fail",
                    reason_code="fail",
                    reason=violation or None,
                    severity=sev,
                    **_record_element_kwargs(r, page_url),
                )
            )
        elif status_raw == "WARNING":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_4_12_text_spacing_static",
                    wcag_sc="1.4.12",
                    status="needs_review",
                    reason_code="needs_review_warning",
                    reason=violation or None,
                    severity=sev,
                    **_record_element_kwargs(r, page_url),
                )
            )
        elif status_raw == "INFO":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_4_12_text_spacing_static",
                    wcag_sc="1.4.12",
                    status="needs_review",
                    reason_code="needs_review_info",
                    reason=violation or None,
                    severity=sev,
                    **_record_element_kwargs(r, page_url),
                )
            )
        elif status_raw == "PASSED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_4_12_text_spacing_static",
                    wcag_sc="1.4.12",
                    status="pass",
                    reason_code="pass_static",
                    severity=None,
                    **_record_element_kwargs(r, page_url),
                )
            )
    return findings


def _sensory_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
    """
    Convert SensoryCharacteristicsAuditor records to standard findings
    for WCAG 1.3.3 — Sensory Characteristics (Level A).

    If the stage ran but produced no sensory records, emit a synthetic
    page-level pass so the rule still appears in the final report.
    """
    findings: List[Dict[str, Any]] = []
    sev = _PYTHON_SEVERITY.get("1.3.3", "serious")

    if not records:
        return [
            _make_finding(
                source="python",
                rule_id="python_1_3_3_sensory_characteristics",
                wcag_sc="1.3.3",
                status="pass",
                reason_code="pass_no_records",
                severity=None,
                element_html="",
                element_id=None,
                element_tag=None,
                page_url=page_url,
            )
        ]

    for r in records:
        status_raw = r.get("wcag_1_3_3_status", "")

        if status_raw == "FAILED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_3_3_sensory_characteristics",
                    wcag_sc="1.3.3",
                    status="fail",
                    reason_code="fail_default",
                    reason_params={
                        "sensory_categories": r.get(
                            "sensory_categories", "unspecified"
                        ),
                    },
                    reason=r.get("wcag_1_3_3_violation") or None,
                    severity=sev,
                    **_record_element_kwargs(
                        r,
                        page_url,
                        element_id_keys=("element_id",),
                        tag_key="element_tag",
                    ),
                )
            )
        elif status_raw == "PASSED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_3_3_sensory_characteristics",
                    wcag_sc="1.3.3",
                    status="pass",
                    reason_code="pass",
                    severity=None,
                    **_record_element_kwargs(
                        r,
                        page_url,
                        element_id_keys=("element_id",),
                        tag_key="element_tag",
                    ),
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
        pass_code="pass_rendered",
    )


def _orientation_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
    return _rendered_rule_to_findings(
        records,
        page_url,
        rule_key="wcag_1_3_4",
        rule_id="python_1_3_4_orientation",
        wcag_sc="1.3.4",
    )


def _hover_focus_content_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
    return _rendered_rule_to_findings(
        records,
        page_url,
        rule_key="wcag_1_4_13",
        rule_id="python_1_4_13_hover_or_focus_content",
        wcag_sc="1.4.13",
        emit_synthetic_pass=True,
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
        emit_synthetic_pass=True,
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
        emit_synthetic_pass=True,
    )


def _media_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
    """Convert MediaAuditor records to standard findings for WCAG 1.2.1."""
    findings = []
    for r in records:
        status_raw = r.get("wcag_1_2_1_status", "")
        if status_raw == "N/A":
            continue
        if status_raw == "FAILED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_2_1_media",
                    wcag_sc="1.2.1",
                    status="fail",
                    reason_code="fail_no_alt",
                    reason=r.get("wcag_1_2_1_violation") or None,
                    severity=_PYTHON_SEVERITY.get("1.2.1", "critical"),
                    **_record_element_kwargs(r, page_url),
                )
            )
        elif status_raw == "NEEDS_REVIEW":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_2_1_media",
                    wcag_sc="1.2.1",
                    status="needs_review",
                    reason_code="needs_review",
                    reason=r.get("wcag_1_2_1_violation") or None,
                    severity=_PYTHON_SEVERITY.get("1.2.1", "critical"),
                    **_record_element_kwargs(r, page_url),
                )
            )
        elif status_raw == "PASSED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_2_1_media",
                    wcag_sc="1.2.1",
                    status="pass",
                    reason_code="pass",
                    severity=None,
                    **_record_element_kwargs(r, page_url),
                )
            )
    return findings


def _contrast_capture_failed_to_findings(
    images_data: list, page_url: str
) -> List[Dict]:
    """
    Emit WCAG 1.4.3 and 1.4.6 needs_review findings for images whose screenshot
    capture failed so OCR could not run.  Called after the OCR result converters
    so the finding appears alongside normal contrast findings.
    """
    findings: List[Dict] = []
    for img in images_data:
        capture_status = getattr(img, "capture_status", "ok") or "ok"
        if capture_status == "ok":
            continue
        src = getattr(img, "src", "") or ""
        filename = getattr(img, "filename", "") or ""
        url = getattr(img, "url", "") or page_url
        capture_error = getattr(img, "capture_error", None)
        capture_params = {
            "capture_status": capture_status,
            "capture_error_suffix": (
                f", error: {capture_error}" if capture_error else ""
            ),
        }
        element_html = f'<img src="{src}">'
        for wcag_sc, rule_id, sev in [
            ("1.4.3", "python_1_4_3_contrast", _PYTHON_SEVERITY.get("1.4.3")),
            ("1.4.6", "python_1_4_6_contrast_enhanced", _PYTHON_SEVERITY.get("1.4.6")),
        ]:
            findings.append(
                _make_finding(
                    source="python",
                    rule_id=rule_id,
                    wcag_sc=wcag_sc,
                    status="needs_review",
                    reason_code="capture_failed",
                    reason_params=capture_params,
                    severity=sev,
                    element_html=element_html,
                    element_id=src or filename or None,
                    element_tag="img",
                    image_src="",
                    image_reference=filename,
                    image_text=None,
                    page_url=url,
                )
            )
    return findings


# ── Converter registries ─────────────────────────────────────────────────────

# Register image-audit rules here so new raw status keys are wired to the
# combined result model in one place.
IMAGE_AUDIT_RECORD_CONVERTERS = (
    ("wcag_1_1_1_status", _alt_text_to_findings),
    ("wcag_4_1_2_status", _name_role_value_to_findings),
    ("wcag_1_4_5_status", _images_of_text_to_findings),
    ("wcag_1_4_11_status", _non_text_contrast_to_findings),
)

# Register OCR-derived rule converters here so new image-text/contrast checks
# cannot be added without explicitly joining the combined result path.
OCR_RESULT_CONVERTERS = (
    ("1.4.3", _contrast_to_findings),
    ("1.4.6", _contrast_enhanced_to_findings),
)
