
"""
enrich_audit.py
================
Enriches WCAG accessibility audit violations with a dynamic reason and
suggested fix using Gemini's Interactions API.

Input:  combined_report.json (any report shaped like {"violations": [...]})
Output: enriched_report.json  (same report, findings enriched in place)
        token_usage.json      (per-batch + total token/cost accounting)

Can be run as a CLI tool or imported and called via run_enrichment() from a
pipeline/orchestrator.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

DEFAULT_MODEL = "gemini-3.5-flash"

# --------------------------------------------------------------------------
# Language support
# --------------------------------------------------------------------------
# Add more entries here as you enrich sites in other languages. The key is
# whatever you pass via --language (CLI) or language= (pipeline call).
LANGUAGE_NAMES = {
    "en": "English",
    "ja": "Japanese",
}

BASE_SYSTEM_INSTRUCTION = (
    "You are a Web Accessibility Remediation Expert specializing in WCAG 2.1/2.2 (Levels A, AA, AAA).\n\n"
    "You will be given an array of accessibility violation objects extracted from an automated audit\n"
    "(axe-core / custom Python rules / OCR-based image analysis). For EACH violation:\n\n"
    "1. Explain WHY this specific instance fails the referenced WCAG Success Criterion - root cause,\n"
    "   in plain language, tied to the actual element/data given (not a generic definition of the SC).\n"
    "2. Give a DYNAMIC, actionable SUGGESTED FIX specific to this element - include exact code changes\n"
    "   (HTML/CSS/ARIA attributes), color values, alt text wording, or content changes where relevant.\n"
    "   Do not give generic boilerplate advice - reference the actual values present (existing alt\n"
    "   text, hex colors, contrast ratio, tag name, detected OCR text, etc.).\n"
    "3. If severity is \"critical\" or \"high\", note the user-impact (who is blocked and how) in one\n"
    "   sentence; otherwise return an empty string for user_impact.\n"
    "4. Keep the reason under 60 words and the fix under 80 words. No preamble, no markdown headers.\n\n"
    "Return one entry per input violation, in the same order, echoing its finding_id and wcag_sc."
)


def build_system_instruction(language: str = "en") -> str:
    """Return the system instruction, appending an explicit output-language
    directive when language != 'en'. Gemini defaults to the language of the
    PROMPT/instruction, not the language of the audited page's content, so
    this must be stated explicitly for non-English sites."""
    if language == "en":
        return BASE_SYSTEM_INSTRUCTION

    lang_name = LANGUAGE_NAMES.get(language, language)
    language_directive = (
        f"\n\nIMPORTANT - OUTPUT LANGUAGE: Write dynamic_reason, dynamic_suggested_fix, and "
        f"user_impact entirely in {lang_name} ({language}), regardless of the language used in "
        f"this instruction. Keep finding_id and wcag_sc as-is (do not translate identifiers/codes). "
        f"Any HTML/CSS/ARIA code snippets inside the fix should remain in code syntax (untranslated), "
        f"but the surrounding explanation must be in {lang_name}."
    )
    return BASE_SYSTEM_INSTRUCTION + language_directive


# --------------------------------------------------------------------------
# Structured output schema (replaces the old hand-written JSON prompt contract
# - Gemini enforces this shape via response_format, so no parsing fallbacks
# are needed on our side).
# --------------------------------------------------------------------------
class EnrichedFinding(BaseModel):
    finding_id: str
    wcag_sc: str = ""
    dynamic_reason: str = Field(description="Why this specific element/content fails, under 60 words.")
    dynamic_suggested_fix: str = Field(description="Specific, actionable fix with exact values/code, under 80 words.")
    user_impact: str = Field(default="", description="One sentence if severity is high/critical, else empty string.")
    confidence: Literal["high", "medium", "low"] = "medium"


class EnrichmentBatch(BaseModel):
    items: list[EnrichedFinding]


# --------------------------------------------------------------------------
# I/O helpers
# --------------------------------------------------------------------------
def load_report(file_path: str) -> dict:
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found at: {file_path}")
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse input file as JSON: {e}")


def validate_report(report: dict) -> None:
    if not isinstance(report, dict):
        raise ValueError("Report must be a JSON object (dictionary).")
    if "violations" not in report:
        raise ValueError("Report is missing the required 'violations' key.")
    if not isinstance(report["violations"], list):
        raise ValueError("'violations' must be a JSON array (list).")


def find_audit_root_dir(input_path: Path) -> Path:
    """If input_path lives under output/crawled_images/<audit_root>/..., return
    <audit_root>. Otherwise fall back to the input file's parent directory."""
    resolved_path = input_path.resolve()
    for parent in resolved_path.parents:
        if parent.parent.name == "crawled_images":
            return parent
    return resolved_path.parent


