"""
ka11y/utils/report_csv.py
=========================
Build the findings CSV server-side.

Byte-for-byte port of ``buildFindingsCsv`` in ka11y-ui/src/lib/wcagAudit.ts. The
browser already produces this file for the Download CSV button; emailing a report
needs the same bytes without a browser in the loop.

The escaping and joining are hand-rolled rather than done with the ``csv`` module
on purpose — ``csv.writer`` emits CRLF line endings and would need a trailing
blank row suppressed, both of which would make the emailed file differ from the
downloaded one. Matching the TS exactly keeps the two outputs identical:

  * quote a field only when it contains ``"``, ``,`` or a newline
  * double any embedded ``"``
  * ``\\n`` line endings
  * exactly one blank line between sections, none after the last
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence


def _csv_escape(value: Any) -> str:
    """Mirror of the TS ``csvEscape``."""
    text = "" if value is None else str(value)
    if any(ch in text for ch in ('"', ",", "\n")):
        return '"' + text.replace('"', '""') + '"'
    return text


def _csv_section(
    title: str, headers: Sequence[str], rows: Sequence[Sequence[Any]]
) -> str:
    """Mirror of the TS ``csvSection``: title line, header row, data rows."""
    lines = [title, ",".join(_csv_escape(h) for h in headers)]
    lines.extend(",".join(_csv_escape(cell) for cell in row) for row in rows)
    return "\n".join(lines)


def _page_url_of(finding: Dict[str, Any], fallback: str) -> str:
    element = finding.get("element")
    if isinstance(element, dict) and element.get("page_url"):
        return str(element["page_url"])
    return fallback


def build_findings_csv(report: Dict[str, Any]) -> str:
    """Return the full report as CSV text (Violations, Needs Review, Passes)."""
    site_url = str(report.get("url") or "")

    # The UI decides this from its scanned-pages selector; `pages_scanned` is the
    # same list that selector reads, so the two agree on when to add the column.
    multi_page = len(report.get("pages_scanned") or []) > 1

    violations: List[Dict] = report.get("violations") or []
    needs_review: List[Dict] = report.get("needs_review") or []
    passes: List[Dict] = report.get("passes") or []

    page_col = ["Page URL"] if multi_page else []

    def page_cell(f: Dict[str, Any]) -> List[str]:
        return [_page_url_of(f, site_url)] if multi_page else []

    violations_section = _csv_section(
        "Violations",
        ["WCAG SC", "Severity", "Level", "Reason", "Suggested Fix", *page_col],
        [
            [
                f.get("wcag_sc") or "",
                f.get("severity") or "",
                f.get("level") or "",
                f.get("reason") or f.get("reason_code") or "",
                f.get("suggested_fix") or "",
                *page_cell(f),
            ]
            for f in violations
        ],
    )

    needs_review_section = _csv_section(
        "Needs Review",
        ["WCAG SC", "Criterion", "Level", "Reason", *page_col],
        [
            [
                f.get("wcag_sc") or "",
                f.get("criterion_name") or "",
                f.get("level") or "",
                f.get("reason") or f.get("reason_code") or "",
                *page_cell(f),
            ]
            for f in needs_review
        ],
    )

    passes_section = _csv_section(
        "Passes",
        ["WCAG SC", "Criterion", "Level", *page_col],
        [
            [
                f.get("wcag_sc") or "",
                f.get("criterion_name") or "",
                f.get("level") or "",
                *page_cell(f),
            ]
            for f in passes
        ],
    )

    return "\n".join(
        [violations_section, "", needs_review_section, "", passes_section]
    )
