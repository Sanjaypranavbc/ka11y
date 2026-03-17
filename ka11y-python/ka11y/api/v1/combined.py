"""
ka11y/api/v1/combined.py
========================
Async combined audit — Python auditors + Node axe-core running in parallel.

  POST /combined/          → 202 { job_id, status: "pending" }
  GET  /combined/{job_id} → job status / combined_report.json content

Output format — flat element-wise findings
──────────────────────────────────────────
Every finding (violation / needs_review / pass) has:
  source          "axe" | "python"
  rule_id         axe rule ID or internal Python rule key
  wcag_sc         "1.1.1"
  criterion_name  "Non-text Content"
  level           "A" | "AA" | "AAA"
  severity        "critical" | "high" | "medium" | "low" | null
  status          "fail" | "pass" | "needs_review"
  reason          human-readable explanation
  suggested_fix   static remediation hint (null for passes)
  element         { html, element_id, tag, page_url } | null  (null for pass rules)

The job also writes combined_report.json to the output directory.
"""

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl

from ka11y.crawler.crawler import AsyncImageCrawler
from ka11y.crawler.forms_crawler import AsyncFormCrawler
from ka11y.crawler.interactive_crawler import InteractiveElementCrawler
from ka11y.crawler.moving_content_crawler import MovingContentCrawler
from ka11y.crawler.target_size_crawler import TargetSizeCrawler
from ka11y.text_detector.text_detector import OCRPreprocessing, TextClassification
from ka11y.accessibility.rules.non_text.alttext import AltTextAccessibilityAuditor
from ka11y.accessibility.rules.forms.form_auditor import FormAccessibilityAuditor
from ka11y.accessibility.rules.input_modalities.label_in_name_auditor import (
    LabelInNameAuditor,
)
from ka11y.accessibility.rules.input_modalities.target_size_auditor import (
    TargetSizeAuditor,
)
from ka11y.accessibility.rules.timing.pause_stop_hide_auditor import (
    PauseStopHideAuditor,
)
from ka11y.config.logger import setup_logger
from ka11y.utils.config_loader import load_config

router = APIRouter(prefix="/combined", tags=["combined"])
logger = setup_logger(name="KAC", tag="combined")

# ── In-memory job store ────────────────────────────────────────────────────────
_jobs: Dict[str, Dict[str, Any]] = {}


# ── Static metadata ────────────────────────────────────────────────────────────

_WCAG_NAMES: Dict[str, str] = {
    "1.1.1": "Non-text Content",
    "1.2.1": "Audio-only and Video-only (Prerecorded)",
    "1.2.2": "Captions (Prerecorded)",
    "1.2.3": "Audio Description or Media Alternative (Prerecorded)",
    "1.3.1": "Info and Relationships",
    "1.3.2": "Meaningful Sequence",
    "1.3.3": "Sensory Characteristics",
    "1.4.1": "Use of Color",
    "1.4.2": "Audio Control",
    "2.1.1": "Keyboard",
    "2.1.2": "No Keyboard Trap",
    "2.1.4": "Character Key Shortcuts",
    "2.2.1": "Timing Adjustable",
    "2.2.2": "Pause, Stop, Hide",
    "2.3.1": "Three Flashes or Below Threshold",
    "2.4.1": "Bypass Blocks",
    "2.4.2": "Page Titled",
    "2.4.3": "Focus Order",
    "2.4.4": "Link Purpose (In Context)",
    "2.5.1": "Pointer Gestures",
    "2.5.2": "Pointer Cancellation",
    "2.5.3": "Label in Name",
    "2.5.4": "Motion Actuation",
    "3.1.1": "Language of Page",
    "3.2.1": "On Focus",
    "3.2.2": "On Input",
    "3.3.1": "Error Identification",
    "3.3.2": "Labels or Instructions",
    "3.3.7": "Redundant Entry",
    "4.1.1": "Parsing",
    "4.1.2": "Name, Role, Value",
    "1.2.4": "Captions (Live)",
    "1.2.5": "Audio Description (Prerecorded)",
    "1.3.4": "Orientation",
    "1.3.5": "Identify Input Purpose",
    "1.4.3": "Contrast (Minimum)",
    "1.4.4": "Resize Text",
    "1.4.5": "Images of Text",
    "1.4.10": "Reflow",
    "1.4.11": "Non-text Contrast",
    "1.4.12": "Text Spacing",
    "1.4.13": "Content on Hover or Focus",
    "2.4.5": "Multiple Ways",
    "2.4.6": "Headings and Labels",
    "2.4.7": "Focus Visible",
    "2.4.11": "Focus Not Obscured (Minimum)",
    "2.4.13": "Focus Appearance",
    "2.5.7": "Dragging Movements",
    "2.5.8": "Target Size (Minimum)",
    "3.1.2": "Language of Parts",
    "3.2.3": "Consistent Navigation",
    "3.2.4": "Consistent Identification",
    "3.2.6": "Consistent Help",
    "3.3.3": "Error Suggestion",
    "3.3.4": "Error Prevention (Legal, Financial, Data)",
    "3.3.8": "Accessible Authentication (Minimum)",
    "4.1.3": "Status Messages",
}