def trim_finding(finding: dict) -> dict:
    """Keep only the fields Gemini needs, to save input tokens."""
    element = finding.get("element") or {}
    element_dict = {
        k: v
        for k, v in {
            "html": element.get("html"),
            "tag": element.get("tag"),
            "image_text": element.get("image_text"),
            "page_url": element.get("page_url"),
        }.items()
        if v is not None
    }
    trimmed = {
        "finding_id": finding.get("finding_id"),
        "rule_id": finding.get("rule_id"),
        "wcag_sc": finding.get("wcag_sc"),
        "criterion_name": finding.get("criterion_name"),
        "level": finding.get("level"),
        "severity": finding.get("severity"),
        "existing_reason": finding.get("reason"),
        "existing_suggested_fix": finding.get("suggested_fix"),
        "element": element_dict,
    }
    return {k: v for k, v in trimmed.items() if v is not None}


def chunk_list(lst: list, size: int) -> list[list]:
    return [lst[i : i + size] for i in range(0, len(lst), size)]


# --------------------------------------------------------------------------
# Gemini call
# --------------------------------------------------------------------------
def call_gemini_batch(
    client: genai.Client,
    model_name: str,
    trimmed_batch: list[dict],
    system_instruction: str,
    max_retries: int = 1,
    backoff_seconds: float = 2.0,
):
    """Send one batch to Gemini and return (items, usage, retries_attempted)."""
    prompt = json.dumps(trimmed_batch, ensure_ascii=False, indent=2)
    last_err: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        try:
            # interaction = client.interactions.create(
            #     model=model_name,
            #     input=prompt,
            #     system_instruction=system_instruction,
            #     response_format={
            #         "type": "text",
            #         "mime_type": "application/json",
            #         "schema": EnrichmentBatch.model_json_schema(),
            #
            #     },
            # )
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,

                    response_mime_type="application/json",
                    response_schema=EnrichmentBatch,

                    temperature=0.2,

                    thinking_config=types.ThinkingConfig(
                        thinking_level="minimal"
                    ),
                ),
            )
            # parsed = EnrichmentBatch.model_validate_json(interaction.output_text).items
            parsed = response.parsed.items
            usage = response.usage_metadata
            # return parsed, interaction.usage, attempt
            return parsed, usage, attempt
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                time.sleep(backoff_seconds)

    raise last_err or RuntimeError("Gemini batch processing failed after retries.")


def new_totals() -> dict:
    return {
        "api_calls": 0,
        "retries": 0,
        "failures": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "thought_tokens": 0,
        "cached_tokens": 0,
        "tool_use_tokens": 0,
        "total_tokens": 0,
        "avg_tokens_per_violation": 0.0,
        "estimated_cost_usd": 0.0,
    }


