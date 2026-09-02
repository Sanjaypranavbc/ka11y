"""
ka11y/utils/report_pdf.py
=========================
Render the findings report as a PDF.

Emailed alongside the CSV: the CSV is for filtering and pivoting, the PDF is for
reading and forwarding. It carries the same three sections the dashboard shows —
Violations, Needs Review, Passes.

Chromium does the rendering, leased from the existing crawler browser pool, so
this adds no dependency and no extra browser process. (The UI's "PDF" button is
a plain ``window.print()`` of whatever page is on screen, so there is no existing
document format to match here.)
"""

from __future__ import annotations

import base64
import io
import math
import re
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import parse_qs, unquote, urlparse

from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="mailer")

# Taken from ka11y-ui/src/app/globals.css so the printed charts read as the same
# product as the dashboard rather than a differently-coloured lookalike.
_C_VIOLATION = "#c00000"
_C_REVIEW = "#114bbf"
_C_PASS = "#00b48c"
_C_TEAL = "#00ac8f"
_C_TEAL_DARK = "#005856"
_LEVEL_COLORS = {"A": "#8fe3d2", "AA": "#00a88f", "AAA": "#00695c"}

# Long single-run cap: a 20-page crawl can produce thousands of passes, and a
# multi-thousand-row PDF is neither readable nor cheap to render. The CSV is the
# complete record; the PDF is the readable summary.
_MAX_ROWS_PER_SECTION = 200

_CSS = """
  @page { size: A4 landscape; margin: 14mm 10mm; }
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial,
                 "Noto Sans JP", sans-serif;
    color: #1a1a1a; font-size: 9pt; line-height: 1.45; margin: 0;
  }
  h1 { font-size: 16pt; margin: 0 0 2mm; font-weight: 600; }
  .meta { color: #555; font-size: 8.5pt; margin-bottom: 5mm; }
  .meta a { color: #0f6b63; text-decoration: none; }
  .totals { display: flex; gap: 4mm; margin-bottom: 7mm; flex-wrap: wrap; }
  .card {
    border: 1px solid #d9d9d9; border-radius: 4px; padding: 2.5mm 4mm; min-width: 26mm;
  }
  .card .n { font-size: 13pt; font-weight: 600; }
  .card .k { font-size: 7.5pt; text-transform: uppercase; letter-spacing: .4px; color: #666; }
  h2 {
    font-size: 11pt; margin: 0 0 2mm; padding-bottom: 1.5mm;
    border-bottom: 2px solid #0f6b63; font-weight: 600;
    /* Never leave a section heading stranded at the foot of a page. */
    page-break-after: avoid; break-after: avoid;
  }
  section { margin-bottom: 8mm; }
  /* Repeat headers when a table splits across pages, and never break a row. */
  table { width: 100%; border-collapse: collapse; table-layout: fixed; }
  thead { display: table-header-group; }
  tr { page-break-inside: avoid; }
  th, td {
    border: 1px solid #e0e0e0; padding: 1.6mm 2mm; text-align: left;
    vertical-align: top; word-wrap: break-word; overflow-wrap: anywhere;
  }
  th { background: #f4f6f6; font-weight: 600; font-size: 8pt; }
  .empty { color: #777; font-style: italic; padding: 2mm 0; }
  .note { color: #777; font-size: 8pt; margin-top: 1.5mm; }

  /* Dashboard charts */
  .charts {
    display: grid; grid-template-columns: 1fr 1fr; gap: 5mm; margin-bottom: 8mm;
  }
  .chart {
    border: 1px solid #e0e0e0; border-radius: 4px; padding: 3mm 4mm;
    page-break-inside: avoid;
  }
  .chart.wide { grid-column: 1 / -1; }
  .chart h3 {
    font-size: 9.5pt; font-weight: 600; margin: 0 0 2.5mm; color: #333;
  }
  .chart svg { display: block; margin: 0 auto; }
  .legend {
    display: flex; flex-wrap: wrap; gap: 1.5mm 4mm; margin-top: 2.5mm;
    font-size: 8pt; color: #444; justify-content: center;
  }
  .legend .li { display: inline-flex; align-items: center; gap: 1.2mm; }
  .legend i {
    width: 8px; height: 8px; border-radius: 2px; display: inline-block;
  }
  .legend b { font-weight: 600; margin-left: 1mm; }
  .pages td:first-child { word-break: break-all; }
  /* Element column: thumbnail above its source filename, as on the dashboard. */
  img.thumb {
    display: block; max-width: 100%; max-height: 22mm; height: auto;
    border: 1px solid #e0e0e0; border-radius: 2px; margin-bottom: 1mm;
  }
  .fname {
    display: block; font-size: 7pt; color: #666; word-break: break-all;
    line-height: 1.3;
  }
  /* Findings tables start on their own page so the dashboard reads as one view. */
  .tables { page-break-before: always; }
"""