_WCAG_LEVEL: Dict[str, str] = {
    "1.1.1": "A",
    "1.2.1": "A",
    "1.2.2": "A",
    "1.2.3": "A",
    "1.3.1": "A",
    "1.3.2": "A",
    "1.3.3": "A",
    "1.4.1": "A",
    "1.4.2": "A",
    "2.1.1": "A",
    "2.1.2": "A",
    "2.1.4": "A",
    "2.2.1": "A",
    "2.2.2": "A",
    "2.3.1": "A",
    "2.4.1": "A",
    "2.4.2": "A",
    "2.4.3": "A",
    "2.4.4": "A",
    "2.5.1": "A",
    "2.5.2": "A",
    "2.5.3": "A",
    "2.5.4": "A",
    "3.1.1": "A",
    "3.2.1": "A",
    "3.2.2": "A",
    "3.3.1": "A",
    "3.3.2": "A",
    "3.3.7": "A",
    "4.1.1": "A",
    "4.1.2": "A",
    "1.2.4": "AA",
    "1.2.5": "AA",
    "1.3.4": "AA",
    "1.3.5": "AA",
    "1.4.3": "AA",
    "1.4.4": "AA",
    "1.4.5": "AA",
    "1.4.10": "AA",
    "1.4.11": "AA",
    "1.4.12": "AA",
    "1.4.13": "AA",
    "2.4.5": "AA",
    "2.4.6": "AA",
    "2.4.7": "AA",
    "2.4.11": "AA",
    "2.4.13": "AA",
    "2.5.7": "AA",
    "2.5.8": "AA",
    "3.1.2": "AA",
    "3.2.3": "AA",
    "3.2.4": "AA",
    "3.2.6": "AA",
    "3.3.3": "AA",
    "3.3.4": "AA",
    "3.3.8": "AA",
    "4.1.3": "AA",
}