def enrich_violations(
    violations: list[dict],
    client: genai.Client,
    model_name: str,
    batch_size: int,
    batches_log: list[dict],
    totals: dict,
    system_instruction: str,
    delay_between_batches: float = 1.0,
) -> None:
    """Enrich `violations` in place, batch by batch, logging token usage."""
    if not violations:
        return

    trimmed = [trim_finding(v) for v in violations]
    chunks = chunk_list(trimmed, batch_size)
    orig_by_id = {v.get("finding_id"): v for v in violations if v.get("finding_id")}

    for i, chunk in enumerate(chunks):
        batch_idx = len(batches_log) + 1
        start = time.perf_counter()
        record = {
            "batch_index": batch_idx,
            "violation_count": len(chunk),
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "latency_ms": 0,
            "status": "success",
        }
        totals["api_calls"] += 1

        try:
            items, usage, retries_attempted = call_gemini_batch(
                client, model_name, chunk, system_instruction
            )
            record["latency_ms"] = (time.perf_counter() - start) * 1000.0
            totals["retries"] += retries_attempted

            if usage:
                in_tok = getattr(usage, "prompt_token_count", 0) or 0
                out_tok = getattr(usage, "candidates_token_count", 0) or 0
                thought_tok = getattr(usage, "thoughts_token_count", 0) or 0
                cached_tok = getattr(usage, "cached_content_token_count", 0) or 0
                tool_tok = getattr(usage, "tool_use_prompt_token_count", 0) or 0
                tot_tok = getattr(usage, "total_token_count", 0) or 0

                record["input_tokens"] = in_tok
                record["output_tokens"] = out_tok
                record["total_tokens"] = tot_tok

                totals["input_tokens"] += in_tok
                totals["output_tokens"] += out_tok
                totals["thought_tokens"] += thought_tok
                totals["cached_tokens"] += cached_tok
                totals["tool_use_tokens"] += tool_tok
                totals["total_tokens"] += tot_tok

            enriched_by_id = {item.finding_id: item for item in items}
            for entry in chunk:
                fid = entry.get("finding_id")
                orig = orig_by_id.get(fid)
                if not orig:
                    continue
                result = enriched_by_id.get(fid)
                if result:
                    orig["dynamic_reason"] = result.dynamic_reason
                    orig["dynamic_suggested_fix"] = result.dynamic_suggested_fix
                    orig["user_impact"] = result.user_impact
                    orig["confidence"] = result.confidence
                else:
                    orig["dynamic_enrichment_failed"] = True

        except Exception as e:
            record["latency_ms"] = (time.perf_counter() - start) * 1000.0
            record["status"] = "failed"
            totals["failures"] += 1
            totals["retries"] += 1
            print(f"Error processing batch {batch_idx}: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            for entry in chunk:
                orig = orig_by_id.get(entry.get("finding_id"))
                if orig:
                    orig["dynamic_enrichment_failed"] = True

        batches_log.append(record)
        if i < len(chunks) - 1:
            time.sleep(delay_between_batches)


def finalize_totals(totals: dict, violation_count: int, price_input: float, price_output: float) -> None:
    totals["avg_tokens_per_violation"] = totals["total_tokens"] / violation_count if violation_count else 0.0
    totals["estimated_cost_usd"] = (
        totals["input_tokens"] * price_input / 1_000_000.0
        + totals["output_tokens"] * price_output / 1_000_000.0
    )


def print_summary_table(batches: list[dict], totals: dict) -> None:
    headers = ["Batch", "Items", "Input Tokens", "Output Tokens", "Total Tokens", "Latency (ms)", "Status"]
    col_widths = [len(h) for h in headers]
    rows = []
    for b in batches:
        row = [
            str(b["batch_index"]), str(b["violation_count"]), str(b["input_tokens"]),
            str(b["output_tokens"]), str(b["total_tokens"]), f"{b['latency_ms']:.0f}", b["status"].upper(),
        ]
        rows.append(row)
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(val))

    total_row = [
        "TOTALS", f"{totals['api_calls']} calls", str(totals["input_tokens"]),
        str(totals["output_tokens"]), str(totals["total_tokens"]), "-",
        f"{totals['failures']} fail" + (f", {totals['retries']} retries" if totals["retries"] else ""),
    ]
    for i, val in enumerate(total_row):
        col_widths[i] = max(col_widths[i], len(val))

    def fmt(r):
        return "| " + " | ".join(v.ljust(w) for v, w in zip(r, col_widths)) + " |"

    border = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    print("\n" + "=" * 40 + " GEMINI ENRICHMENT SUMMARY " + "=" * 40)
    print(border); print(fmt(headers)); print(border)
    for r in rows:
        print(fmt(r))
    print(border); print(fmt(total_row)); print(border)
    print(f"Thought tokens: {totals['thought_tokens']}  |  Cached tokens: {totals['cached_tokens']}  |  Tool-use tokens: {totals['tool_use_tokens']}")
    print(f"Average tokens per violation: {totals['avg_tokens_per_violation']:.1f}")
    print(f"Estimated Cost: ${totals['estimated_cost_usd']:.5f} USD")
    print("=" * 107 + "\n")


# --------------------------------------------------------------------------
# Core entry point - used by both the CLI and pipeline callers
# --------------------------------------------------------------------------
def run_enrichment(
    report: dict,
    output_dir: Path,
    report_filename: str = "combined_report.json",
    batch_size: int = 10,
    model_name: str = DEFAULT_MODEL,
    price_input: float = 0.075,
    price_output: float = 0.30,
    api_key: Optional[str] = None,
    print_table: bool = True,
    language: str = "en",
) -> dict:
    """Enrich report["violations"] and write enriched_report.json + token_usage.json
    to output_dir. Returns the token_usage dict. Never raises for a missing/bad
    API key - it writes an (unenriched) report and an empty usage file instead,
    so pipeline callers don't crash.

    language: output language for dynamic_reason / dynamic_suggested_fix /
        user_impact (e.g. "en", "ja"). Gemini follows the language of the
        PROMPT, not the language of the audited page, so this must be passed
        explicitly for non-English sites (e.g. language="ja" for Melt Beauty,
        The Answer)."""
    load_dotenv()
    api_key = api_key or os.environ.get("GEMINI_API_KEY")

    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    report_copy = deepcopy(report)
    violations = report_copy.get("violations", [])
    run_started_at = datetime.now(timezone.utc).isoformat()

    def write_outputs(batches_log: list[dict], totals: dict) -> dict:
        with open(out_dir / "enriched_report.json", "w", encoding="utf-8") as f:
            json.dump(report_copy, f, indent=2, ensure_ascii=False)
        usage_data = {
            "report_file": report_filename,
            "run_started_at": run_started_at,
            "run_completed_at": datetime.now(timezone.utc).isoformat(),
            "model": model_name,
            "language": language,
            "violations_enriched": len(violations),
            "batches": batches_log,
            "totals": totals,
        }
        with open(out_dir / "token_usage.json", "w", encoding="utf-8") as f:
            json.dump(usage_data, f, indent=2, ensure_ascii=False)
        return usage_data

    if not api_key:
        print("[enrichment] Warning: GEMINI_API_KEY is not set. Skipping enrichment.", file=sys.stderr)
        return write_outputs([], new_totals())

    if not violations:
        print("No violations to enrich. Writing unmodified report.")
        return write_outputs([], new_totals())

    client = genai.Client(api_key=api_key)
    batches_log: list[dict] = []
    totals = new_totals()
    system_instruction = build_system_instruction(language)

    lang_label = LANGUAGE_NAMES.get(language, language)
    print(f"Enriching {len(violations)} violations using model '{model_name}' (output language: {lang_label})...")
    enrich_violations(violations, client, model_name, batch_size, batches_log, totals, system_instruction)
    finalize_totals(totals, len(violations), price_input, price_output)

    usage_data = write_outputs(batches_log, totals)
    if print_table:
        print_summary_table(batches_log, totals)
    return usage_data


