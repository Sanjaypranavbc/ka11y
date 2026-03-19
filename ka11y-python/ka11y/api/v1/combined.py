"""
ka11y/api/v1/combined.py
========================
Async combined audit — Python auditors + Node axe-core running in parallel.

ENDPOINTS
─────────
  POST /combined/                 202  { job_id, status, url, submitted_at }
  GET  /combined/{job_id}          200  Full job status + result once completed
  GET  /combined/{job_id}/stream   200  Server-Sent Events stream (text/event-stream)

JOB LIFECYCLE
─────────────
  submitted → pending → running → completed
                                ↘ failed (only when every stage errors out)

  Graceful degradation: if the axe-core (Node) stage fails but Python stages
  succeed, the job still completes. The report includes a `warnings` list
  noting which sources were unavailable.

STAGE ORDER & NAMES
───────────────────
  axe_core        Node / axe-core WCAG scan (runs in parallel with Python stages)
  image_audit     Crawl images → OCR → 1.1.1 alt-text check
  form_audit      Crawl forms → 3.3.1 / 3.3.2 label / error checks
  label_in_name   Crawl interactive elements → 2.5.3 check
  pause_stop_hide Crawl moving content → 2.2.2 check
  target_size     Crawl touch targets → 2.5.8 size check

SSE EVENT SCHEMA
────────────────
  All events arrive as:
    event: <event_type>
    data: <json>

  Event types:
    stage_start     { stage_name: str, started_at: str }
    stage_complete  { stage_name: str, completed_at: str, findings_count: int }
    stage_error     { stage_name: str, error: str }
    job_state       { current_stage: str, stages: list }   (sent on late connect)
    job_complete    { job_id: str, summary: dict }
    job_failed      { job_id: str, error: str }

  Heartbeat comment lines (": keepalive") are sent every 25 s to keep the
  connection alive through proxies that would otherwise time out.

OUTPUT FORMAT
─────────────
  Every finding (violation / needs_review / pass) carries:
    source          "axe" | "python"
    rule_id         axe rule ID or internal Python rule key
    wcag_sc         e.g. "1.1.1"
    criterion_name  e.g. "Non-text Content"
    level           "A" | "AA" | "AAA"
    severity        "critical" | "high" | "medium" | "low" | null
    status          "fail" | "pass" | "needs_review"
    reason          human-readable explanation
    suggested_fix   static remediation hint (null for passes)
    element         { html, element_id, tag, page_url } | null

  Contrast findings (source="python", rule_id="python_1_4_3_contrast") also
  include an extra top-level key in the combined report:

    contrast_report {
        summary { total_regions_analysed, total_violations,
                  images_with_violations, pass_rate_pct }
        table   [ flat row per detected text region ]
        images  [ per-image nested detail ]
    }

HOW TO ADD A NEW PYTHON RULE
─────────────────────────────
Step 1 — Crawler  (ka11y/crawler/)
  • Write (or subclass) an async crawler with:
      async def crawl() -> List[Dict]   — one dict per detected element
      def save_raw_json()
  • Each dict may carry arbitrary keys; your auditor will consume them.

Step 2 — Auditor  (ka11y/accessibility/rules/<category>/)
  • Implement: generate_audit_report(items) -> List[Dict]
  • Each output record MUST include:
      <rule_key>_status    "FAILED" | "PASSED" | "N/A"
      <rule_key>_violation str  (ignored on PASSED / N/A)
      html_snippet         str
      element_id           str | None
      tag                  str

Step 3 — Finding converter  (add to this file)
  def _myrule_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
      findings = []
      for r in records:
          status_raw = r.get("mykey_status", "")
          if status_raw == "N/A":
              continue
          if status_raw == "FAILED":
              findings.append(_make_finding(
                  source="python", rule_id="python_X_X_X_myrule",
                  wcag_sc="X.X.X", status="fail",
                  reason=r.get("mykey_violation") or "Default reason.",
                  severity=_PYTHON_SEVERITY["X.X.X"],
                  element_html=r.get("html_snippet", ""),
                  element_id=r.get("element_id"),
                  element_tag=r.get("tag", ""),
                  page_url=page_url,
              ))
          elif status_raw == "PASSED":
              findings.append(_make_finding(
                  source="python", rule_id="python_X_X_X_myrule",
                  wcag_sc="X.X.X", status="pass",
                  reason="Element meets WCAG X.X.X.", severity=None,
                  page_url=page_url,
              ))
      return findings

Step 4 — Register severity & suggested fix
  • Add wcag_sc entry to _PYTHON_SEVERITY  (skip if already present)
  • Add wcag_sc entry to _SUGGESTED_FIX    (skip if already present)

Step 5 — Wire into _run_python_stages()
  Add a new stage block following the existing pattern:

      stage_findings: List[Dict] = []
      _stage_start(job_id, "my_stage_name")
      try:
          my_crawler = MyCrawler(
              base_url=url, output_dir=str(output_dir), max_depth=max_depth,
          )
          items = await my_crawler.crawl()
          my_crawler.save_raw_json()
          if run_my_audit:
              auditor = MyAuditor(output_dir=str(output_dir))
              records = auditor.generate_audit_report(items)
              stage_findings = _myrule_to_findings(records, url)
              all_findings.extend(stage_findings)
          _stage_complete(job_id, "my_stage_name", len(stage_findings))
      except Exception as _exc:
          _stage_error_and_warn(job_id, "my_stage_name", _exc)

Step 6 — Expose the toggle in CombinedRequest
  Add:  run_my_audit: bool = True
  Pass it through submit_combined_audit → _run_job → _run_python_stages.
"""