_SUGGESTED_FIX: Dict[str, str] = {
    "1.1.1": "Add a descriptive alt attribute: <img alt='Description'>. For decorative images use alt=''.",
    "1.3.1": "Use semantic HTML (headings, lists, tables). Add appropriate ARIA landmark roles where needed.",
    "1.3.5": "Add autocomplete attributes to inputs: <input autocomplete='email'>.",
    "1.4.1": "Do not use colour as the only means to convey information. Add text labels or patterns.",
    "1.4.2": "Provide a mechanism to pause or stop auto-playing audio, or ensure it stops within 3 seconds.",
    "1.4.3": "Ensure text has a contrast ratio of at least 4.5:1 (3:1 for large text ≥ 18pt or bold 14pt).",
    "1.4.4": "Remove CSS that blocks zoom. Content must reflow at 200% without horizontal scrolling.",
    "1.4.11": "Ensure UI components have at least 3:1 contrast ratio against adjacent colours.",
    "1.4.12": "Do not prevent line-height, letter-spacing, or word-spacing CSS overrides.",
    "2.1.1": "Ensure all functionality is operable via keyboard. Avoid onclick-only handlers and positive tabindex.",
    "2.1.2": "Allow keyboard users to move focus away from any component without requiring unusual key sequences.",
    "2.2.2": "Add a visible Pause/Stop button for any auto-playing content lasting more than 5 seconds.",
    "2.4.1": "Add a skip link as the first focusable element: <a href='#main'>Skip to main content</a>.",
    "2.4.2": "Add a descriptive <title>: <title>Page Name — Site Name</title>.",
    "2.4.3": "Ensure focus order follows a logical reading order. Remove positive tabindex values.",
    "2.4.4": "Replace generic link text ('Click here', 'Read more') with descriptive destination text.",
    "2.4.6": "Use heading levels (h1–h6) hierarchically. Provide visible labels for form groups.",
    "2.4.7": "Ensure all focusable elements have a clearly visible focus indicator (outline or border).",
    "2.5.3": "Ensure the accessible name (aria-label) contains the visible label text verbatim.",
    "2.5.8": "Increase the target to at least 24×24 CSS px, or add padding to reach that size.",
    "3.1.1": "Add a lang attribute to <html>: <html lang='en'>.",
    "3.1.2": "Add lang to inline content in another language: <span lang='fr'>Bonjour</span>.",
    "3.2.3": "Keep navigation menus in the same order across all pages.",
    "3.3.1": "Associate error messages with inputs using aria-describedby or aria-errormessage.",
    "3.3.2": "Add a visible <label> or aria-label to every form input. Do not rely on placeholder text alone.",
    "4.1.1": "Remove duplicate id attributes — each id must be unique within a page.",
    "4.1.2": "Give every interactive element an accessible name, role, and value using native HTML or ARIA.",
    "4.1.3": "Wrap status messages in a live region: <div role='status' aria-live='polite'>...</div>.",
}

# Python-auditor severity by WCAG SC
_PYTHON_SEVERITY: Dict[str, str] = {
    "1.1.1": "critical",
    "2.2.2": "high",
    "2.5.3": "high",
    "2.5.8": "medium",
    "3.3.1": "high",
    "3.3.2": "high",
}


# ── Request / Response models ──────────────────────────────────────────────────


class CombinedRequest(BaseModel):
    url: HttpUrl
    node_base_url: str = os.getenv("NODE_BASE_URL", "http://localhost:3000")
    max_depth: int = 0
    run_ocr: bool = True
    run_image_audit: bool = True
    run_form_audit: bool = True
    run_label_in_name_audit: bool = True
    run_pause_stop_hide_audit: bool = True
    run_target_size_audit: bool = True


class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # pending | running | completed | failed
    url: str
    submitted_at: str
    completed_at: Optional[str] = None
    report_path: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ── Node caller ───────────────────────────────────────────────────────────────


async def _call_node_flat(url: str, node_base_url: str) -> List[Dict]:
    """
    POST to Node's /api/v1/analyse-url-flat.
    Returns a flat list of element-wise findings:
      [{ source, rule_id, wcag_sc, criterion_name, level, severity,
         status, reason, suggested_fix, help_url, element }, ...]
    """
    endpoint = f"{node_base_url.rstrip('/')}/api/v1/analyse-url-flat"
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(endpoint, json={"url": url})
        resp.raise_for_status()
        return resp.json().get("findings", [])


# ── Python pipeline → flat findings ───────────────────────────────────────────


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
    return {
        "source": source,
        "rule_id": rule_id,
        "wcag_sc": wcag_sc,
        "criterion_name": _WCAG_NAMES.get(wcag_sc),
        "level": _WCAG_LEVEL.get(wcag_sc),
        "severity": severity if status != "pass" else None,
        "status": status,
        "reason": reason,
        "suggested_fix": _SUGGESTED_FIX.get(wcag_sc) if status != "pass" else None,
        "help_url": None,
        "element": (
            {
                "html": element_html[:600],
                "element_id": element_id,
                "tag": element_tag,
                "page_url": page_url,
            }
            if status != "pass"
            else None
        ),
    }


def _alt_text_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
    findings = []
    for r in records:
        status_raw = r.get("wcag_1_1_1_status", "")
        violation = r.get("wcag_1_1_1_violation", "")
        html = r.get("html_snippet", "")
        src = r.get("src", "") or ""

        if status_raw == "FAILED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_1_1_alt",
                    wcag_sc="1.1.1",
                    status="fail",
                    reason=violation or "Image missing adequate alt text.",
                    severity=_PYTHON_SEVERITY["1.1.1"],
                    element_html=html,
                    element_id=None,
                    element_tag="IMG",
                    page_url=page_url,
                )
            )
        elif status_raw == "PASSED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_1_1_alt",
                    wcag_sc="1.1.1",
                    status="pass",
                    reason="Image has adequate alt text.",
                    severity=None,
                    page_url=page_url,
                )
            )
    return findings


