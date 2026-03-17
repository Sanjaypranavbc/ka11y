"""
ka11y/api/v1/combined.py
========================
Async combined audit endpoint — runs Python auditors + Node axe-core in parallel.

  POST /combined/          → 202 { job_id, status: "pending", ... }
  GET  /combined/{job_id} → job status / result

The job fires asyncio.gather() over:
  - Node  : POST /api/v1/analyse-url  (Puppeteer + axe-core)
  - Python: all configured auditors   (Playwright crawlers)

Results are merged side-by-side per WCAG Success Criterion (Q1=a).
axe "incomplete" items appear in a separate "needs_review" bucket (Q2=a).
"""

import asyncio
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
from ka11y.accessibility.rules.input_modalities.label_in_name_auditor import LabelInNameAuditor
from ka11y.accessibility.rules.input_modalities.target_size_auditor import TargetSizeAuditor
from ka11y.accessibility.rules.timing.pause_stop_hide_auditor import PauseStopHideAuditor
from ka11y.config.logger import setup_logger
from ka11y.utils.config_loader import load_config

router = APIRouter(prefix="/combined", tags=["combined"])
logger = setup_logger(name="KAC", tag="combined")

# ── In-memory job store ────────────────────────────────────────────────────────
_jobs: Dict[str, Dict[str, Any]] = {}


# ── WCAG 2.2 metadata ──────────────────────────────────────────────────────────

_WCAG_NAMES: Dict[str, str] = {
    # A
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
    # AA
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
    "1.1.1": "A",  "1.2.1": "A",  "1.2.2": "A",  "1.2.3": "A",
    "1.3.1": "A",  "1.3.2": "A",  "1.3.3": "A",
    "1.4.1": "A",  "1.4.2": "A",
    "2.1.1": "A",  "2.1.2": "A",  "2.1.4": "A",
    "2.2.1": "A",  "2.2.2": "A",
    "2.3.1": "A",
    "2.4.1": "A",  "2.4.2": "A",  "2.4.3": "A",  "2.4.4": "A",
    "2.5.1": "A",  "2.5.2": "A",  "2.5.3": "A",  "2.5.4": "A",
    "3.1.1": "A",
    "3.2.1": "A",  "3.2.2": "A",
    "3.3.1": "A",  "3.3.2": "A",  "3.3.7": "A",
    "4.1.1": "A",  "4.1.2": "A",
    "1.2.4": "AA", "1.2.5": "AA",
    "1.3.4": "AA", "1.3.5": "AA",
    "1.4.3": "AA", "1.4.4": "AA", "1.4.5": "AA",
    "1.4.10": "AA", "1.4.11": "AA", "1.4.12": "AA", "1.4.13": "AA",
    "2.4.5": "AA", "2.4.6": "AA", "2.4.7": "AA",
    "2.4.11": "AA", "2.4.13": "AA",
    "2.5.7": "AA", "2.5.8": "AA",
    "3.1.2": "AA",
    "3.2.3": "AA", "3.2.4": "AA", "3.2.6": "AA",
    "3.3.3": "AA", "3.3.4": "AA", "3.3.8": "AA",
    "4.1.3": "AA",
}


# ── Request / Response models ──────────────────────────────────────────────────

class CombinedRequest(BaseModel):
    url: HttpUrl
    node_base_url: str = "http://localhost:3000"
    max_depth: int = 0
    run_ocr: bool = True
    run_image_audit: bool = True
    run_form_audit: bool = True
    run_label_in_name_audit: bool = True
    run_pause_stop_hide_audit: bool = True
    run_target_size_audit: bool = True


class JobStatusResponse(BaseModel):
    job_id: str
    status: str          # pending | running | completed | failed
    url: str
    submitted_at: str
    completed_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ── Node caller ───────────────────────────────────────────────────────────────

async def _call_node_analyse_url(url: str, node_base_url: str) -> List[Dict]:
    """POST url to Node's /api/v1/analyse-url; returns the grouped results list."""
    endpoint = f"{node_base_url.rstrip('/')}/api/v1/analyse-url"
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(endpoint, json={"url": url})
        resp.raise_for_status()
        return resp.json().get("results", [])


# ── Python pipeline runner ─────────────────────────────────────────────────────

