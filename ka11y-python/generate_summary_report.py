
"""
generate_summary_report.py
===========================
Builds a consolidated, human-readable Markdown summary of a (Gemini-)enriched
accessibility audit report for multi-page crawls (max_depth >= 1).

Input:  an enriched report dict (or enriched_report.json on disk) shaped like
        {"url", "summary", "pages": [...], ...} — the same shape enrich_audit.py
        writes to enriched_report.json.
Output: summary_report.md       (per-page tables + a Gemini-written overall
                                  assessment of how violated the crawl is and
                                  how severe the remediation effort is)
        summary_token_usage.json (token/cost accounting for that Gemini call,
                                  same shape as enrich_audit.py's token_usage.json)

The per-page tables (SC / criterion / level / severity / reason / fix / review)
are rendered deterministically from the report data — those numbers and codes
must be exact. Only the "Overall Assessment" narrative is delegated to Gemini,
which is given the aggregate stats (never raw findings) and asked to reason
about severity and remediation priority the way enrich_audit.py reasons about
a single violation's reason/fix.

Single-page audits (max_depth == 0) are intentionally skipped — the report
groups findings per crawled page, which only carries information for
multi-page crawls.

Can be run as a CLI tool or imported and called via run_summary_report() from
a pipeline/orchestrator (see ka11y/api/v1/combined/runner.py).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from enrich_audit import DEFAULT_MODEL, LANGUAGE_NAMES, finalize_totals, new_totals

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
REVIEW_LABELS = {"pass": "Pass", "violation": "Fail"}
PENDING_REVIEW_LABEL = "Pending"


# --------------------------------------------------------------------------
# Structured output schema for the Gemini-written overall assessment
# --------------------------------------------------------------------------
class ConsolidatedSummaryResult(BaseModel):
    overall_severity: Literal["Critical", "High", "Moderate", "Low", "Minimal"]
    narrative: str = Field(
        description="3-5 sentences on how violated the site is overall across the "
        "audited depth, citing the actual score/violation/severity numbers given, and "
        "what level of remediation effort that implies."
    )
    top_priorities: list[str] = Field(
        description="Up to 5 concrete, actionable remediation priorities ordered by "
        "impact, each under 25 words, grounded in the worst-performing pages/criteria given."
    )


CONSOLIDATED_SUMMARY_SYSTEM_INSTRUCTION = (
    "You are a Web Accessibility Program Manager writing the executive summary of a "
    "multi-page WCAG 2.1/2.2 audit for a development team.\n\n"
    "You will be given aggregate statistics for the whole crawl (violation / needs-review / "
    "pass counts, compliance score, severity breakdown, WCAG level breakdown, and the "
    "worst-performing pages and success criteria) — never raw element-level findings. "
    "Using ONLY the numbers given (never invent counts, SC codes, or page URLs that are not "
    "present):\n\n"
    "1. Classify overall_severity as Critical, High, Moderate, Low, or Minimal based on how "
    "many violations exist and how severe they are — critical/high severity counts matter far "
    "more than medium/low ones.\n"
    "2. Write the narrative, citing the actual numbers, and state what level of remediation "
    "effort they imply (e.g. spot fixes vs. a dedicated remediation sprint).\n"
    "3. List top_priorities grounded in the worst-performing pages/criteria given.\n\n"
    "No preamble, no markdown headers in your output fields."
)


def _build_consolidated_system_instruction(language: str = "en") -> str:
    if language == "en":
        return CONSOLIDATED_SUMMARY_SYSTEM_INSTRUCTION
    lang_name = LANGUAGE_NAMES.get(language, language)
    return CONSOLIDATED_SUMMARY_SYSTEM_INSTRUCTION + (
        f"\n\nIMPORTANT - OUTPUT LANGUAGE: Write narrative and top_priorities entirely in "
        f"{lang_name} ({language}), regardless of the language used in this instruction."
    )


# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------
def _md_escape(value: Any) -> str:
    """Collapse whitespace/newlines and escape pipes so values are safe inside
    a Markdown table cell."""
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    return text.replace("|", "\\|") or "—"


def _sc_columns(finding: dict) -> tuple[str, str, str]:
    return (
        _md_escape(finding.get("wcag_sc")),
        _md_escape(finding.get("criterion_name")),
        _md_escape(finding.get("level")),
    )


def _pct(value: Optional[float]) -> str:
    return f"{value}%" if value is not None else "—"


def _violations_table(violations: list[dict]) -> str:
    if not violations:
        return "_No violations on this page._\n"
    rows = [
        "| SC | Criterion | Level | Severity | Reason | Suggested Fix |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    ordered = sorted(violations, key=lambda f: SEVERITY_ORDER.get(f.get("severity"), 9))
    for f in ordered:
        sc, criterion, level = _sc_columns(f)
        severity = _md_escape((f.get("severity") or "—").title() if f.get("severity") else "—")
        reason = _md_escape(f.get("dynamic_reason") or f.get("reason"))
        fix = _md_escape(f.get("dynamic_suggested_fix") or f.get("suggested_fix"))
        rows.append(f"| {sc} | {criterion} | {level} | {severity} | {reason} | {fix} |")
    return "\n".join(rows) + "\n"


def _needs_review_table(items: list[dict]) -> str:
    if not items:
        return "_No items require manual review on this page._\n"
    rows = ["| SC | Criterion | Level | Review |", "| --- | --- | --- | --- |"]
    for f in items:
        sc, criterion, level = _sc_columns(f)
        # review_status is stamped by apply_reviews() once a reviewer adjudicates
        # the item via the frontend; at audit-completion time none exist yet, so
        # every needs_review row starts out Pending.
        review = REVIEW_LABELS.get(f.get("review_status"), PENDING_REVIEW_LABEL)
        rows.append(f"| {sc} | {criterion} | {level} | {review} |")
    return "\n".join(rows) + "\n"


def _passes_table(passes: list[dict]) -> str:
    if not passes:
        return "_No passes recorded on this page._\n"
    rows = ["| SC | Criterion | Level |", "| --- | --- | --- |"]
    for f in passes:
        sc, criterion, level = _sc_columns(f)
        rows.append(f"| {sc} | {criterion} | {level} |")
    return "\n".join(rows) + "\n"


def _heuristic_overall_assessment(summary: dict) -> str:
    """Local fallback used when Gemini is unavailable (no API key) or the
    consolidated-summary call fails — describes how violated the audited site
    is overall, and how much remediation effort that implies, purely from the
    aggregate (whole-crawl) summary numbers."""
    by_sev = summary.get("by_severity") or {}
    critical = by_sev.get("critical", 0)
    high = by_sev.get("high", 0)
    medium = by_sev.get("medium", 0)
    low = by_sev.get("low", 0)
    violations = summary.get("violations", 0)
    needs_review = summary.get("needs_review", 0)
    passes = summary.get("passes", 0)
    total_scored = violations + passes

    weighted = critical * 4 + high * 3 + medium * 2 + low * 1
    if critical > 0 or weighted >= 40:
        label = "Critical"
        effort = (
            "a dedicated remediation sprint — critical/high-severity issues block core "
            "content or navigation for assistive-technology users and should be fixed "
            "before any other accessibility work"
        )
    elif high > 0 or weighted >= 15:
        label = "High"
        effort = (
            "a focused remediation effort across a few sprints, prioritising the "
            "high-severity findings first"
        )
    elif medium > 0 or weighted >= 5:
        label = "Moderate"
        effort = "incremental fixes folded into regular development work"
    elif violations > 0:
        label = "Low"
        effort = "minor, low-risk fixes that can be scheduled opportunistically"
    else:
        label = "Minimal"
        effort = "no dedicated remediation effort — spot-check periodically to prevent regressions"

    return (
        f"Compliance score: **{_pct(summary.get('score'))}** across {total_scored} scored findings "
        f"({violations} violations, {passes} passes; {needs_review} additional item(s) pending manual "
        f"review). Severity breakdown — critical: {critical}, high: {high}, medium: {medium}, low: {low}. "
        f"Overall violation severity across the crawl is **{label}**, requiring {effort}."
    )


def _trim_summary_for_gemini(summary: dict, pages: list[dict]) -> dict:
    """Aggregate-only payload for the overall-assessment call — no raw
    findings, just the counts/scores needed to reason about severity and
    remediation priority."""
    page_rows = [
        {
            "page_url": p.get("page_url"),
            **{
                k: (p.get("summary") or {}).get(k)
                for k in ("violations", "needs_review", "passes", "score", "by_severity")
            },
        }
        for p in pages
    ]
    by_sc = summary.get("by_wcag_sc") or {}
    top_violated_sc = sorted(
        (
            {"wcag_sc": sc, **counts}
            for sc, counts in by_sc.items()
            if counts.get("violations")
        ),
        key=lambda x: -x["violations"],
    )[:10]
    return {
        "aggregate": {
            k: summary.get(k)
            for k in ("violations", "needs_review", "passes", "score", "by_severity", "by_level", "page_count")
        },
        "pages": page_rows,
        "top_violated_success_criteria": top_violated_sc,
    }


def _call_gemini_for_overall_assessment(
    payload: dict,
    model_name: str,
    system_instruction: str,
    api_key: str,
    max_retries: int = 1,
    backoff_seconds: float = 2.0,
):
    """Send the aggregate stats to Gemini and return (result, usage, retries_attempted)."""
    # Explicit timeout so a stalled connection fails fast into the retry path
    # below instead of hanging indefinitely — see enrich_audit.GEMINI_HTTP_TIMEOUT_MS.
    from enrich_audit import GEMINI_HTTP_TIMEOUT_MS

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=GEMINI_HTTP_TIMEOUT_MS),
    )
    prompt = json.dumps(payload, ensure_ascii=False, indent=2)
    last_err: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=ConsolidatedSummaryResult,
                    temperature=0.2,
                    thinking_config=types.ThinkingConfig(thinking_level="high"),
                ),
            )
            return response.parsed, response.usage_metadata, attempt
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                time.sleep(backoff_seconds)

    raise last_err or RuntimeError("Gemini consolidated-summary call failed after retries.")


def generate_overall_assessment(
    summary: dict,
    pages: list[dict],
    model_name: str = DEFAULT_MODEL,
    price_input: float = 1.50,
    price_output: float = 7.50,
    api_key: Optional[str] = None,
    language: str = "en",
) -> tuple[str, dict]:
    """Return (narrative_markdown, usage_record).

    Passes the aggregate crawl statistics to Gemini and asks it to write the
    "Overall Assessment" narrative + severity classification + remediation
    priorities, the same way enrich_audit.py asks Gemini to write a
    dynamic_reason/dynamic_suggested_fix per violation. Falls back to a local
    heuristic (no Gemini call, empty usage totals) if GEMINI_API_KEY is unset
    or the call fails, so a missing key / API outage never blocks the report.
    """
    load_dotenv()
    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    totals = new_totals()

    if not api_key:
        print(
            "[summary-report] Warning: GEMINI_API_KEY is not set. Using local heuristic overall assessment.",
            file=sys.stderr,
        )
        return _heuristic_overall_assessment(summary), {"batches": [], "totals": totals}

    payload = _trim_summary_for_gemini(summary, pages)
    system_instruction = _build_consolidated_system_instruction(language)
    batch_record = {
        "batch_index": 1,
        "page_count": len(pages),
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "latency_ms": 0,
        "status": "success",
    }
    totals["api_calls"] += 1
    start = time.perf_counter()

    try:
        result, usage, retries_attempted = _call_gemini_for_overall_assessment(
            payload, model_name, system_instruction, api_key
        )
        batch_record["latency_ms"] = (time.perf_counter() - start) * 1000.0
        totals["retries"] += retries_attempted

        if usage:
            in_tok = getattr(usage, "prompt_token_count", 0) or 0
            out_tok = getattr(usage, "candidates_token_count", 0) or 0
            thought_tok = getattr(usage, "thoughts_token_count", 0) or 0
            cached_tok = getattr(usage, "cached_content_token_count", 0) or 0
            tool_tok = getattr(usage, "tool_use_prompt_token_count", 0) or 0
            tot_tok = getattr(usage, "total_token_count", 0) or 0

            batch_record["input_tokens"] = in_tok
            batch_record["output_tokens"] = out_tok
            batch_record["total_tokens"] = tot_tok

            totals["input_tokens"] += in_tok
            totals["output_tokens"] += out_tok
            totals["thought_tokens"] += thought_tok
            totals["cached_tokens"] += cached_tok
            totals["tool_use_tokens"] += tool_tok
            totals["total_tokens"] += tot_tok

        narrative = (
            f"**Overall severity: {result.overall_severity}.** {result.narrative}\n\n"
            "**Top priorities:**\n" + "\n".join(f"- {p}" for p in result.top_priorities)
        )
    except Exception as e:
        batch_record["latency_ms"] = (time.perf_counter() - start) * 1000.0
        batch_record["status"] = "failed"
        totals["failures"] += 1
        totals["retries"] += 1
        print(
            f"[summary-report] Gemini overall-assessment call failed, falling back to heuristic: {e}",
            file=sys.stderr,
        )
        traceback.print_exc(file=sys.stderr)
        narrative = _heuristic_overall_assessment(summary)

    finalize_totals(totals, violation_count=1, price_input=price_input, price_output=price_output)
    return narrative, {"batches": [batch_record], "totals": totals}


# --------------------------------------------------------------------------
# Core builder
# --------------------------------------------------------------------------
def build_markdown_report(report: dict, overall_assessment: str) -> str:
    """Render the full consolidated Markdown summary for `report` (a
    (possibly-enriched) combined-audit report dict with a `pages` array),
    with the Gemini-written (or heuristic-fallback) `overall_assessment`
    narrative appended at the end."""
    summary = report.get("summary") or {}
    pages = report.get("pages") or []

    lines: list[str] = [
        "# Consolidated Accessibility Audit Summary",
        "",
        f"- **URL:** {report.get('url', '—')}",
        f"- **Generated at:** {report.get('generated_at', '—')}",
        f"- **Language:** {report.get('lang', 'en')}",
        f"- **Pages audited:** {summary.get('page_count', len(pages))}",
        f"- **Total findings:** {summary.get('total_findings', 0)}",
        f"- **Violations:** {summary.get('violations', 0)}",
        f"- **Needs review:** {summary.get('needs_review', 0)}",
        f"- **Passes:** {summary.get('passes', 0)}",
        f"- **Score:** {_pct(summary.get('score'))}",
        "",
    ]

    for page in pages:
        p_summary = page.get("summary") or {}
        lines.append(f"## Page: {page.get('page_url', '—')}")
        lines.append("")
        lines.append(
            f"Violations: **{p_summary.get('violations', 0)}** | "
            f"Needs review: **{p_summary.get('needs_review', 0)}** | "
            f"Passes: **{p_summary.get('passes', 0)}** | "
            f"Score: **{_pct(p_summary.get('score'))}**"
        )
        lines.append("")
        lines.append("### Violations")
        lines.append("")
        lines.append(_violations_table(page.get("violations") or []))
        lines.append("### Needs Review")
        lines.append("")
        lines.append(_needs_review_table(page.get("needs_review") or []))
        lines.append("### Passes")
        lines.append("")
        lines.append(_passes_table(page.get("passes") or []))

    lines.append("## Overall Assessment")
    lines.append("")
    lines.append(overall_assessment)
    lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------------
# Core entry point — used by both the CLI and pipeline callers
# --------------------------------------------------------------------------
def run_summary_report(
    report: dict,
    output_dir: Path,
    depth: int,
    model_name: str = DEFAULT_MODEL,
    price_input: float = 0.075,
    price_output: float = 0.30,
    api_key: Optional[str] = None,
    language: str = "en",
    filename: str = "summary_report.md",
    usage_filename: str = "summary_token_usage.json",
) -> Optional[str]:
    """Build and write the consolidated Markdown summary for a multi-page
    (depth >= 1) crawl `report` into `output_dir/filename`, plus a
    `usage_filename` token/cost accounting file for the Gemini call behind
    the Overall Assessment section (same shape as enrich_audit.py's
    token_usage.json).

    Returns the Markdown text, or None when depth < 1 — the per-page report
    only carries information for multi-page crawls, so single-page audits
    are skipped and callers should not attach anything to the API response.
    """
    if depth < 1:
        return None

    run_started_at = datetime.now(timezone.utc).isoformat()
    summary = report.get("summary") or {}
    pages = report.get("pages") or []

    overall_assessment, usage = generate_overall_assessment(
        summary,
        pages,
        model_name=model_name,
        price_input=price_input,
        price_output=price_output,
        api_key=api_key,
        language=language,
    )

    markdown = build_markdown_report(report, overall_assessment)

    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / filename, "w", encoding="utf-8") as f:
        f.write(markdown)

    usage_data = {
        "report_file": "enriched_report.json",
        "run_started_at": run_started_at,
        "run_completed_at": datetime.now(timezone.utc).isoformat(),
        "model": model_name,
        "language": language,
        "batches": usage["batches"],
        "totals": usage["totals"],
    }
    with open(out_dir / usage_filename, "w", encoding="utf-8") as f:
        json.dump(usage_data, f, indent=2, ensure_ascii=False)

    return markdown


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a consolidated Markdown summary from an enriched WCAG accessibility report."
    )
    parser.add_argument("--input", required=True, help="Path to enriched_report.json.")
    parser.add_argument("--output-dir", help="Directory to write summary_report.md. Defaults to the input file's directory.")
    parser.add_argument("--depth", type=int, required=True, help="Crawl max_depth for this run (report is skipped if < 1).")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Gemini model ID for the overall-assessment call (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument("--price-input", type=float, default=0.075, help="USD per 1M input tokens (default: 0.075).")
    parser.add_argument("--price-output", type=float, default=0.30, help="USD per 1M output tokens (default: 0.30).")
    parser.add_argument("--language", default="en", help=f"Output language. Supported: {', '.join(LANGUAGE_NAMES.keys())}.")
    parser.add_argument("--filename", default="summary_report.md", help="Output filename (default: summary_report.md).")
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    input_path = Path(args.input).resolve()
    if not input_path.is_file():
        print(f"Error: input file not found at {input_path}", file=sys.stderr)
        return 1

    with open(input_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    out_dir = Path(args.output_dir).resolve() if args.output_dir else input_path.parent
    markdown = run_summary_report(
        report,
        out_dir,
        depth=args.depth,
        model_name=args.model,
        price_input=args.price_input,
        price_output=args.price_output,
        language=args.language,
        filename=args.filename,
    )

    if markdown is None:
        print(f"Skipped: depth={args.depth} < 1, consolidated summary only applies to multi-page crawls.")
        return 0

    print(f"Success! Consolidated summary report written to: {out_dir / args.filename}")
    print(f"Token usage written to: {out_dir / 'summary_token_usage.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