def _legend(items: Sequence[Tuple[str, str, Any]]) -> str:
    """Colour swatch + label + value, shared by the chart cards."""
    return "<div class='legend'>" + "".join(
        f"<span class='li'><i style='background:{c}'></i>{escape(label)}"
        f"<b>{escape(str(value))}</b></span>"
        for label, c, value in items
    ) + "</div>"


def _donut(segments: Sequence[Tuple[str, str, int]]) -> str:
    """Donut chart. Segments are (label, colour, value).

    Drawn with stroke-dasharray on concentric circles rather than arc paths —
    far less trigonometry to get wrong, and Chromium renders it identically.
    """
    total = sum(v for _, _, v in segments)
    if total <= 0:
        return "<p class='empty'>No findings.</p>"

    r, cx, cy = 54.0, 70.0, 70.0
    circumference = 2 * math.pi * r
    offset = 0.0
    arcs = []
    for _label, colour, value in segments:
        if value <= 0:
            continue
        length = circumference * value / total
        arcs.append(
            f"<circle cx='{cx}' cy='{cy}' r='{r}' fill='none' stroke='{colour}' "
            f"stroke-width='26' stroke-dasharray='{length:.2f} {circumference - length:.2f}' "
            f"stroke-dashoffset='{-offset:.2f}' transform='rotate(-90 {cx} {cy})'/>"
        )
        offset += length

    return (
        f"<svg viewBox='0 0 140 140' width='140' height='140' role='img'>"
        f"{''.join(arcs)}"
        f"<text x='{cx}' y='{cy - 2}' text-anchor='middle' font-size='20' "
        f"font-weight='600' fill='#1a1a1a'>{total}</text>"
        f"<text x='{cx}' y='{cy + 13}' text-anchor='middle' font-size='9' "
        f"fill='#666'>findings</text></svg>"
    )


def _gauge(score: Optional[float]) -> str:
    """Semicircular score gauge, mirroring the dashboard's PerformanceGauge."""
    if score is None:
        return "<p class='empty'>Not scored.</p>"

    r, cx, cy = 58.0, 70.0, 72.0
    arc_len = math.pi * r
    filled = arc_len * max(0.0, min(100.0, float(score))) / 100.0
    path = f"M {cx - r} {cy} A {r} {r} 0 0 1 {cx + r} {cy}"
    return (
        f"<svg viewBox='0 0 140 92' width='150' height='99' role='img'>"
        f"<path d='{path}' fill='none' stroke='#e2e6e6' stroke-width='16' stroke-linecap='round'/>"
        f"<path d='{path}' fill='none' stroke='{_C_TEAL}' stroke-width='16' stroke-linecap='round' "
        f"stroke-dasharray='{filled:.2f} {arc_len - filled:.2f}'/>"
        f"<text x='{cx}' y='{cy - 8}' text-anchor='middle' font-size='22' font-weight='600' "
        f"fill='{_C_TEAL_DARK}'>{score}%</text>"
        f"<text x='{cx}' y='{cy + 6}' text-anchor='middle' font-size='8.5' fill='#666'>pass rate</text>"
        f"</svg>"
    )


