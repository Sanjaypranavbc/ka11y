# Accessbility Checker Backend API

This is an mimic of a11y of axe-core + lighthouse + visual accessbility test

## Installation
```
poetry install
```

## Observability (Arize tracing)

`ka11y/observability/` exports OpenTelemetry traces of the whole audit engine
to [Arize](https://arize.com) or any OpenInference collector. An audit is one
trace, from the HTTP call that submitted it down to the individual Gemini
requests:

```
POST /api/v1/combined/python-audit          ← http span, ~50 ms, carries job id
  ⇢ links to
audit.job                                   ← root of the audit's own trace
  ├── audit.python_stages
  │     ├── crawler.universal_snapshot
  │     │     └── crawler.page              ← one per URL: depth, links, outcome
  │     ├── stage.image_audit
  │     │     ├── crawler.image
  │     │     │     └── crawler.page
  │     │     ├── stage.image_audit.ocr_scan
  │     │     ├── rules.alt_text            ← 1.1.1 / 4.1.2 / 1.4.5 / 1.4.11
  │     │     └── rule.1.4.3                ← one per rule converter
  │     └── stage.media_audit
  │           └── rules.media               ← 1.2.1 / 1.2.2 / 1.2.3 / 1.4.2
  ├── audit.node_axe                        ← the Node/axe-core service call
  └── enrichment.run
        └── enrichment.batch
              └── GenerateContent           ← prompt, response, tokens, cost
```

The audit is a *separate trace* linked to the request rather than a child of
it: the submit endpoint answers 202 in milliseconds while the audit runs for
minutes, so nesting would report the job's latency as 50 ms. `session.id` is
the job id on both, which is how Arize groups them.

Errors are recorded even where the engine deliberately swallows them — a failed
stage, an unreachable child page, a Node service that timed out, a Gemini batch
that blew up. Each degrades the audit rather than failing it, so the span is
the only place they show as errors instead of as suspiciously empty results.

Attribute names all live in `ka11y/observability/attributes.py`; filter on
`ka11y.job.id`, `ka11y.stage`, `ka11y.rule`, `ka11y.page.url`, `ka11y.status`.

Two destinations, switched by one variable — see `.env.example` for the full
list.

**Local Phoenix UI (no account needed).** `docker compose up -d phoenix`, then
set `KA11Y_TRACING_BACKEND=phoenix` in the root `.env` and
`docker compose up -d python`. Traces appear live at <http://localhost:6006>.
The compose file already points the python service at `http://phoenix:4317`
(OTLP/gRPC over the `ka11y-net` network — never `localhost`, which inside the
container is the container itself).

**Arize AX.** Leave `KA11Y_TRACING_BACKEND` empty (or set it to `arize`) and
supply credentials in `.env`:

```
ARIZE_SPACE_ID=...
ARIZE_API_KEY=...
ARIZE_PROJECT_NAME=ka11y
```

With credentials set and the backend on `auto`, Arize AX wins — Phoenix only
takes over when you ask for it explicitly, so a shared `.env` can't silently
divert production traces.

The API initialises tracing in its lifespan startup and installs
`TracingMiddleware`; the `enrich_audit.py` CLI initialises it on its own.

Most new work is traced without touching this package. Anything timed through
`ka11y.utils.stage_timing` gets a `stage.*` / `rule.*` span for free, and
anything wrapped in `ka11y.utils.crawler_timing.time_crawler` gets a
`crawler.*` one — so adding a stage or a rule converter the way the existing
ones are written is enough. For anything else:

```python
from ka11y.observability import traced_span, set_span_output

with traced_span("my.step", attributes={"page": url}) as span:
    ...
    set_span_output(span, result)
```

Tracing never fails a run: missing keys, a missing dependency or an unreachable
collector degrade to no-op spans, and every attribute write is swallowed on
error. Span payloads are truncated at `KA11Y_TRACING_MAX_ATTR_CHARS` (8192)
so an oversized attribute can't overrun the collector and drop a whole batch.

## Report export and WCAG technique tags

Every finding in the combined report (pass, fail and needs_review) carries the
WCAG **Situation(s)** and **Technique(s)** that test its success criterion:

```json
{
  "wcag_sc": "2.4.2", "status": "fail", "rule_id": "custom-page-titled",
  "technique_match": "exact",
  "techniques": [
    {"id": "G88", "name": "Providing descriptive titles for Web pages",
     "situations": ["Sufficient"], "cover": "Implemented"}
  ],
  "situations": ["Sufficient"]
}
```

`technique_match` says how the match was made — every tier is specific to the
check that produced the finding; there is no "all techniques of the SC" fallback:

| value | source |
|-------|--------|
| `exact` | the check named the technique (Node custom checks tag issues with `technique: 'G88'`; PDF rules encode it in `python_pdf_<id>`) |
| `reason` | `ka11y/data/rule-techniques.json` → the rule's `by_reason_code` (Python auditors: `missing_alt` → H37) |
| `issue` | `rule-techniques.json` → the rule's `by_issue_type` (Node issue type `horizontal-scroll` → C32/C31/C38) |
| `rule` | `rule-techniques.json` → the rule's check-level `techniques` (what a pass covers) |
| `evidence` | the workbook's *Code Evidence* cites the rule's source file |
| `none` | unmapped — add the rule to `rule-techniques.json` |

`rule-techniques.json` is hand-maintained; entries marked `"review": true` were
authored from the WCAG technique definitions rather than the workbook. Sub-rule
ids (`custom-resize-text-units`) fall back to their base rule's entry.
`ka11y/data/wcag-technique-supplement.json` adds the WCAG 2.2 criteria the
workbook lacks (2.4.11–2.4.13, 2.5.7, 2.5.8, 3.2.6, 3.3.7–3.3.9) and is merged
by the generator. Stored reports are re-tagged on every read, so a mapping fix
applies to existing audits and exports. See `ka11y/accessibility/technique_map.py`.

**Frontend boundary.** `GET /api/v1/combined/{job_id}` — the dashboard's read —
strips `techniques` / `situations` / `technique_match` / `technique_id` from every
finding whose status is not `pass` (`_finalize_job_view` in
`ka11y/api/v1/combined/routes.py`). The stored report, the email, the admin
export and the download endpoint below keep the full data.

**Download endpoint.**

```
GET /api/v1/combined/{job_id}/export?format=json|csv|html|pdf
```

Signed-in owner / organisation member (or any user when PostgreSQL is off).
Builds the file on demand from the stored report with manual-review decisions
applied; the filename is `<host>-accessibility-audit.<format>`.

| format | content |
|--------|---------|
| `json` | the full report, pretty-printed |
| `csv`  | one flat table, one row per (finding, technique): `SC, Criterion, Level, Status, Review Status, Severity, Source, Rule ID, Situation, Technique ID, Technique Name, Technique Cover, Technique Match, Page URL, Element, Reason, Suggested Fix` |
| `html` | the printable report (`ka11y/utils/report_pdf.py`) with Techniques/Situations columns and a "Techniques referenced" legend; every row |
| `pdf`  | the same document rendered by Chromium from the crawler browser pool (503 if rendering is unavailable) |

The dashboard's "Export report" menu (`ka11y-ui/src/components/dashboard/DownloadActions.tsx`)
links straight to this endpoint through the same-origin rewrite in
`ka11y-ui/next.config.ts`.

**Regenerating the technique map.** The tags come from
`ka11y/data/wcag-technique-map.json`, built from the `All Techniques` sheet of
`WCAG_Testing_Report_CodeCoverage.xlsx`. Whenever the workbook changes:

```bash
cd ka11y-python
poetry run python scripts/build_technique_map.py --xlsx ~/Downloads/WCAG_Testing_Report_CodeCoverage.xlsx
```

Run it from a checkout that contains `ka11y-node/` so `rulesGuide.js:<line>`
citations resolve to axe rule ids, then commit the JSON.

## Manual verdicts on "needs review" findings

Findings the engine cannot decide carry ``status: needs_review``. A signed-in
user can adjudicate them; engine ``pass``/``fail`` verdicts cannot be overridden
(the endpoint answers 409).

```
POST /api/v1/combined/{job_id}/findings/{finding_id}/review
{"status": "pass" | "violation" | "needs_review", "note": "optional, ≤2000 chars"}
```

``violation`` is a fail; ``needs_review`` re-opens the item. The verdict is stored
in the SQLite run store (``finding_reviews``, one row per finding, upserted) and
applied as an **overlay** every time the report is read — the automated
``status`` is never rewritten, so ``summary.automated`` always shows the engine's
own counts. On the finding:

| field | meaning |
|-------|---------|
| ``verdict_source`` | ``"manual"`` for a reviewed item, ``"engine"`` for everything else |
| ``review_status`` | ``pass`` / ``violation`` — the bucket the item now sits in |
| ``review_message`` | audit-trail sentence in the report's language: *Reviewed by user and manually changed to Pass.* |
| ``review_note`` | the reviewer's own words, if any |
| ``reviewed_by`` / ``reviewed_at`` | the signed-in user's e-mail (``"user"`` when auth is off) and the UTC timestamp |
| ``reviewed`` / ``manual_review`` | ``true`` on reviewed items / on every needs_review item |

The dashboard's Needs Review page calls this endpoint from "Choose verdict",
re-reads the report and shows the item under Fail or Passes with the
``review_message``. The report export (`…/export?format=json|csv|html|pdf`)
carries the same fields; the CSV has ``Review Status``, ``Verdict Source``,
``Review Message``, ``Review Note``, ``Reviewed By`` and ``Reviewed At`` columns,
and the HTML/PDF tables a ``Review`` column.