def _form_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
    findings = []
    for r in records:
        html = r.get("html_snippet", "")
        tag = r.get("tag", "INPUT")
        eid = r.get("element_id") or r.get("element_name")

        for sc, key in [("3.3.1", "wcag_3_3_1_status"), ("3.3.2", "wcag_3_3_2_status")]:
            viol_key = key.replace("_status", "_violation")
            status_raw = r.get(key, "")
            violation = r.get(viol_key, "")

            if status_raw == "FAILED":
                findings.append(
                    _make_finding(
                        source="python",
                        rule_id=f"python_{sc.replace('.','_')}",
                        wcag_sc=sc,
                        status="fail",
                        reason=violation or f"Form field violates WCAG {sc}.",
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
                        rule_id=f"python_{sc.replace('.','_')}",
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
        html = r.get("html_snippet", "")
        eid = r.get("element_id") or None
        tag = r.get("tag", "")
        violation = r.get("wcag_2_5_3_violation", "")

        if status_raw == "FAILED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_2_5_3_label_in_name",
                    wcag_sc="2.5.3",
                    status="fail",
                    reason=violation
                    or "Accessible name does not contain visible label.",
                    severity=_PYTHON_SEVERITY["2.5.3"],
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
        violation = r.get("wcag_2_2_2_violation", "")
        html = r.get("html_snippet", "")
        tag = r.get("tag", "")
        eid = r.get("element_id") or None

        if status_raw == "FAILED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_2_2_2_pause_stop_hide",
                    wcag_sc="2.2.2",
                    status="fail",
                    reason=violation
                    or "Auto-playing content has no pause/stop mechanism.",
                    severity=_PYTHON_SEVERITY["2.2.2"],
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
        violation = r.get("wcag_2_5_8_violation", "")
        html = r.get("html_snippet", "")
        tag = r.get("tag", "")
        eid = r.get("element_id") or None
        w = r.get("rendered_width_px", 0)
        h = r.get("rendered_height_px", 0)

        if status_raw == "FAILED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_2_5_8_target_size",
                    wcag_sc="2.5.8",
                    status="fail",
                    reason=violation
                    or f"Target size {w:.0f}×{h:.0f} px is below 24×24 px minimum.",
                    severity=_PYTHON_SEVERITY["2.5.8"],
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
                    rule_id="python_2_5_8_target_size",
                    wcag_sc="2.5.8",
                    status="pass",
                    reason=f"Target size {w:.0f}×{h:.0f} px meets the 24×24 px minimum.",
                    severity=None,
                    page_url=page_url,
                )
            )
    return findings