def enrich_report_in_pipeline(
    report: dict,
    output_dir: Path,
    report_filename: str = "combined_report.json",
    batch_size: int = 10,
    model_name: str = DEFAULT_MODEL,
    price_input: float = 0.075,
    price_output: float = 0.30,
    language: str = "en",
) -> None:
    """Backward-compatible entry point for pipeline/orchestrator callers
    (e.g. ka11y/api/v1/combined/runner.py). Thin wrapper around
    run_enrichment() - kept so existing `from enrich_audit import
    enrich_report_in_pipeline` call sites don't need to change.

    Pass language="ja" for Japanese-language sites (e.g. Melt Beauty,
    The Answer) so dynamic_reason/dynamic_suggested_fix come back in
    Japanese instead of defaulting to English."""
    run_enrichment(
        report=report,
        output_dir=output_dir,
        report_filename=report_filename,
        batch_size=batch_size,
        model_name=model_name,
        price_input=price_input,
        price_output=price_output,
        language=language,
    )


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enrich WCAG accessibility violations with dynamic reasons and suggested fixes using Gemini."
    )
    parser.add_argument("--input", required=True, help="Path to the input JSON accessibility report file.")
    parser.add_argument("--output-dir", help="Directory to write output files. Defaults to the audit root dir.")
    parser.add_argument("--batch-size", type=int, default=10, help="Violations per Gemini call (default: 10).")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Gemini model ID (default: {DEFAULT_MODEL}). For deeper reasoning, use gemini-3.1-pro-preview (Preview).",
    )
    parser.add_argument("--price-input", type=float, default=0.075, help="USD per 1M input tokens (default: 0.075).")
    parser.add_argument("--price-output", type=float, default=0.30, help="USD per 1M output tokens (default: 0.30).")
    parser.add_argument(
        "--language",
        default="en",
        help=(
            "Output language for dynamic_reason / dynamic_suggested_fix / user_impact "
            f"(default: en). Supported: {', '.join(LANGUAGE_NAMES.keys())}. "
            "Use 'ja' for Japanese-language sites."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()

    try:
        report = load_report(args.input)
        validate_report(report)
    except Exception as e:
        print(f"Validation Error: {e}", file=sys.stderr)
        return 1

    input_path = Path(args.input).resolve()
    out_dir = Path(args.output_dir).resolve() if args.output_dir else find_audit_root_dir(input_path)

    if not os.environ.get("GEMINI_API_KEY") and not os.getenv("GEMINI_API_KEY"):
        # run_enrichment() also checks this, but fail fast with a clear CLI message.
        load_dotenv()
        if not os.getenv("GEMINI_API_KEY"):
            print("Error: GEMINI_API_KEY environment variable is not set.", file=sys.stderr)
            print("Please add GEMINI_API_KEY to your .env file.", file=sys.stderr)
            return 1

    start = time.perf_counter()
    run_enrichment(
        report=report,
        output_dir=out_dir,
        report_filename=input_path.name,
        batch_size=args.batch_size,
        model_name=args.model,
        price_input=args.price_input,
        price_output=args.price_output,
        language=args.language,
    )
    print(f"Success! Enriched report and token usage files written to: {out_dir}")
    print(f"Total Wall-Clock Time: {time.perf_counter() - start:.2f} seconds")
    return 0


if __name__ == "__main__":
    sys.exit(main())