def _level_bars(breakdown: Sequence[Dict[str, Any]]) -> str:
    """Grouped bars: violations / needs review / passes for each WCAG level."""
    peak = max(
        [
            max(r["violations"], r["needs_review"], r["passes"])
            for r in breakdown
        ]
        or [0]
    )
    if peak <= 0:
        return "<p class='empty'>No findings.</p>"

    w, h, pad = 300.0, 130.0, 18.0
    plot_h = h - pad - 14
    group_w = w / len(breakdown)
    bar_w = group_w / 4.5
    bars = []
    for i, row in enumerate(breakdown):
        base_x = i * group_w + (group_w - bar_w * 3) / 2
        for j, (key, colour) in enumerate(
            (("violations", _C_VIOLATION), ("needs_review", _C_REVIEW), ("passes", _C_PASS))
        ):
            value = row[key]
            bar_h = plot_h * value / peak if peak else 0
            x = base_x + j * bar_w
            y = pad + plot_h - bar_h
            bars.append(
                f"<rect x='{x:.1f}' y='{y:.1f}' width='{bar_w - 1.5:.1f}' "
                f"height='{bar_h:.1f}' fill='{colour}' rx='1.5'/>"
            )
        bars.append(
            f"<text x='{i * group_w + group_w / 2:.1f}' y='{h - 2:.1f}' text-anchor='middle' "
            f"font-size='9' fill='#555'>{escape(str(row['level']))}</text>"
        )

    return (
        f"<svg viewBox='0 0 {w} {h}' width='100%' height='{h}' role='img'>"
        f"<line x1='0' y1='{pad + plot_h}' x2='{w}' y2='{pad + plot_h}' stroke='#d9d9d9'/>"
        f"{''.join(bars)}</svg>"
    )


def _criteria_bars(criteria: Sequence[Dict[str, Any]]) -> str:
    """Horizontal bars for the most-failed criteria, coloured by WCAG level."""
    if not criteria:
        return "<p class='empty'>No failing criteria.</p>"

    peak = max(c["count"] for c in criteria) or 1
    row_h, label_w, w = 17.0, 150.0, 330.0
    bar_max = w - label_w - 34
    rows = []
    for i, c in enumerate(criteria):
        y = i * row_h
        bar_w = bar_max * c["count"] / peak
        label = f"{c['code']} {c['label']}"
        if len(label) > 30:
            label = label[:29] + "…"
        pages = c.get("pages_affected") or 0
        suffix = f"{c['count']}" + (f" · {pages}p" if pages > 1 else "")
        rows.append(
            f"<text x='0' y='{y + 11:.1f}' font-size='8.5' fill='#333'>{escape(label)}</text>"
            f"<rect x='{label_w}' y='{y + 3:.1f}' width='{bar_w:.1f}' height='9' rx='1.5' "
            f"fill='{_LEVEL_COLORS.get(c.get('level'), _C_TEAL)}'/>"
            f"<text x='{label_w + bar_w + 4:.1f}' y='{y + 11:.1f}' font-size='8' "
            f"fill='#555'>{escape(suffix)}</text>"
        )

    height = len(criteria) * row_h
    return (
        f"<svg viewBox='0 0 {w} {height}' width='100%' height='{height}' role='img'>"
        f"{''.join(rows)}</svg>"
    )