async def _run_python_pipeline(
    url: str,
    output_dir: Path,
    max_depth: int,
    run_ocr: bool,
    run_image_audit: bool,
    run_form_audit: bool,
    run_label_in_name_audit: bool,
    run_pause_stop_hide_audit: bool,
    run_target_size_audit: bool = True,
) -> Dict[str, Any]:
    """
    Run all Python auditors sequentially (they each open their own browser).
    Returns a dict keyed by auditor name with summary stats.
    """
    results: Dict[str, Any] = {}

    # ── 1.1.1 : Image / Alt-text audit ────────────────────────────────────
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
        total  = len(records)
        passed = sum(1 for r in records if r["overall_status"] == "PASSED")
        results["AltTextAuditor"] = {
            "criteria":      ["1.1.1"],
            "total":         total,
            "passed":        passed,
            "failed":        total - passed,
            "pass_rate_pct": round(passed / total * 100, 1) if total else 0,
            "status":        "PASSED" if total - passed == 0 else "FAILED",
        }

    # ── 3.3.1 / 3.3.2 : Form audit ───────────────────────────────────────
    form_crawler = AsyncFormCrawler(
        base_url=url, output_dir=str(output_dir), max_depth=max_depth,
    )
    form_inputs = await form_crawler.crawl()
    form_crawler.save_raw_json()

    if run_form_audit:
        form_auditor = FormAccessibilityAuditor(output_dir=str(output_dir))
        records  = form_auditor.generate_audit_report(form_inputs=form_inputs)
        summary  = FormAccessibilityAuditor.summarize(records)
        results["FormAuditor"] = {
            "criteria": ["3.3.1", "3.3.2"],
            **summary,
            "status": "PASSED" if summary["failed"] == 0 else "FAILED",
        }

    # ── 2.5.3 : Label in Name audit ───────────────────────────────────────
    interactive_crawler = InteractiveElementCrawler(
        base_url=url, output_dir=str(output_dir), max_depth=max_depth,
    )
    interactive_elements = await interactive_crawler.crawl()
    interactive_crawler.save_raw_json()

    if run_label_in_name_audit:
        lin_auditor = LabelInNameAuditor(output_dir=str(output_dir))
        records = lin_auditor.generate_audit_report(interactive_elements)
        summary = LabelInNameAuditor.summarize(records)
        results["LabelInNameAuditor"] = {
            "criteria": ["2.5.3"],
            **summary,
            "status": "PASSED" if summary["failed"] == 0 else "FAILED",
        }

    # ── 2.2.2 : Pause, Stop, Hide audit ──────────────────────────────────
    moving_crawler = MovingContentCrawler(
        base_url=url, output_dir=str(output_dir), max_depth=max_depth,
    )
    moving_items = await moving_crawler.crawl()
    moving_crawler.save_raw_json()

    if run_pause_stop_hide_audit:
        psh_auditor = PauseStopHideAuditor(output_dir=str(output_dir))
        records = psh_auditor.generate_audit_report(moving_items)
        summary = PauseStopHideAuditor.summarize(records)
        results["PauseStopHideAuditor"] = {
            "criteria": ["2.2.2"],
            **summary,
            "status": "PASSED" if summary["failed"] == 0 else "FAILED",
        }

    # ── 2.5.8 : Target Size audit ─────────────────────────────────────
    target_size_crawler = TargetSizeCrawler(
        base_url=url, output_dir=str(output_dir), max_depth=max_depth,
    )
    target_size_items = await target_size_crawler.crawl()
    target_size_crawler.save_raw_json()

    if run_target_size_audit:
        ts_auditor = TargetSizeAuditor(output_dir=str(output_dir))
        records = ts_auditor.generate_audit_report(target_size_items)
        summary = TargetSizeAuditor.summarize(records)
        results["TargetSizeAuditor"] = {
            "criteria": ["2.5.8"],
            **summary,
            "status": "PASSED" if summary["failed"] == 0 else "FAILED",
        }

    return results


# ── Result merger ──────────────────────────────────────────────────────────────

def _sort_key(cid: str) -> list:
    """Sort WCAG criterion IDs numerically (e.g. "1.4.10" > "1.4.9")."""
    try:
        return [int(p) for p in cid.split(".")]
    except ValueError:
        return [999]


