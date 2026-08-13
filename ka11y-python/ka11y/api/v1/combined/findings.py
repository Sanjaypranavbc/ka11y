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
import os
from typing import Any, Dict, List, Optional

from ka11y.accessibility.rules.non_text.alttext import (
    _EMPTY_OR_GENERIC as _EMPTY_OR_GENERIC_ALT,
    _norm as _norm_alt,
)
from ka11y.config.logger import setup_logger
from ka11y.utils.url_canonical import canonicalize_url as _canonicalize_url
from ka11y.i18n.loader import (
    get_level_label,
    get_severity_label,
    get_status_label,
    get_suggested_fixes,
    get_wcag_names,
    render_reason,
)

from .auditor_field_map import get_status, get_reason
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
    quality_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    # R-2: canonicalise the page_url at the central choke point so dedup keys
    # in _merge_findings and the per-page UI grouping see identical strings
    # across stages and engines. Idempotent — safe to call here even if a
    # caller already canonicalised.
    page_url = _canonicalize_url(page_url) if page_url else page_url
    is_pass = status in ("pass", "inapplicable")
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
        if element and quality_report:
            element["quality_report"] = quality_report
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
        if quality_report:
            element["quality_report"] = quality_report

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
        "detected_by": ["python"],
        "reason_code": reason_code,
        "suggested_fix": None if is_pass else suggested_fixes.get(wcag_sc),
        "help_url": None,
        "element": element,
    }


def _is_incomplete_reason(reason: str) -> bool:
    """Identify manual-review reasons that should surface as needs_review."""
    return reason.strip().upper().startswith("INCOMPLETE")


# ── Alt-text reason-code selection ────────────────────────────────────────────
#
# The localized reason shown in the UI comes from `reason_code` → i18n YAML.
# Every 1.1.1 failure used to be emitted as `fail_missing_alt` ("this image has
# no alt attribute"), regardless of why it actually failed — so an <img> that
# DOES carry alt="YouTube" was reported to the client as having no alt text.
# The code is now derived from the record itself so the message matches the
# defect. Derived from fields, never by parsing the English reason string.


def _alt_is_generic(value: Optional[str]) -> bool:
    """True when the alt text is present but carries no information."""
    if value is None:
        return False
    return _norm_alt(value) in _EMPTY_OR_GENERIC_ALT


def _alt_reason_params(record: Dict[str, Any]) -> Dict[str, Any]:
    """Placeholder values shared by every 1.1.1 reason template."""
    return {
        "name": record.get("alt_text") or "",
        "ocr_text": record.get("detected_text") or "",
    }


def _alt_text_reason_code(record: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    """Pick the i18n reason code + params for a 1.1.1 record.

    The auditor stamps ``wcag_1_1_1_code`` whenever its branch knows the exact
    situation; that always wins. The derivation below only covers branches that
    did not name one.
    """
    alt = record.get("alt_text")
    params = _alt_reason_params(record)
    classification = str(record.get("classification") or "").strip().lower()
    sub_type = str(record.get("sub_type") or "").strip().lower()

    explicit = str(record.get("wcag_1_1_1_code") or "").strip()
    if explicit:
        return explicit, params

    # No alt attribute at all — the only case that is genuinely "missing alt".
    if alt is None:
        return "missing_alt", params

    if classification == "decorative":
        # Marked decorative yet exposing a description (or vice versa).
        return "decorative_invalid", params

    if not str(alt).strip():
        return "missing_alt", params

    if _alt_is_generic(alt):
        return "generic_alt", params

    if sub_type == "logos":
        return "logo_review", params

    if sub_type == "icons":
        return "icon_terse", params

    if record.get("has_ocr_text"):
        # Informative image whose alt does not convey the text baked into it.
        return "alt_text_mismatch", params

    return "generic_alt", params


def _incomplete_reason_code(record: Dict[str, Any], sc: str = "1.1.1") -> str:
    """`capture_failed` only when the screenshot really could not be captured.

    A needs_review verdict that the rule reached deliberately (an unverifiable
    long description, an OCR/alt mismatch) carries its own code and must not be
    mislabelled as a capture failure.
    """
    capture_status = str(record.get("capture_status") or "ok")
    if capture_status != "ok":
        return "capture_failed"
    explicit = str(record.get(f"wcag_{sc.replace('.', '_')}_code") or "").strip()
    return explicit or "needs_review_unknown"


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
        "quality_report": record.get("quality_report"),
    }


# ── Image classification inference ────────────────────────────────────────────