def _level_breakdown(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    by_level = (report.get("summary") or {}).get("by_level") or {}
    out = []
    for level in ("A", "AA", "AAA"):
        counts = by_level.get(level) or {}
        out.append(
            {
                "level": level,
                "violations": counts.get("violations", 0),
                "needs_review": counts.get("needs_review", 0),
                "passes": counts.get("passes", 0),
            }
        )
    return out


def _top_criteria(report: Dict[str, Any], limit: int = 8) -> List[Dict[str, Any]]:
    """Mirror of the dashboard's getTopFailingCriteria."""
    by_sc = (report.get("summary") or {}).get("by_wcag_sc") or {}

    meta: Dict[str, Dict[str, str]] = {}
    for key in ("violations", "needs_review", "passes"):
        for f in report.get(key) or []:
            sc = f.get("wcag_sc")
            if sc and sc not in meta:
                meta[sc] = {
                    "level": f.get("level") or "A",
                    "label": f.get("criterion_name") or sc,
                }

    rows = [
        {
            "code": code,
            "label": meta.get(code, {}).get("label", code),
            "level": meta.get(code, {}).get("level", "A"),
            "count": counts.get("violations", 0),
            "pages_affected": counts.get("pages_affected", 0),
        }
        for code, counts in by_sc.items()
    ]
    rows = [r for r in rows if r["count"] > 0]
    rows.sort(key=lambda r: -r["count"])
    return rows[:limit]


def _pages_table(report: Dict[str, Any]) -> str:
    """Per-page breakdown — the dashboard's Findings by Page table."""
    pages = report.get("pages") or []
    if not pages:
        return ""

    rows = []
    for page in pages[:40]:
        summary = page.get("summary") or {}
        score = summary.get("score")
        rows.append(
            _row_html(
                [
                    page.get("page_url") or "",
                    "—" if score is None else f"{score}%",
                    summary.get("total_findings", 0),
                    summary.get("violations", 0),
                    summary.get("needs_review", 0),
                    summary.get("passes", 0),
                ]
            )
        )

    head = "".join(
        f"<th>{h}</th>"
        for h in ("Page", "Score", "Findings", "Violations", "Needs review", "Passes")
    )
    note = (
        f"<p class='note'>Showing 40 of {len(pages)} pages.</p>"
        if len(pages) > 40
        else ""
    )
    return (
        f"<section><h2>Findings by page ({len(pages)})</h2>"
        f"<table class='pages'><thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>{note}</section>"
    )


def _charts(report: Dict[str, Any]) -> str:
    """The dashboard's four charts, redrawn as print-friendly SVG."""
    summary = report.get("summary") or {}
    violations = summary.get("violations", len(report.get("violations") or []))
    needs_review = summary.get("needs_review", len(report.get("needs_review") or []))
    passes = summary.get("passes", len(report.get("passes") or []))

    overview = _donut(
        [
            ("Violations", _C_VIOLATION, violations),
            ("Needs review", _C_REVIEW, needs_review),
            ("Passes", _C_PASS, passes),
        ]
    ) + _legend(
        [
            ("Violations", _C_VIOLATION, violations),
            ("Needs review", _C_REVIEW, needs_review),
            ("Passes", _C_PASS, passes),
        ]
    )

    levels = _level_breakdown(report)
    level_chart = _level_bars(levels) + _legend(
        [
            ("Violations", _C_VIOLATION, ""),
            ("Needs review", _C_REVIEW, ""),
            ("Passes", _C_PASS, ""),
        ]
    )

    criteria_chart = _criteria_bars(_top_criteria(report)) + _legend(
        [(f"Level {lvl}", col, "") for lvl, col in _LEVEL_COLORS.items()]
    )

    def card(title: str, body: str, wide: bool = False) -> str:
        cls = "chart wide" if wide else "chart"
        return f"<div class='{cls}'><h3>{escape(title)}</h3>{body}</div>"

    return (
        "<div class='charts'>"
        + card("Findings overview", overview)
        + card("Site performance score", _gauge(summary.get("score")))
        + card("WCAG level breakdown", level_chart)
        + card("Top failing criteria", criteria_chart)
        + "</div>"
    )


class _Raw(str):
    """Marks a cell whose content is already HTML and must not be escaped."""


# ── Element images ───────────────────────────────────────────────────────────
# Chromium renders the report via set_content(), so it has no base URL and no
# API credentials — the "/api/v1/assets/…" and "/api/v1/combined/…/image?path=…"
# srcs the report carries would all fail to load. Each image is therefore
# resolved back to a file on disk, downscaled, and inlined as a data: URI.

_THUMB_W, _THUMB_H = 190, 130
# Base64 inflates by ~33% and Gmail rejects messages over 25 MB, so the embedded
# images get their own budget well under that. Once spent, remaining rows simply
# show no thumbnail rather than the attachment becoming undeliverable.
_IMAGE_BUDGET_BYTES = 6_000_000
_ASSET_URL_RE = re.compile(r"^/api/v1/assets/(\d+)$")


async def _src_to_path(src: str) -> Optional[str]:
    """Map a report image src back to an absolute file path, if it is local."""
    if src.startswith("/api/v1/assets/"):
        match = _ASSET_URL_RE.match(src)
        if not match:
            return None
        from ka11y.store.assets import get_asset

        row = await get_asset(int(match.group(1)))
        return row.get("abs_path") if row else None

    if src.startswith("/api/v1/"):
        # Legacy serving route: the real path is the ?path= query parameter.
        query = parse_qs(urlparse(src).query)
        raw = (query.get("path") or [None])[0]
        return unquote(raw) if raw else None

    if src.startswith(("http://", "https://", "data:")):
        # Never fetch remote images while rendering a report.
        return None

    return src


def _thumbnail_data_uri(path: str) -> Optional[Tuple[str, int]]:
    """Return (data-URI, encoded size) for *path*, downscaled. None if unusable."""
    try:
        from PIL import Image

        with Image.open(path) as img:
            img.load()
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            img.thumbnail((_THUMB_W, _THUMB_H), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=72, optimize=True)
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}", len(encoded)
    except Exception:  # noqa: BLE001 — a bad crop must not sink the whole PDF
        return None


