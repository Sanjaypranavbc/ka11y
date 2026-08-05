"""
ka11y/utils/report_mail.py
==========================
Compose and send the "your report is ready" email.

Deep crawls (max_depth 1-2) run far longer than a browser will wait, so the
frontend stops polling and the result is delivered here instead.

Every failure path is swallowed: by the time this runs the audit has already
finished and been persisted, so a missing .env or an SMTP outage must never turn
a successful run into a failed one. The caller gets False and a log line.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import urlparse

from ka11y.config.logger import setup_logger
from ka11y.utils.gmail_sender import GmailSender
from ka11y.utils.report_csv import build_findings_csv

logger = setup_logger(name="KAC", tag="mailer")


# Same name the Download CSV button produces (DownloadActions.tsx), so the
# emailed attachment and the browser download are indistinguishable.
_CSV_FILENAME = "a11y-findings.csv"
_PDF_FILENAME = "a11y-findings.pdf"


def _body(site_url: str, summary: Dict[str, Any], pages_scanned: int) -> str:
    score = summary.get("score")
    score_line = "Not scored" if score is None else f"{score}%"
    return (
        f"Scan complete for {site_url}\n"
        f"Pages scanned: {pages_scanned}\n\n"
        f"Violations:    {summary.get('violations', 0)}\n"
        f"Needs review:  {summary.get('needs_review', 0)}\n"
        f"Passes:        {summary.get('passes', 0)}\n"
        f"Score:         {score_line}\n\n"
        "Full results are attached as a PDF and a CSV.\n"
    )


def send_report_email(
    to_email: str,
    report: Dict[str, Any],
    job_id: Optional[str] = None,
    pdf_bytes: Optional[bytes] = None,
) -> bool:
    """Email *report* to *to_email* with the findings CSV attached.

    Returns True if sent, False if skipped (no credentials) or failed.
    """
    if not to_email:
        return False

    try:
        sender = GmailSender()
        if not sender.is_configured():
            logger.warning(
                "[mailer] job %s: SMTP credentials not configured — skipping the "
                "report email to %s. Set SENDER_EMAIL/SENDER_PASSWORD to enable.",
                job_id,
                to_email,
            )
            return False

        site_url = str(report.get("url") or "")
        summary = report.get("summary") or {}
        pages_scanned = len(report.get("pages_scanned") or []) or 1
        host = urlparse(site_url).hostname or site_url

        # PDF first so it is the attachment the recipient sees first; it is
        # omitted rather than fatal when rendering failed upstream.
        attachments = []
        if pdf_bytes:
            attachments.append((_PDF_FILENAME, pdf_bytes, "pdf"))
        attachments.append((_CSV_FILENAME, build_findings_csv(report), "csv"))

        sender.send_email(
            receiver_email=to_email,
            subject=f"Accessibility report — {host}",
            body_text=_body(site_url, summary, pages_scanned),
            attachments=attachments,
        )
        logger.info("[mailer] job %s: report emailed to %s", job_id, to_email)
        return True

    except Exception as exc:  # noqa: BLE001
        # The run itself already succeeded and is stored; a delivery problem is
        # logged and dropped rather than surfaced as an audit failure.
        logger.error(
            "[mailer] job %s: could not email the report to %s (%s: %s)",
            job_id,
            to_email,
            type(exc).__name__,
            exc,
        )
        return False
