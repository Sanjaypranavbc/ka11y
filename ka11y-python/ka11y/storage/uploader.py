"""
ka11y/storage/uploader.py
=========================
What gets uploaded, when. Every function is best-effort: a storage failure is
logged and never fails the audit (same contract as ``store/repo.py``).

During the run
    ``store/assets.put_asset`` → :func:`upload_asset_file`
        screenshots · element/OCR/contrast crops · HTML snapshots · subtitles
On completion (``runner``)      → :func:`upload_job_artifacts`
        reports/report.json  · reports/findings.csv · reports/report.pdf
        assets/html/…        (rendered HTML of every crawled page)
        raw/ocr/…            (text_detection_report.json, contrast_report.*)
        raw/steps/…          (execution step log)
    and one ``reports`` row per report file in PostgreSQL (spec §13).
On failure (``runner``)         → :func:`upload_crash`  → crash/crash.json
On retention delete             → :func:`delete_job_artifacts` (opt-in)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ka11y.config.logger import setup_logger
from ka11y.storage import keys
from ka11y.storage.backends import ObjectRef, get_store, guess_type
from ka11y.storage.config import settings

logger = setup_logger(name="KAC", tag="storage")


def _json_default(o: Any) -> Any:
    return str(o)


async def upload_asset_file(
    job_id: str,
    *,
    kind: str,
    path: Path,
    filename: str,
    page_url: Optional[str] = None,
    content_type: Optional[str] = None,
) -> Optional[ObjectRef]:
    """Upload one registered asset. Returns the ref, or None if storage is off/failed."""
    store = get_store()
    if store is None:
        return None
    try:
        prefix = await keys.job_prefix(job_id)
        slug = None
        if page_url:
            from ka11y.crawler.image_extractor import url_slug

            slug = url_slug(page_url)
        if kind in ("ocr_report", "step_log", "crawler_json"):
            folder = {"ocr_report": "ocr", "step_log": "steps", "crawler_json": "crawler"}[kind]
            key = keys.raw_key(prefix, folder, filename)
        else:
            key = keys.asset_key(prefix, kind, filename, page_slug=slug)
        return await store.put_file(key, path, content_type=content_type or guess_type(filename))
    except Exception:  # noqa: BLE001
        logger.warning("[storage] asset upload failed (job=%s kind=%s)", job_id, kind, exc_info=True)
        return None


async def _register_report(job_id: str, ref: ObjectRef, *, report_type: str, fmt: str) -> None:
    try:
        from ka11y.db import audit_repo

        await audit_repo.add_report(
            job_id,
            report_type=report_type,
            fmt=fmt,
            bucket=ref.bucket if ref.backend == "s3" else None,
            key=ref.key,
            size=ref.size,
        )
    except Exception:  # noqa: BLE001
        logger.warning("[storage] reports row failed (job=%s %s)", job_id, fmt, exc_info=True)


async def upload_job_artifacts(
    job_id: str,
    *,
    report: Dict[str, Any],
    output_dir: Optional[Path],
    html_snapshots: Optional[Dict[str, str]] = None,
    step_log_paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Upload everything a finished audit produced. Returns
    ``{"reports": {fmt: key}, "assets": n, "pdf_bytes": bytes|None}``."""
    out: Dict[str, Any] = {"reports": {}, "assets": 0, "pdf_bytes": None}
    store = get_store()
    if store is None:
        return out
    cfg = settings()
    try:
        prefix = await keys.job_prefix(job_id)
    except Exception:  # noqa: BLE001
        logger.warning("[storage] cannot resolve prefix for %s", job_id, exc_info=True)
        return out

    # 1. Full report JSON
    try:
        raw = json.dumps(report, ensure_ascii=False, default=_json_default).encode("utf-8")
        ref = await store.put_bytes(keys.report_key(prefix, "report.json"), raw, content_type="application/json")
        out["reports"]["json"] = ref.key
        await _register_report(job_id, ref, report_type="detailed", fmt="json")
    except Exception:  # noqa: BLE001
        logger.warning("[storage] report.json upload failed (%s)", job_id, exc_info=True)

    # 2. Findings CSV
    try:
        from ka11y.utils.report_csv import build_findings_csv

        csv_text = build_findings_csv(report)
        ref = await store.put_bytes(
            keys.report_key(prefix, "findings.csv"), csv_text.encode("utf-8"), content_type="text/csv"
        )
        out["reports"]["csv"] = ref.key
        await _register_report(job_id, ref, report_type="tabular", fmt="csv")
    except Exception:  # noqa: BLE001
        logger.warning("[storage] findings.csv upload failed (%s)", job_id, exc_info=True)

    # 3. PDF (Chromium render — the most expensive step; opt-out via KA11Y_ARTIFACT_PDF=0)
    if cfg.pdf_on_complete:
        try:
            from ka11y.utils.report_pdf import build_report_pdf

            pdf = await build_report_pdf(report)
            if pdf:
                ref = await store.put_bytes(keys.report_key(prefix, "report.pdf"), pdf, content_type="application/pdf")
                out["reports"]["pdf"] = ref.key
                out["pdf_bytes"] = pdf
                await _register_report(job_id, ref, report_type="summary", fmt="pdf")
        except Exception:  # noqa: BLE001
            logger.warning("[storage] report.pdf upload failed (%s)", job_id, exc_info=True)

    # 4. HTML snapshots, OCR artifacts and step logs go through the asset
    #    registry so they are listed/served like every other asset.
    from ka11y.store.assets import put_asset

    for page_url, html_path in (html_snapshots or {}).items():
        p = Path(html_path)
        if p.is_file():
            if await put_asset(run_id=job_id, kind="html_snapshot", data=p, page_url=page_url, mime="text/html"):
                out["assets"] += 1

    if output_dir:
        for p in _ocr_artifact_files(Path(output_dir)):
            if await put_asset(run_id=job_id, kind="ocr_report", data=p, mime=guess_type(p.name)):
                out["assets"] += 1

    for sp in step_log_paths or []:
        p = Path(sp)
        if p.is_file():
            if await put_asset(run_id=job_id, kind="step_log", data=p, mime=guess_type(p.name, "text/plain")):
                out["assets"] += 1

    logger.info(
        "[storage] job %s artifacts uploaded: reports=%s assets=%d",
        job_id, sorted(out["reports"]), out["assets"],
    )
    return out