async def _collect_images(report: Dict[str, Any], limit: int) -> Dict[str, str]:
    """Build a ``{image_src: data-URI}`` map for the rows the PDF will render.

    Only the rows that actually appear are resolved, and the same src is
    encoded once however many findings reference it.
    """
    srcs: List[str] = []
    seen = set()
    for key in ("violations", "needs_review", "passes"):
        for finding in (report.get(key) or [])[:limit]:
            element = finding.get("element")
            if not isinstance(element, dict):
                continue
            src = element.get("image_src")
            if src and src not in seen:
                seen.add(src)
                srcs.append(src)

    images: Dict[str, str] = {}
    spent = 0
    for src in srcs:
        if spent >= _IMAGE_BUDGET_BYTES:
            logger.info(
                "[mailer] image budget reached after %d thumbnails — remaining "
                "rows render without one",
                len(images),
            )
            break
        try:
            path = await _src_to_path(src)
        except Exception:  # noqa: BLE001
            continue
        if not path or not Path(path).is_file():
            continue
        made = _thumbnail_data_uri(path)
        if not made:
            continue
        uri, size = made
        images[src] = uri
        spent += size
    return images


def _element_cell(finding: Dict[str, Any], images: Dict[str, str]) -> "_Raw":
    """Element column: thumbnail plus the source filename, as on the dashboard."""
    element = finding.get("element")
    if not isinstance(element, dict):
        return _Raw("—")

    src = element.get("image_src")
    uri = images.get(src) if src else None

    parts = []
    if uri:
        parts.append(f"<img class='thumb' src='{uri}' alt=''/>")

    # Name the image underneath it. `image_reference` is the image's real file
    # name from its src URL (see findings._source_filename), which is the most
    # recognisable label; asset URLs resolve to sha256 filenames, which would be
    # noise, so those fall back to nothing.
    name = element.get("image_reference") or ""
    if not name and src and not src.startswith("/api/v1/"):
        name = Path(src).name
    elif not name and src and "path=" in src:
        raw = unquote(parse_qs(urlparse(src).query).get("path", [""])[0])
        name = Path(raw).name if raw else ""
    if name:
        parts.append(f"<span class='fname'>{escape(str(name))}</span>")

    return _Raw("".join(parts) if parts else "—")


def _row_html(cells: Sequence[Any]) -> str:
    # `str(c or "")` would blank out a legitimate 0 — a page with zero
    # violations must read "0", not an empty cell.
    out = []
    for c in cells:
        if isinstance(c, _Raw):
            out.append(f"<td>{c}</td>")
        else:
            out.append(f"<td>{escape('' if c is None else str(c))}</td>")
    return "<tr>" + "".join(out) + "</tr>"


def _table(
    title: str,
    headers: Sequence[str],
    rows: List[Sequence[str]],
    total: int,
) -> str:
    if not rows:
        return f"<section><h2>{escape(title)}</h2><p class='empty'>None found.</p></section>"

    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = "".join(_row_html(r) for r in rows)
    note = ""
    if total > len(rows):
        note = (
            f"<p class='note'>Showing the first {len(rows)} of {total}. "
            "The attached CSV contains every row.</p>"
        )
    return (
        f"<section><h2>{escape(title)} ({total})</h2>"
        f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>{note}</section>"
    )


def _page_url_of(finding: Dict[str, Any], fallback: str) -> str:
    element = finding.get("element")
    if isinstance(element, dict) and element.get("page_url"):
        return str(element["page_url"])
    return fallback