async def _run_python_pipeline(
    url: str,
    output_dir: Path,
    max_depth: int,
    run_ocr: bool,
    run_image_audit: bool,
    run_form_audit: bool,
    run_label_in_name_audit: bool,
    run_pause_stop_hide_audit: bool,
    run_target_size_audit: bool,
) -> List[Dict[str, Any]]:
    """Run all Python auditors; return flat element-wise findings list."""
    all_findings: List[Dict] = []

    # ── 1.1.1 image / alt-text ────────────────────────────────────────────
    image_crawler = AsyncImageCrawler(base_url=url, max_depth=max_depth)
    await image_crawler.crawl_page()
    image_crawler.save_results()

    ocr_results: list = []
    if run_ocr:
        detector = OCRPreprocessing(source_directory=image_crawler.output_dir)
        detector.scan_directory()
        saver = TextClassification(source_directory=image_crawler.output_dir)
        saver.results = detector.results
        saver.save_reports()
        ocr_results = detector.results

    if run_image_audit:
        auditor = AltTextAccessibilityAuditor()
        records = auditor.generate_audit_report(
            images_data=image_crawler.images_data,
            ocr_results=ocr_results,
            output_dir=image_crawler.output_dir,
        )
        all_findings.extend(_alt_text_to_findings(records, url))

    # ── 3.3.1 / 3.3.2 form audit ──────────────────────────────────────────
    form_crawler = AsyncFormCrawler(
        base_url=url,
        output_dir=str(output_dir),
        max_depth=max_depth,
    )
    form_inputs = await form_crawler.crawl()
    form_crawler.save_raw_json()

    if run_form_audit:
        form_auditor = FormAccessibilityAuditor(output_dir=str(output_dir))
        records = form_auditor.generate_audit_report(form_inputs=form_inputs)
        all_findings.extend(_form_to_findings(records, url))

    # ── 2.5.3 label-in-name ───────────────────────────────────────────────
    interactive_crawler = InteractiveElementCrawler(
        base_url=url,
        output_dir=str(output_dir),
        max_depth=max_depth,
    )
    interactive_elements = await interactive_crawler.crawl()
    interactive_crawler.save_raw_json()

    if run_label_in_name_audit:
        lin_auditor = LabelInNameAuditor(output_dir=str(output_dir))
        records = lin_auditor.generate_audit_report(interactive_elements)
        all_findings.extend(_lin_to_findings(records, url))

    # ── 2.2.2 pause-stop-hide ─────────────────────────────────────────────
    moving_crawler = MovingContentCrawler(
        base_url=url,
        output_dir=str(output_dir),
        max_depth=max_depth,
    )
    moving_items = await moving_crawler.crawl()
    moving_crawler.save_raw_json()

    if run_pause_stop_hide_audit:
        psh_auditor = PauseStopHideAuditor(output_dir=str(output_dir))
        records = psh_auditor.generate_audit_report(moving_items)
        all_findings.extend(_psh_to_findings(records, url))

    # ── 2.5.8 target size ─────────────────────────────────────────────────
    ts_crawler = TargetSizeCrawler(
        base_url=url,
        output_dir=str(output_dir),
        max_depth=max_depth,
    )
    ts_items = await ts_crawler.crawl()
    ts_crawler.save_raw_json()

    if run_target_size_audit:
        ts_auditor = TargetSizeAuditor(output_dir=str(output_dir))
        records = ts_auditor.generate_audit_report(ts_items)
        all_findings.extend(_ts_to_findings(records, url))

    return all_findings


# ── Report builder ────────────────────────────────────────────────────────────


def _build_report(url: str, all_findings: List[Dict]) -> Dict[str, Any]:
    """Merge axe + Python flat findings into the final combined report."""

    violations = [f for f in all_findings if f["status"] == "fail"]
    needs_review = [f for f in all_findings if f["status"] == "needs_review"]
    passes = [f for f in all_findings if f["status"] == "pass"]

    # ── by_severity ──────────────────────────────────────────────────────
    sev_count: Dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in violations + needs_review:
        sev = f.get("severity")
        if sev in sev_count:
            sev_count[sev] += 1

    # ── by_level ─────────────────────────────────────────────────────────
    level_count: Dict[str, Dict] = {}
    for f in all_findings:
        lv = f.get("level") or "unknown"
        if lv not in level_count:
            level_count[lv] = {"violations": 0, "needs_review": 0, "passes": 0}
        if f["status"] == "fail":
            level_count[lv]["violations"] += 1
        elif f["status"] == "needs_review":
            level_count[lv]["needs_review"] += 1
        else:
            level_count[lv]["passes"] += 1

    # ── by_wcag_sc ────────────────────────────────────────────────────────
    sc_count: Dict[str, Dict] = {}
    for f in all_findings:
        sc = f.get("wcag_sc") or "unknown"
        if sc not in sc_count:
            sc_count[sc] = {"violations": 0, "needs_review": 0, "passes": 0}
        if f["status"] == "fail":
            sc_count[sc]["violations"] += 1
        elif f["status"] == "needs_review":
            sc_count[sc]["needs_review"] += 1
        else:
            sc_count[sc]["passes"] += 1

    # ── by_source ─────────────────────────────────────────────────────────
    src_count: Dict[str, Dict] = {}
    for f in all_findings:
        src = f.get("source", "unknown")
        if src not in src_count:
            src_count[src] = {"violations": 0, "needs_review": 0, "passes": 0}
        if f["status"] == "fail":
            src_count[src]["violations"] += 1
        elif f["status"] == "needs_review":
            src_count[src]["needs_review"] += 1
        else:
            src_count[src]["passes"] += 1

    return {
        "url": url,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_findings": len(all_findings),
            "violations": len(violations),
            "needs_review": len(needs_review),
            "passes": len(passes),
            "by_severity": sev_count,
            "by_level": level_count,
            "by_wcag_sc": sc_count,
            "by_source": src_count,
        },
        "violations": violations,
        "needs_review": needs_review,
        "passes": passes,
    }