def _merge_results(
    url: str,
    node_results: List[Dict],
    python_results: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Merge Node axe-core results with Python auditor results.
    Groups rules by WCAG criterion, side-by-side.
    axe "incomplete" items go into a separate needs_review bucket (Q2=a).
    """
    # Build axe lookup: criteriaId → { violations, passes, needs_review }
    axe_by_criteria: Dict[str, Dict] = {}
    for group in node_results:
        cid          = group["successCriteriaId"]
        violations   = []
        passes       = []
        needs_review = []
        for rule in group.get("rules", []):
            entry = dict(rule)
            if rule["status"] == "fail":
                violations.append(entry)
            elif rule["status"] == "incomplete":
                needs_review.append(entry)
            else:
                passes.append(entry)
        axe_by_criteria[cid] = {
            "violations":   violations,
            "passes":       passes,
            "needs_review": needs_review,
        }

    # Build python lookup: criteriaId → checker result
    python_by_criteria: Dict[str, Dict] = {}
    for checker_name, summary in python_results.items():
        for cid in summary.get("criteria", []):
            python_by_criteria[cid] = {
                "checker": checker_name,
                **{k: v for k, v in summary.items() if k != "criteria"},
            }

    # Union of all criterion IDs, sorted numerically
    all_criteria = sorted(
        set(axe_by_criteria.keys()) | set(python_by_criteria.keys()),
        key=_sort_key,
    )

    wcag_by_criterion = []
    total_violations   = 0
    total_passes       = 0
    total_needs_review = 0
    python_failed      = 0
    python_passed      = 0

    for cid in all_criteria:
        axe = axe_by_criteria.get(cid)
        py  = python_by_criteria.get(cid)

        if axe:
            total_violations   += len(axe["violations"])
            total_passes       += len(axe["passes"])
            total_needs_review += len(axe["needs_review"])

        if py:
            if py.get("status") == "FAILED":
                python_failed += 1
            elif py.get("status") == "PASSED":
                python_passed += 1

        wcag_by_criterion.append({
            "successCriteriaId": cid,
            "criterionName":     _WCAG_NAMES.get(cid, cid),
            "level":             _WCAG_LEVEL.get(cid, "?"),
            "axe":               axe,
            "python":            py,
        })

    return {
        "url":               url,
        "wcag_by_criterion": wcag_by_criterion,
        "summary": {
            "total_criteria_tested":  len(wcag_by_criterion),
            "axe_violations":         total_violations,
            "axe_passes":             total_passes,
            "axe_needs_review":       total_needs_review,
            "python_criteria_failed": python_failed,
            "python_criteria_passed": python_passed,
        },
    }


# ── Async job runner ───────────────────────────────────────────────────────────

async def _run_job(job_id: str, payload: CombinedRequest) -> None:
    """Background task: runs Python + Node concurrently, merges and stores results."""
    _jobs[job_id]["status"] = "running"
    url = str(payload.url)

    config    = load_config()
    domain    = urlparse(url).netloc.replace("www.", "").replace(".", "_")
    ts        = time.strftime("%m%d_%H%M")
    output_dir = Path(f"{config['input']['output_dir']}/{domain}_{ts}_combined")
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        node_task = asyncio.create_task(
            _call_node_analyse_url(url, payload.node_base_url)
        )
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

        node_results, python_results = await asyncio.gather(node_task, python_task)
        merged = _merge_results(url, node_results, python_results)

        _jobs[job_id].update({
            "status":       "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "result":       merged,
        })
        logger.info(
            f"[combined] job {job_id} completed — "
            f"{len(merged['wcag_by_criterion'])} criteria, "
            f"{merged['summary']['axe_violations']} axe violations, "
            f"{merged['summary']['python_criteria_failed']} python criteria failed"
        )

    except Exception as exc:
        logger.error(f"[combined] job {job_id} failed: {exc}")
        _jobs[job_id].update({
            "status":       "failed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error":        str(exc),
        })


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/", response_model=JobStatusResponse, status_code=202)
async def submit_combined_audit(payload: CombinedRequest):
    """
    Submit a combined Python + Node axe-core accessibility audit.

    Returns job_id immediately (HTTP 202). The audit runs Node (Puppeteer/axe)
    and all Python auditors concurrently via asyncio.gather().

    Poll **GET /api/v1/combined/{job_id}** for status and results.

    Result shape when completed:
    ```json
    {
      "url": "...",
      "wcag_by_criterion": [
        {
          "successCriteriaId": "1.1.1",
          "criterionName": "Non-text Content",
          "level": "A",
          "axe": {
            "violations": [...],
            "passes": [...],
            "needs_review": [...]
          },
          "python": {
            "checker": "AltTextAuditor",
            "status": "FAILED",
            "total": 10,
            "passed": 7,
            "failed": 3
          }
        }
      ],
      "summary": {
        "total_criteria_tested": 42,
        "axe_violations": 5,
        "axe_passes": 38,
        "axe_needs_review": 2,
        "python_criteria_failed": 1,
        "python_criteria_passed": 3
      }
    }
    ```
    """
    job_id = str(uuid.uuid4())
    url    = str(payload.url)
    now    = datetime.now(timezone.utc).isoformat()

    _jobs[job_id] = {
        "job_id":       job_id,
        "status":       "pending",
        "url":          url,
        "submitted_at": now,
        "completed_at": None,
        "result":       None,
        "error":        None,
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
    - **completed** — `result` field populated with merged WCAG data
    - **failed**    — `error` field contains the exception message
    """
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    return job