from __future__ import annotations

import asyncio
import functools
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
import mimetypes
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple
from urllib.parse import quote, urlparse

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
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


# ── In-memory stores ────────────────────────────────────────────────────────────
_jobs: Dict[str, Dict[str, Any]] = {}

# SSE subscriber bus: job_id → list of per-client asyncio.Queue
_subscribers: Dict[str, List[asyncio.Queue]] = {}
_subscribers_lock: asyncio.Lock = asyncio.Lock()  # guards _subscribers mutations

# TTL for completed/failed jobs (1 hour)
_JOB_TTL_SECONDS: int = 3600


# ── Static metadata ─────────────────────────────────────────────────────────────

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

_PYTHON_SEVERITY: Dict[str, str] = {
    "1.1.1": "critical",
    "1.4.3": "high",  # ← contrast (Minimum) — new
    "2.2.2": "high",
    "2.5.3": "high",
    "2.5.8": "medium",
    "3.3.1": "high",
    "3.3.2": "high",
}


# ── Request / Response models ────────────────────────────────────────────────────


class CombinedRequest(BaseModel):
    url: HttpUrl
    max_depth: int = 0
    wcag_level: str = "AA"  # "A" | "AA" | "AAA"
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
    current_stage: Optional[str] = None
    stages: List[Dict[str, Any]] = []
    warnings: List[str] = []


# ── SSE subscriber bus ───────────────────────────────────────────────────────────


def _broadcast(job_id: str, event_type: str, data: Dict[str, Any]) -> None:
    """Push an SSE event dict to every subscriber queue for this job."""
    msg = {"event": event_type, "data": data}
    # Read-only iteration — lock not required here since put_nowait is thread-safe
    for q in list(_subscribers.get(job_id, [])):
        q.put_nowait(msg)


def _close_subscribers(job_id: str) -> None:
    """Send sentinel None to all queues so their generators exit, then clean up."""
    for q in list(_subscribers.get(job_id, [])):
        q.put_nowait(None)
    _subscribers.pop(job_id, None)


async def _evict_old_jobs() -> None:
    """Background task: remove completed/failed jobs older than _JOB_TTL_SECONDS."""
    while True:
        await asyncio.sleep(300)  # run every 5 minutes
        cutoff = time.time() - _JOB_TTL_SECONDS
        expired = [
            jid
            for jid, job in list(_jobs.items())
            if job.get("status") in ("completed", "failed")
            and job.get("_created_at", 0) < cutoff
        ]
        for jid in expired:
            _jobs.pop(jid, None)
            _subscribers.pop(jid, None)
        if expired:
            logger.info(f"[combined] TTL eviction: removed {len(expired)} old jobs")


# ── Stage tracking helpers ───────────────────────────────────────────────────────


