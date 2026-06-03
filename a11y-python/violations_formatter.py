import json
import csv
import os
import sys

# ── HOW TO USE ───────────────────────────────────────────────────────────────
#  Option 1 — Pass the JSON file path as a command-line argument:
#      python extract_report.py "D:\INTERN2\Works\Wcag\combined_report_2_.json"
#
#  Option 2 — Run without arguments and type the path when prompted:
#      python extract_report.py
#      Enter path to JSON file: D:\INTERN2\Works\Wcag\combined_report_2_.json
#
#  Output: 3 CSV files saved in the SAME folder as the JSON file
#      violations.csv / passes.csv / needs_review.csv
# ─────────────────────────────────────────────────────────────────────────────

SECTIONS = ["violations", "passes", "needs_review"]

FIELDS = [
    "source",
    "rule_id",
    "wcag_sc",
    "criterion_name",
    "level",
    "severity",
    "status",
    "reason",
    "suggested_fix",
    "help_url",
    "element_html",
    "element_tag",
    "element_id",
    "element_target",
    "page_url",
]


def flatten_record(record: dict) -> dict:
    """Flatten the nested 'element' sub-object into top-level fields."""
    flat = {field: record.get(field) for field in FIELDS}

    element = record.get("element") or {}
    flat["element_html"]   = record.get("element_html") or element.get("html")
    flat["element_tag"]    = element.get("tag")
    flat["element_id"]     = element.get("element_id")
    flat["page_url"]       = element.get("page_url")

    # target is a list — join with " | " for readability in CSV
    target = element.get("target") or []
    flat["element_target"] = " | ".join(target) if target else None

    return flat


def export_section(records: list, section_name: str, output_dir: str):
    if not records:
        print(f"  [{section_name}] No records found — skipping.")
        return

    out_path = os.path.join(output_dir, f"{section_name}.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for rec in records:
            writer.writerow(flatten_record(rec))

    print(f"  [{section_name}] {len(records)} records  ->  {out_path}")


def main():
    # Step 1: Get the JSON file path from CLI arg or interactive prompt
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    else:
        input_file = input("Enter path to JSON file: ").strip().strip('"').strip("'")

    if not input_file:
        print("\n  ERROR: No file path provided.")
        sys.exit(1)

    # Validate the file exists
    if not os.path.isfile(input_file):
        print(f"\n  ERROR: File not found -> {input_file}")
        sys.exit(1)

    # Step 2: Output goes to the SAME directory as the JSON file
    output_dir = os.path.dirname(os.path.abspath(input_file))

    # Step 3: Load JSON
    with open(input_file, encoding="utf-8") as f:
        data = json.load(f)

    print(f"\n  Job ID  : {data.get('job_id')}")
    print(f"  URL     : {data.get('url')}")
    print(f"  Status  : {data.get('status')}")
    print(f"  Totals  -> violations : {data.get('violations_count')} | "
          f"needs_review : {data.get('needs_review_count')} | "
          f"passes : {data.get('passes_count')}")
    print(f"\n  Saving CSVs to -> {output_dir}\n")

    # Step 4: Export each section
    for section in SECTIONS:
        export_section(data.get(section, []), section, output_dir)

    print(f"\n  Done! All CSVs saved in: {output_dir}")


if __name__ == "__main__":
    main()