def _infer_classification(path: str) -> str:
    """Derive the image classification from its storage path."""
    p = path.replace("\\", "/").lower()
    if "/functional/buttons/" in p:
        return "button"
    if "/functional/icons/" in p:
        return "icon"
    if "/functional/logos/" in p:
        return "functional_logo"
    if "/informative/logos/" in p:
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


def _build_contrast_report(
    ocr_results: list,
    page_by_filename: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Extract contrast data from OCR results into a structured report.

    ``page_by_filename`` maps a saved image filename → the page URL it was found
    on (built from the crawler's ``images_data``). It lets the UI group/filter
    the image visualiser per page on multi-page crawls (max_depth > 0). When the
    map is absent or has no entry for an image, ``page_url`` falls back to None.

    Returns
    -------
    {
        "summary": { total_regions_analysed, total_violations,
                     images_with_violations, pass_rate_pct },
        "table":   [ flat row per detected text region ],
        "images":  [ per-image nested detail ],
    }
    """
    page_by_filename = page_by_filename or {}

    def _page_for(result: Any) -> Optional[str]:
        # Match on the saved filename first, then the screenshot basename.
        fn = getattr(result, "filename", None)
        if fn and fn in page_by_filename:
            return page_by_filename[fn]
        orig = getattr(result, "original_path", None)
        if orig:
            base = os.path.basename(str(orig))
            if base in page_by_filename:
                return page_by_filename[base]
        return None

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
                    "page_url": _page_for(result),
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
                # Page the image was discovered on — drives the per-page image
                # visualiser on multi-page crawls (max_depth > 0).
                "page_url": record.get("url"),
                "alt_text": record.get("alt_text"),
                "title": record.get("title"),
                "classification": classification,
                "sub_type": record.get("sub_type") or None,
                "overall_status": overall_status,
                "has_ocr_text": bool(record.get("has_ocr_text")),
                "detected_text": record.get("detected_text") or "",
                "contrast_violations_count": contrast_violations_count,
                "wcag_1_1_1_status": get_status(record, "1.1.1", default=None),
                "wcag_4_1_2_status": get_status(record, "4.1.2", default=None),
                "wcag_1_4_3_status": get_status(record, "1.4.3", default=None),
                "wcag_1_4_5_status": get_status(record, "1.4.5", default=None),
                "wcag_1_4_6_status": get_status(record, "1.4.6", default=None),
                "wcag_1_4_11_status": get_status(record, "1.4.11", default=None),
                "wcag_1_1_1_reason": get_reason(record, "1.1.1"),
                "wcag_4_1_2_reason": get_reason(record, "4.1.2"),
                "wcag_1_4_3_reason": get_reason(record, "1.4.3"),
                "wcag_1_4_5_reason": get_reason(record, "1.4.5"),
                "wcag_1_4_6_reason": get_reason(record, "1.4.6"),
                "wcag_1_4_11_reason": get_reason(record, "1.4.11"),
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
        status_raw = get_status(r, "1.1.1", default="")
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
                    reason_code=_incomplete_reason_code(r),
                    reason_params=_alt_reason_params(r),
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
            fail_code, fail_params = _alt_text_reason_code(r)
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_1_1_alt",
                    wcag_sc="1.1.1",
                    status="fail",
                    reason_code=fail_code,
                    reason_params=fail_params,
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
        status_raw = get_status(r, "4.1.2", default="")
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
                    reason_code=_incomplete_reason_code(r, "4.1.2"),
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


def _contrast_to_findings(
    ocr_results: list,
    page_url: str,
    page_by_filename: Optional[Dict[str, str]] = None,
) -> List[Dict]:
    # page_by_filename maps OCR result.filename → the page the image was scraped
    # from; without it every contrast finding on a multi-page crawl collapses to
    # the root page_url and child pages silently lose 1.4.3 findings in the UI.
    findings = []
    _by_fn = page_by_filename or {}
    for result in ocr_results:
        _pu = _by_fn.get(result.filename) or page_url
        if not result.has_text:
            continue

        # WCAG 1.4.3 Exception: Logos and decorative images have no contrast requirement.
        # Functional components (even if they are logos) should still be evaluated.
        classification = _infer_classification(result.original_path)
        if classification in ("logo", "decorative") and getattr(result, "category", "") != "button_text":
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
                        page_url=_pu,
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
                        page_url=_pu,
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
                        page_url=_pu,
                    )
                )
    return findings


def _contrast_enhanced_to_findings(
    ocr_results: list,
    page_url: str,
    page_by_filename: Optional[Dict[str, str]] = None,
) -> List[Dict]:
    findings = []
    _by_fn = page_by_filename or {}
    for result in ocr_results:
        _pu = _by_fn.get(result.filename) or page_url
        if not result.has_text:
            continue

        # WCAG 1.4.6 Exception: Logos and decorative images have no contrast requirement
        classification = _infer_classification(result.original_path)
        if classification in ("logo", "decorative") and getattr(result, "category", "") != "button_text":
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
                        page_url=_pu,
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
                        page_url=_pu,
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
                        page_url=_pu,
                    )
                )
    return findings


def _images_of_text_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
    """Convert image-audit records to WCAG 1.4.5 (Images of Text) findings."""
    findings: List[Dict] = []
    sev = _PYTHON_SEVERITY.get("1.4.5")
    for r in records:
        status_raw = get_status(r, "1.4.5", default="N/A")
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
                    reason_code=_incomplete_reason_code(r, "1.4.5"),
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
        status_raw = get_status(r, "1.4.11", default="N/A")
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


def _media_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
    """Convert MediaAuditor records to standard findings for WCAG 1.2.1 and 1.2.2."""
    if not records:
        return [
            _make_finding(
                source="python", rule_id="python_1_2_1_media", wcag_sc="1.2.1", status="pass",
                reason="No media elements found on page.", severity=None, page_url=page_url
            ),
            _make_finding(
                source="python", rule_id="python_1_2_2_media", wcag_sc="1.2.2", status="pass",
                reason="No media elements found on page.", severity=None, page_url=page_url
            )
        ]

    findings = []
    for r in records:
        # WCAG 1.2.1
        s_121 = get_status(r, "1.2.1", default="")
        if s_121 == "FAILED":
            findings.append(_make_finding(
                source="python", rule_id="python_1_2_1_media", wcag_sc="1.2.1", status="fail",
                reason=r.get("wcag_1_2_1_violation") or "No text alternative for prerecorded media.",
                severity=_PYTHON_SEVERITY.get("1.2.1", "critical"), **_record_element_kwargs(r, page_url)
            ))
        elif s_121 == "NEEDS_REVIEW":
            findings.append(_make_finding(
                source="python", rule_id="python_1_2_1_media", wcag_sc="1.2.1", status="needs_review",
                reason=r.get("wcag_1_2_1_violation") or "Manual review required for transcript quality.",
                severity=_PYTHON_SEVERITY.get("1.2.1", "critical"), **_record_element_kwargs(r, page_url)
            ))
        elif s_121 == "PASSED":
            findings.append(_make_finding(
                source="python", rule_id="python_1_2_1_media", wcag_sc="1.2.1", status="pass",
                reason="Prerecorded media has an equivalent text alternative.",
                severity=None, **_record_element_kwargs(r, page_url)
            ))
        elif s_121 == "N/A":
            findings.append(_make_finding(
                source="python", rule_id="python_1_2_1_media", wcag_sc="1.2.1", status="inapplicable",
                reason=r.get("wcag_1_2_1_violation") or "Rule 1.2.1 evaluates to N/A for this element.",
                severity=None, **_record_element_kwargs(r, page_url)
            ))

        # WCAG 1.2.2
        s_122 = get_status(r, "1.2.2", default="")
        if s_122 == "FAILED":
            findings.append(_make_finding(
                source="python", rule_id="python_1_2_2_media", wcag_sc="1.2.2", status="fail",
                reason=r.get("wcag_1_2_2_violation") or "No captions found for synchronized media.",
                severity=_PYTHON_SEVERITY.get("1.2.2", "critical"), **_record_element_kwargs(r, page_url)
            ))
        elif s_122 == "NEEDS_REVIEW":
            findings.append(_make_finding(
                source="python", rule_id="python_1_2_2_media", wcag_sc="1.2.2", status="needs_review",
                reason=r.get("wcag_1_2_2_violation") or "Manual review required for captions quality.",
                severity=_PYTHON_SEVERITY.get("1.2.2", "critical"), **_record_element_kwargs(r, page_url)
            ))
        elif s_122 == "PASSED":
            findings.append(_make_finding(
                source="python", rule_id="python_1_2_2_media", wcag_sc="1.2.2", status="pass",
                reason="Synchronized media has a captions track.",
                severity=None, **_record_element_kwargs(r, page_url)
            ))
        elif s_122 == "N/A":
            findings.append(_make_finding(
                source="python", rule_id="python_1_2_2_media", wcag_sc="1.2.2", status="inapplicable",
                reason=r.get("wcag_1_2_2_violation") or "Rule 1.2.2 evaluates to N/A for this element.",
                severity=None, **_record_element_kwargs(r, page_url)
            ))
            
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