def _ocr_artifact_files(output_dir: Path) -> List[Path]:
    """text_detection_report.json + contrast_report.{json,csv,md} wherever the
    OCR stage wrote them under the run's output directory."""
    names = {"text_detection_report.json", "contrast_report.json", "contrast_report.csv", "contrast_report.md"}
    found: List[Path] = []
    try:
        for p in output_dir.rglob("*"):
            if p.is_file() and p.name in names and "text_detected" in p.parts:
                found.append(p)
    except OSError:
        pass
    return found


async def upload_crash(job_id: str, payload: Dict[str, Any]) -> Optional[ObjectRef]:
    store = get_store()
    if store is None:
        return None
    try:
        prefix = await keys.job_prefix(job_id)
        raw = json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default).encode("utf-8")
        return await store.put_bytes(keys.crash_key(prefix), raw, content_type="application/json")
    except Exception:  # noqa: BLE001
        logger.warning("[storage] crash upload failed (%s)", job_id, exc_info=True)
        return None


async def delete_job_artifacts(job_id: str) -> int:
    store = get_store()
    if store is None:
        return 0
    try:
        prefix = await keys.job_prefix(job_id)
        n = await store.delete_prefix(prefix)
        keys.forget_job(job_id)
        return n
    except Exception:  # noqa: BLE001
        logger.warning("[storage] delete failed (%s)", job_id, exc_info=True)
        return 0


async def download_url_for(key: Optional[str], *, filename: Optional[str] = None) -> Optional[str]:
    """Presigned URL (S3) or None (local backend → serve through the API)."""
    store = get_store()
    if store is None or not key:
        return None
    try:
        return await store.download_url(key, filename=filename)
    except Exception:  # noqa: BLE001
        logger.debug("[storage] presign failed for %s", key, exc_info=True)
        return None