def _stage_start(job_id: str, name: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    rec = {"name": name, "status": "running", "started_at": now}
    job = _jobs[job_id]
    job["current_stage"] = name
    job.setdefault("stages", []).append(rec)
    _broadcast(job_id, "stage_start", {"stage_name": name, "started_at": now})


def _stage_complete(job_id: str, name: str, findings_count: int = 0) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for s in _jobs[job_id].get("stages", []):
        if s["name"] == name and s["status"] == "running":
            s.update(
                status="completed", completed_at=now, findings_count=findings_count
            )
            break
    _broadcast(
        job_id,
        "stage_complete",
        {
            "stage_name": name,
            "completed_at": now,
            "findings_count": findings_count,
        },
    )


def _stage_error(job_id: str, name: str, error: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for s in _jobs[job_id].get("stages", []):
        if s["name"] == name and s["status"] == "running":
            s.update(status="error", completed_at=now, error=error)
            break
    _broadcast(job_id, "stage_error", {"stage_name": name, "error": error})


def _stage_error_and_warn(job_id: str, name: str, exc: Exception) -> None:
    """Record a non-fatal stage failure: update stages, broadcast, log a warning."""
    msg = str(exc)
    logger.warning(f"[combined] {name} stage error: {msg}")
    _stage_error(job_id, name, msg)
    _jobs[job_id].setdefault("warnings", []).append(f"{name}: {msg}")


# ── WCAG level filter ────────────────────────────────────────────────────────────


def _allowed_levels(wcag_level: str) -> set:
    levels = {"A"}
    if wcag_level in ("AA", "AAA"):
        levels.add("AA")
    if wcag_level == "AAA":
        levels.add("AAA")
    return levels


# ── Node caller ──────────────────────────────────────────────────────────────────


async def _call_node_flat(
    url: str, node_base_url: str, wcag_level: str = "AA"
) -> List[Dict]:
    """
    POST to Node's /api/v1/analyse-url-flat.
    Returns a flat list of element-wise findings from axe-core.
    """
    endpoint = f"{node_base_url.rstrip('/')}/api/v1/analyse-url-flat"
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(endpoint, json={"url": url, "level": wcag_level})
        resp.raise_for_status()
        return resp.json().get("findings", [])


# ── Finding factory ──────────────────────────────────────────────────────────────


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


# ── Contrast report builder ──────────────────────────────────────────────────────


def _build_contrast_report(ocr_results: list) -> Dict[str, Any]:
    """
    Extract contrast data from OCR results into a structured report.

    Returns
    -------
    {
        "summary": {
            "total_regions_analysed": int,
            "total_violations":       int,
            "images_with_violations": int,
            "pass_rate_pct":          float,
        },
        "table": [          # one flat row per detected text region
            {
                "image":            str,
                "image_path":       str,
                "text":             str,
                "confidence":       float,
                "foreground_hex":   str | None,
                "foreground_lum":   float | None,
                "background_hex":   str | None,
                "background_lum":   float | None,
                "contrast_ratio":   float | None,
                "AA_normal":        bool | None,
                "AA_large":         bool | None,
                "AAA_normal":       bool | None,
                "AAA_large":        bool | None,
                "violations":       list[str],
            },
            ...
        ],
        "images": [         # per-image nested detail
            {
                "filename":                  str,
                "path":                      str,
                "contrast_violations_count": int,
                "detections": [ ... ],
            },
            ...
        ],
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
            aa_n = aa_l = aaa_n = aaa_l = None

            compliance = ci.get("compliance") or {}
            if compliance:
                ratio = compliance.get("contrast_ratio")
                aa_n = compliance.get("AA_normal")
                aa_l = compliance.get("AA_large")
                aaa_n = compliance.get("AAA_normal")
                aaa_l = compliance.get("AAA_large")

            fg = col.get("foreground") or {}
            bg_pal = col.get("background_palette") or []
            checks = col.get("contrast_checks") or []
            dominant_bg: Dict[str, Any] = bg_pal[0] if bg_pal else {}

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
                    "AA_normal": aa_n,
                    "AA_large": aa_l,
                    "AAA_normal": aaa_n,
                    "AAA_large": aaa_l,
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
                    "AA_normal": aa_n,
                    "AA_large": aa_l,
                    "AAA_normal": aaa_n,
                    "AAA_large": aaa_l,
                }
            )

        if image_has_violation:
            images_with_violations += 1

        if image_detections:
            images_detail.append(
                {
                    "filename": result.filename,
                    "path": result.original_path,
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


# ── Per-auditor finding converters ───────────────────────────────────────────────
# Each converter maps raw auditor records → flat finding dicts.
# Add a new converter here when adding a new Python rule (see HOW TO ADD A NEW RULE).


def _alt_text_to_findings(records: List[Dict], page_url: str) -> List[Dict]:
    findings = []
    for r in records:
        status_raw = r.get("wcag_1_1_1_status", "")
        if status_raw == "FAILED":
            findings.append(
                _make_finding(
                    source="python",
                    rule_id="python_1_1_1_alt",
                    wcag_sc="1.1.1",
                    status="fail",
                    reason=r.get("wcag_1_1_1_violation")
                    or "Image missing adequate alt text.",
                    severity=_PYTHON_SEVERITY["1.1.1"],
                    element_html=r.get("html_snippet", ""),
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


def _contrast_to_findings(ocr_results: list, page_url: str) -> List[Dict]:
    """
    Convert per-detection contrast data from OCR results into WCAG 1.4.3
    findings so they appear in the combined violations / passes lists
    alongside every other rule.

    Single source of truth: contrast_info["compliance"] from contrast_analyser,
    which is computed directly from pixel luminance. wcag_violations strings are
    NOT used here — they come from a separate cluster-based path in color_info
    and can disagree with contrast_info.

    Decision logic (requires contrast data to be present):
      - aa_normal is False  → fail  (ratio < 4.5:1)
      - aa_normal is True   → pass  (ratio >= 4.5:1)
      - aa_normal is None   → skip  (no contrast data available)
    """
    findings: List[Dict] = []

    for result in ocr_results:
        if not result.has_text:
            continue

        for det in result.detections:
            ci = det.contrast_info or {}
            col = det.color_info or {}

            # ── Single source of truth: contrast_analyser compliance dict ──────
            compliance = ci.get("compliance") or {}
            aa_normal = compliance.get("AA_normal")  # True | False | None
            ratio = compliance.get("contrast_ratio")

            # Skip entirely if we have no measured contrast data
            if aa_normal is None:
                logger.warning(
                    f"[combined] contrast_to_findings: no AA_normal for "
                    f'"{det.text[:40]!r}" in {result.filename} — skipping'
                )
                continue

            # ── Display metadata (for reason string and element snippet) ──────
            fg = col.get("foreground") or {}
            bg_pal = col.get("background_palette") or []
            dominant_bg = bg_pal[0] if bg_pal else {}

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
                # ratio < 4.5:1 — AA normal text contrast failure
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
                # ratio >= 4.5:1 — passes AA normal text contrast
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


# ── Per-stage coroutines (run concurrently via asyncio.gather) ───────────────
#
# Each coroutine owns its crawler + auditor lifecycle and reports its own
# stage_start / stage_complete / stage_error SSE events.
#
# CPU-bound auditor calls are offloaded to a thread pool via
# asyncio.to_thread() so they never block the event loop.


async def _stage_image_audit(
    url: str,
    output_dir: Path,
    max_depth: int,
    run_ocr: bool,
    run_image_audit: bool,
    job_id: str,
) -> Tuple[List[Dict], Optional[Dict[str, Any]]]:
    """Crawl images → OCR → 1.1.1 alt-text + 1.4.3 contrast."""
    _stage_start(job_id, "image_audit")
    try:
        image_crawler = AsyncImageCrawler(base_url=url, max_depth=max_depth)
        await image_crawler.crawl_page()
        await asyncio.to_thread(image_crawler.save_results)

        ocr_results: list = []
        contrast_report: Optional[Dict[str, Any]] = None
        findings: List[Dict] = []

        if run_ocr:
            detector = OCRPreprocessing(source_directory=image_crawler.output_dir)
            # Heavy CPU — EasyOCR + NumPy inference; must not block event loop
            await asyncio.to_thread(detector.scan_directory)

            saver = TextClassification(source_directory=image_crawler.output_dir)
            saver.results = detector.results
            await asyncio.to_thread(saver.save_reports)

            ocr_results = detector.results
            contrast_report = _build_contrast_report(ocr_results)
            findings.extend(_contrast_to_findings(ocr_results, url))

        if run_image_audit:
            auditor = AltTextAccessibilityAuditor()
            records = await asyncio.to_thread(
                auditor.generate_audit_report,
                images_data=image_crawler.images_data,
                ocr_results=ocr_results,
                output_dir=image_crawler.output_dir,
            )
            findings.extend(_alt_text_to_findings(records, url))

        _stage_complete(job_id, "image_audit", len(findings))
        return findings, contrast_report
    except Exception as _exc:
        _stage_error_and_warn(job_id, "image_audit", _exc)
        return [], None


async def _stage_form_audit(
    url: str,
    output_dir: Path,
    max_depth: int,
    run_form_audit: bool,
    job_id: str,
) -> List[Dict]:
    """Crawl forms → 3.3.1 / 3.3.2 label + error checks."""
    _stage_start(job_id, "form_audit")
    try:
        form_crawler = AsyncFormCrawler(
            base_url=url, output_dir=str(output_dir), max_depth=max_depth
        )
        form_inputs = await form_crawler.crawl()
        await asyncio.to_thread(form_crawler.save_raw_json)

        findings: List[Dict] = []
        if run_form_audit:
            form_auditor = FormAccessibilityAuditor(output_dir=str(output_dir))
            records = await asyncio.to_thread(
                functools.partial(
                    form_auditor.generate_audit_report, form_inputs=form_inputs
                )
            )
            findings = _form_to_findings(records, url)

        _stage_complete(job_id, "form_audit", len(findings))
        return findings
    except Exception as _exc:
        _stage_error_and_warn(job_id, "form_audit", _exc)
        return []


async def _stage_label_in_name(
    url: str,
    output_dir: Path,
    max_depth: int,
    run_label_in_name_audit: bool,
    job_id: str,
) -> List[Dict]:
    """Crawl interactive elements → 2.5.3 label-in-name check."""
    _stage_start(job_id, "label_in_name")
    try:
        interactive_crawler = InteractiveElementCrawler(
            base_url=url, output_dir=str(output_dir), max_depth=max_depth
        )
        interactive_elements = await interactive_crawler.crawl()
        await asyncio.to_thread(interactive_crawler.save_raw_json)

        findings: List[Dict] = []
        if run_label_in_name_audit:
            lin_auditor = LabelInNameAuditor(output_dir=str(output_dir))
            records = await asyncio.to_thread(
                lin_auditor.generate_audit_report, interactive_elements
            )
            findings = _lin_to_findings(records, url)

        _stage_complete(job_id, "label_in_name", len(findings))
        return findings
    except Exception as _exc:
        _stage_error_and_warn(job_id, "label_in_name", _exc)
        return []


async def _stage_pause_stop_hide(
    url: str,
    output_dir: Path,
    max_depth: int,
    run_pause_stop_hide_audit: bool,
    job_id: str,
) -> List[Dict]:
    """Crawl moving content → 2.2.2 pause/stop/hide check."""
    _stage_start(job_id, "pause_stop_hide")
    try:
        moving_crawler = MovingContentCrawler(
            base_url=url, output_dir=str(output_dir), max_depth=max_depth
        )
        moving_items = await moving_crawler.crawl()
        await asyncio.to_thread(moving_crawler.save_raw_json)

        findings: List[Dict] = []
        if run_pause_stop_hide_audit:
            psh_auditor = PauseStopHideAuditor(output_dir=str(output_dir))
            records = await asyncio.to_thread(
                psh_auditor.generate_audit_report, moving_items
            )
            findings = _psh_to_findings(records, url)

        _stage_complete(job_id, "pause_stop_hide", len(findings))
        return findings
    except Exception as _exc:
        _stage_error_and_warn(job_id, "pause_stop_hide", _exc)
        return []


async def _stage_target_size(
    url: str,
    output_dir: Path,
    max_depth: int,
    run_target_size_audit: bool,
    job_id: str,
) -> List[Dict]:
    """Crawl touch targets → 2.5.8 target-size check."""
    _stage_start(job_id, "target_size")
    try:
        ts_crawler = TargetSizeCrawler(
            base_url=url, output_dir=str(output_dir), max_depth=max_depth
        )
        ts_items = await ts_crawler.crawl()
        await asyncio.to_thread(ts_crawler.save_raw_json)

        findings: List[Dict] = []
        if run_target_size_audit:
            ts_auditor = TargetSizeAuditor(output_dir=str(output_dir))
            records = await asyncio.to_thread(
                ts_auditor.generate_audit_report, ts_items
            )
            findings = _ts_to_findings(records, url)

        _stage_complete(job_id, "target_size", len(findings))
        return findings
    except Exception as _exc:
        _stage_error_and_warn(job_id, "target_size", _exc)
        return []


# ── Python pipeline orchestrator ─────────────────────────────────────────────


async def _run_python_stages(
    *,
    url: str,
    output_dir: Path,
    max_depth: int,
    run_ocr: bool,
    run_image_audit: bool,
    run_form_audit: bool,
    run_label_in_name_audit: bool,
    run_pause_stop_hide_audit: bool,
    run_target_size_audit: bool,
    job_id: str,
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Run all 5 Python audit stages **concurrently**.

    Each stage crawls the target URL with its own browser instance and runs
    its auditor in a thread pool so CPU-bound work never blocks the event loop.

    Returns
    -------
    (all_findings, contrast_report)
    """
    results = await asyncio.gather(
        _stage_image_audit(
            url, output_dir, max_depth, run_ocr, run_image_audit, job_id
        ),
        _stage_form_audit(url, output_dir, max_depth, run_form_audit, job_id),
        _stage_label_in_name(
            url, output_dir, max_depth, run_label_in_name_audit, job_id
        ),
        _stage_pause_stop_hide(
            url, output_dir, max_depth, run_pause_stop_hide_audit, job_id
        ),
        _stage_target_size(
            url, output_dir, max_depth, run_target_size_audit, job_id
        ),
        return_exceptions=True,
    )

    all_findings: List[Dict] = []
    contrast_report: Optional[Dict[str, Any]] = None

    # Image audit returns (findings, contrast_report)
    img_result = results[0]
    if not isinstance(img_result, Exception):
        img_findings, contrast_report = img_result
        all_findings.extend(img_findings)

    # All other stages return a plain findings list
    for r in results[1:]:
        if not isinstance(r, Exception):
            all_findings.extend(r)

    return all_findings, contrast_report


# ── Report builder ───────────────────────────────────────────────────────────────


def _build_report(
    url: str,
    all_findings: List[Dict],
    contrast_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Merge axe + Python flat findings into the final combined report.

    The `contrast_report` key surfaces the full structured contrast analysis
    (summary, flat table, and per-image detail) alongside the flat findings.
    """
    violations = [f for f in all_findings if f["status"] == "fail"]
    needs_review = [f for f in all_findings if f["status"] == "needs_review"]
    passes = [f for f in all_findings if f["status"] == "pass"]

    sev_count: Dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in violations + needs_review:
        sev = f.get("severity")
        if sev in sev_count:
            sev_count[sev] += 1

    level_count: Dict[str, Dict] = {}
    sc_count: Dict[str, Dict] = {}
    src_count: Dict[str, Dict] = {}

    for f in all_findings:
        for bucket, key in [
            (level_count, f.get("level") or "unknown"),
            (sc_count, f.get("wcag_sc") or "unknown"),
            (src_count, f.get("source", "unknown")),
        ]:
            if key not in bucket:
                bucket[key] = {"violations": 0, "needs_review": 0, "passes": 0}
            if f["status"] == "fail":
                bucket[key]["violations"] += 1
            elif f["status"] == "needs_review":
                bucket[key]["needs_review"] += 1
            else:
                bucket[key]["passes"] += 1

    report: Dict[str, Any] = {
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
        # ── NEW: full structured contrast report ──────────────────────────
        "contrast_report": contrast_report,
    }
    return report


# ── Async job runner ─────────────────────────────────────────────────────────────


async def _run_job(job_id: str, payload: CombinedRequest) -> None:
    """
    Background task: run axe-core (Node) and Python stages in parallel.

    Graceful degradation:
    • Uses asyncio.gather(return_exceptions=True) so neither branch cancels the other.
    • If axe-core fails → Python-only report with a warning entry.
    • If a Python stage fails → other stages continue; warning entry added.
    • Job fails ONLY when both axe-core AND all Python stages return nothing.
    """
    _jobs[job_id]["status"] = "running"
    url = str(payload.url)

    config = load_config()
    node_base_url = os.getenv("NODE_BASE_URL", "http://localhost:3000")
    domain = urlparse(url).netloc.replace("www.", "").replace(".", "_")
    ts = time.strftime("%m%d_%H%M")
    output_dir = Path(f"{config['input']['output_dir']}/{domain}_{ts}_combined")
    output_dir.mkdir(parents=True, exist_ok=True)
    _jobs[job_id]["output_dir"] = str(output_dir)

    try:
        # Fire axe-core and all Python stages concurrently
        _stage_start(job_id, "axe_core")
        node_task = asyncio.create_task(
            _call_node_flat(url, node_base_url, payload.wcag_level)
        )
        python_task = asyncio.create_task(
            _run_python_stages(
                url=url,
                output_dir=output_dir,
                max_depth=payload.max_depth,
                run_ocr=payload.run_ocr,
                run_image_audit=payload.run_image_audit,
                run_form_audit=payload.run_form_audit,
                run_label_in_name_audit=payload.run_label_in_name_audit,
                run_pause_stop_hide_audit=payload.run_pause_stop_hide_audit,
                run_target_size_audit=payload.run_target_size_audit,
                job_id=job_id,
            )
        )

        node_result, python_result = await asyncio.gather(
            node_task, python_task, return_exceptions=True
        )

        # ── Resolve axe-core result ───────────────────────────────────────────
        if isinstance(node_result, Exception):
            _stage_error_and_warn(job_id, "axe_core", node_result)
            node_findings: List[Dict] = []
        else:
            node_findings = node_result
            _stage_complete(job_id, "axe_core", len(node_findings))

        # ── Resolve Python result ─────────────────────────────────────────────
        python_findings: List[Dict] = []
        contrast_report: Optional[Dict[str, Any]] = None

        if isinstance(python_result, Exception):
            pass  # all stages failed — warnings already recorded
        else:
            python_findings, contrast_report = python_result

        if not node_findings and not python_findings:
            raise RuntimeError(
                "All audit sources failed — no findings could be collected. "
                "Check warnings for details."
            )

        # Filter Python findings to the requested WCAG level
        allowed = _allowed_levels(payload.wcag_level)
        python_findings = [
            f
            for f in python_findings
            if f.get("level") in allowed or f.get("level") is None
        ]

        all_findings = node_findings + python_findings
        all_findings.sort(
            key=lambda f: {"fail": 0, "needs_review": 1, "pass": 2}.get(f["status"], 3)
        )

        report = _build_report(url, all_findings, contrast_report=contrast_report)
        report["warnings"] = _jobs[job_id].get("warnings", [])

        # Inject image_url into each contrast-report image so the frontend
        # can render the image directly without constructing the URL itself.
        if report.get("contrast_report"):
            for img in report["contrast_report"].get("images", []):
                img["image_url"] = (
                    f"/api/v1/combined/{job_id}/image"
                    f"?path={quote(img['path'], safe='')}"
                )

        report_path = output_dir / "combined_report.json"
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)

        _jobs[job_id].update(
            {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "report_path": str(report_path),
                "result": report,
                "current_stage": None,
            }
        )

        logger.info(
            f"[combined] job {job_id} completed — "
            f"{report['summary']['violations']} violations, "
            f"{report['summary']['needs_review']} needs_review, "
            f"{report['summary']['passes']} passes | "
            f"contrast regions: {(contrast_report or {}).get('summary', {}).get('total_regions_analysed', 0)} | "
            f"report → {report_path}"
        )

        _broadcast(
            job_id,
            "job_complete",
            {
                "job_id": job_id,
                "summary": report["summary"],
            },
        )

    except Exception as exc:
        logger.error(f"[combined] job {job_id} failed: {exc}")
        _jobs[job_id].update(
            {
                "status": "failed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error": str(exc),
                "current_stage": None,
            }
        )
        _broadcast(job_id, "job_failed", {"job_id": job_id, "error": str(exc)})

    finally:
        _close_subscribers(job_id)


# ── Routes ───────────────────────────────────────────────────────────────────────


@router.post("/", response_model=JobStatusResponse, status_code=202)
async def submit_combined_audit(payload: CombinedRequest):
    """
    Submit a combined Python + Node axe-core accessibility audit.

    Returns `job_id` immediately (HTTP 202). Poll **GET /api/v1/combined/{job_id}**
    for status and the full report, or connect to
    **GET /api/v1/combined/{job_id}/stream** for real-time SSE stage events.

    **Graceful degradation**: if Node/axe-core is unavailable the job still
    completes using Python-only findings; a `warnings` list notes the failure.

    The completed result includes a `contrast_report` key with:
    - `summary`  — aggregate counts and pass-rate
    - `table`    — one flat row per detected text region (suitable for CSV/table display)
    - `images`   — per-image nested detail with full palette and compliance data
    """
    job_id = str(uuid.uuid4())
    url = str(payload.url)
    now = datetime.now(timezone.utc).isoformat()

    # SSRF guard: reject private / loopback / link-local URLs
    _parsed = urlparse(url)
    _host = _parsed.hostname or ""
    _PRIVATE_PREFIXES = ("localhost", "127.", "10.", "192.168.", "169.254.")
    if _host == "localhost" or any(_host.startswith(p) for p in _PRIVATE_PREFIXES):
        raise HTTPException(
            status_code=400,
            detail=f"URL hostname '{_host}' is not allowed (private/loopback address).",
        )

    _jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "url": url,
        "submitted_at": now,
        "_created_at": time.time(),
        "completed_at": None,
        "report_path": None,
        "result": None,
        "error": None,
        "current_stage": None,
        "stages": [],
        "warnings": [],
    }

    asyncio.create_task(_run_job(job_id, payload))
    logger.info(f"[combined] job {job_id} submitted for {url}")
    return _jobs[job_id]


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_combined_audit(job_id: str):
    """
    Poll the status or retrieve the result of a combined audit job.

    - **pending**   — queued, not yet started
    - **running**   — stages executing (`current_stage` shows active stage)
    - **completed** — `result` populated; `warnings` lists any non-fatal failures
    - **failed**    — `error` contains the root-cause message

    When completed, `result.contrast_report` contains the full contrast analysis:
    - `summary`  — counts and pass-rate across all detected text regions
    - `table`    — flat list of rows, one per text region (image, text, fg/bg hex,
                   ratio, AA_normal, AA_large, AAA_normal, AAA_large, violations)
    - `images`   — per-image nested detail with full palette and contrast checks
    """
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    return job


@router.get("/{job_id}/image")
async def get_job_image(job_id: str, path: str):
    """
    Serve an image file belonging to a completed audit job.

    The ``path`` query parameter must exactly match one of the image paths
    recorded in ``result.contrast_report.images`` for the given job — any
    other path is rejected with 403 to prevent directory traversal.

    Example:
        GET /api/v1/combined/<job_id>/image?path=/tmp/output/img.png
    """
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")

    # Whitelist: only serve paths that appear in this job's contrast report
    result = job.get("result") or {}
    contrast_report = result.get("contrast_report") or {}
    valid_paths = {img["path"] for img in contrast_report.get("images", [])}

    if path not in valid_paths:
        raise HTTPException(
            status_code=403,
            detail="Image path is not associated with this job.",
        )

    img_path = Path(path)
    if not img_path.exists() or not img_path.is_file():
        raise HTTPException(status_code=404, detail="Image file not found on server.")

    media_type, _ = mimetypes.guess_type(str(img_path))
    return FileResponse(str(img_path), media_type=media_type or "image/png")


@router.get("/{job_id}/stream")
async def stream_combined_audit(job_id: str):
    """
    Server-Sent Events stream for a combined audit job.

    Connect immediately after submitting to receive real-time stage progress.
    If the job has already completed or failed when you connect, a single
    terminal event is sent and the stream closes.

    Events: stage_start | stage_complete | stage_error | job_state |
            job_complete | job_failed
    Heartbeat: ': keepalive' comment lines every 25 s.
    """
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")

    q: asyncio.Queue = asyncio.Queue()
    async with _subscribers_lock:
        _subscribers.setdefault(job_id, []).append(q)

    async def generator() -> AsyncGenerator[str, None]:
        try:
            current = _jobs.get(job_id, {})

            # If job already finished, send the terminal event immediately
            if current.get("status") == "completed":
                result = current.get("result", {})
                yield (
                    f"event: job_complete\n"
                    f"data: {json.dumps({'job_id': job_id, 'summary': result.get('summary', {})})}\n\n"
                )
                return
            if current.get("status") == "failed":
                yield (
                    f"event: job_failed\n"
                    f"data: {json.dumps({'job_id': job_id, 'error': current.get('error', '')})}\n\n"
                )
                return

            # Send current running state for late-connecting clients
            if current.get("current_stage") or current.get("stages"):
                yield (
                    f"event: job_state\n"
                    f"data: {json.dumps({'current_stage': current.get('current_stage'), 'stages': current.get('stages', [])})}\n\n"
                )

            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=25.0)
                    if msg is None:  # sentinel — job reached terminal state
                        break
                    yield f"event: {msg['event']}\ndata: {json.dumps(msg['data'])}\n\n"
                    if msg["event"] in ("job_complete", "job_failed"):
                        break
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"  # prevent proxy timeout
        finally:
            async with _subscribers_lock:
                subs = _subscribers.get(job_id, [])
                if q in subs:
                    subs.remove(q)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx output buffering for SSE
        },
    )