def build_report_html(
    report: Dict[str, Any], images: Optional[Dict[str, str]] = None
) -> str:
    """Build the printable HTML document for *report*.

    *images* maps ``element.image_src`` to an inline data URI (see
    :func:`_collect_images`). Omit it to render the tables without thumbnails.
    """
    images = images or {}
    site_url = str(report.get("url") or "")
    summary = report.get("summary") or {}
    pages = report.get("pages_scanned") or []
    multi_page = len(pages) > 1

    def page_col(f: Dict[str, Any]) -> List[str]:
        return [_page_url_of(f, site_url)] if multi_page else []

    page_header = ["Page"] if multi_page else []

    violations: List[Dict] = report.get("violations") or []
    needs_review: List[Dict] = report.get("needs_review") or []
    passes: List[Dict] = report.get("passes") or []

    v_rows = [
        [
            f.get("wcag_sc") or "",
            f.get("severity") or "",
            f.get("level") or "",
            f.get("reason") or f.get("reason_code") or "",
            f.get("suggested_fix") or "",
            _element_cell(f, images),
            *page_col(f),
        ]
        for f in violations[:_MAX_ROWS_PER_SECTION]
    ]
    n_rows = [
        [
            f.get("wcag_sc") or "",
            f.get("criterion_name") or "",
            f.get("level") or "",
            f.get("reason") or f.get("reason_code") or "",
            _element_cell(f, images),
            *page_col(f),
        ]
        for f in needs_review[:_MAX_ROWS_PER_SECTION]
    ]
    p_rows = [
        [
            f.get("wcag_sc") or "",
            f.get("criterion_name") or "",
            f.get("level") or "",
            _element_cell(f, images),
            *page_col(f),
        ]
        for f in passes[:_MAX_ROWS_PER_SECTION]
    ]

    score = summary.get("score")
    score_text = "—" if score is None else f"{score}%"

    cards = "".join(
        f"<div class='card'><div class='n'>{n}</div><div class='k'>{escape(k)}</div></div>"
        for k, n in (
            ("Violations", summary.get("violations", len(violations))),
            ("Needs review", summary.get("needs_review", len(needs_review))),
            ("Passes", summary.get("passes", len(passes))),
            ("Score", score_text),
            ("Pages", len(pages) or 1),
        )
    )

    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>Accessibility report — {escape(site_url)}</title>"
        f"<style>{_CSS}</style></head><body>"
        "<h1>Accessibility report</h1>"
        f"<div class='meta'>{escape(site_url)}</div>"
        f"<div class='totals'>{cards}</div>"
        + _charts(report)
        + _pages_table(report)
        + "<div class='tables'>"
        + _table(
            "Violations",
            [
                "WCAG SC",
                "Severity",
                "Level",
                "Reason",
                "Suggested fix",
                "Element",
                *page_header,
            ],
            v_rows,
            len(violations),
        )
        + _table(
            "Needs review",
            ["WCAG SC", "Criterion", "Level", "Reason", "Element", *page_header],
            n_rows,
            len(needs_review),
        )
        + _table(
            "Passes",
            ["WCAG SC", "Criterion", "Level", "Element", *page_header],
            p_rows,
            len(passes),
        )
        + "</div></body></html>"
    )


async def build_report_pdf(report: Dict[str, Any]) -> Optional[bytes]:
    """Render *report* to PDF bytes, or None if rendering fails.

    Returning None rather than raising keeps a rendering problem from costing the
    user their email — the CSV still goes out on its own.
    """
    try:
        from ka11y.crawler.browser_pool import get_pool

        # Resolved before rendering: asset lookups hit the DB, which needs this
        # event loop, and the images must be inline by the time Chromium runs.
        images = await _collect_images(report, _MAX_ROWS_PER_SECTION)
        if images:
            logger.info("[mailer] embedded %d element thumbnails", len(images))

        html = build_report_html(report, images)
        pool = get_pool()
        async with pool.lease_context() as context:
            page = await context.new_page()
            try:
                await page.set_content(html, wait_until="load")
                return await page.pdf(
                    format="A4",
                    landscape=True,
                    print_background=True,
                    margin={
                        "top": "14mm",
                        "bottom": "14mm",
                        "left": "10mm",
                        "right": "10mm",
                    },
                )
            finally:
                await page.close()
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "[mailer] PDF rendering failed (%s: %s) — sending the CSV only",
            type(exc).__name__,
            exc,
        )
        return None