# ── Async job runner ───────────────────────────────────────────────────────────


async def _run_job(job_id: str, payload: CombinedRequest) -> None:
    """Background task: runs Python + Node concurrently, builds and saves report."""
    _jobs[job_id]["status"] = "running"
    url = str(payload.url)

    config = load_config()
    domain = urlparse(url).netloc.replace("www.", "").replace(".", "_")
    ts = time.strftime("%m%d_%H%M")
    output_dir = Path(f"{config['input']['output_dir']}/{domain}_{ts}_combined")
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        node_task = asyncio.create_task(_call_node_flat(url, payload.node_base_url))
        python_task = asyncio.create_task(
            _run_python_pipeline(
                url=url,
                output_dir=output_dir,
                max_depth=payload.max_depth,
                run_ocr=payload.run_ocr,
                run_image_audit=payload.run_image_audit,
                run_form_audit=payload.run_form_audit,
                run_label_in_name_audit=payload.run_label_in_name_audit,
                run_pause_stop_hide_audit=payload.run_pause_stop_hide_audit,
                run_target_size_audit=payload.run_target_size_audit,
            )
        )

        node_findings, python_findings = await asyncio.gather(node_task, python_task)

        # Merge: violations first, then needs_review, then passes
        all_findings = node_findings + python_findings
        all_findings.sort(
            key=lambda f: {"fail": 0, "needs_review": 1, "pass": 2}.get(f["status"], 3)
        )

        report = _build_report(url, all_findings)

        # Write combined_report.json
        report_path = output_dir / "combined_report.json"
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)

        _jobs[job_id].update(
            {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "report_path": str(report_path),
                "result": report,
            }
        )
        logger.info(
            f"[combined] job {job_id} completed — "
            f"{report['summary']['violations']} violations, "
            f"{report['summary']['needs_review']} needs_review, "
            f"{report['summary']['passes']} passes | "
            f"report → {report_path}"
        )

    except Exception as exc:
        logger.error(f"[combined] job {job_id} failed: {exc}")
        _jobs[job_id].update(
            {
                "status": "failed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error": str(exc),
            }
        )


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.post("/", response_model=JobStatusResponse, status_code=202)
async def submit_combined_audit(payload: CombinedRequest):
    """
    Submit a combined Python + Node axe-core accessibility audit.

    Returns `job_id` immediately (HTTP 202). Poll **GET /api/v1/combined/{job_id}**
    for status and the full report.

    **`result.violations`** — flat list of failing elements, each with:
    - `source` ("axe" | "python"), `rule_id`, `wcag_sc`, `criterion_name`, `level`
    - `severity` (critical / high / medium / low)
    - `reason` — why the element failed
    - `suggested_fix` — static remediation hint
    - `element` — `{ html, element_id, tag, page_url }`

    **`result.needs_review`** — same shape; manual verification required.

    **`result.passes`** — rule-level (not element-level) passing checks.

    **`result.summary`** — totals broken down by severity, level, WCAG SC, and source.

    The full report is also saved as `combined_report.json` in the output directory.
    """
    job_id = str(uuid.uuid4())
    url = str(payload.url)
    now = datetime.now(timezone.utc).isoformat()

    _jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "url": url,
        "submitted_at": now,
        "completed_at": None,
        "report_path": None,
        "result": None,
        "error": None,
    }

    asyncio.create_task(_run_job(job_id, payload))
    logger.info(f"[combined] job {job_id} submitted for {url}")
    return _jobs[job_id]


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_combined_audit(job_id: str):
    """
    Poll the status or retrieve the result of a combined audit job.

    - **pending**   — queued, not yet started
    - **running**   — Python + Node auditors executing
    - **completed** — `result` populated, `report_path` points to `combined_report.json`
    - **failed**    — `error` contains the exception message
    """
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    return job
