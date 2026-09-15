"""
ka11y/observability/attributes.py
=================================
The ka11y span-attribute vocabulary — one place where every attribute name
lives, so a dashboard filter written against ``ka11y.stage`` keeps working no
matter which module emitted the span.

Naming follows OpenTelemetry conventions: lowercase, dot-separated, namespaced
under ``ka11y.`` for our own concepts and under the standard ``http.`` /
``exception.`` prefixes where OTel already defines the meaning (so the generic
back-end views — Arize's HTTP panel, Phoenix's error list — light up without
per-attribute configuration).

Span names are here too. They are part of the observability contract just as
much as the attributes: an alert on ``audit.job`` p95 latency breaks silently
if a call site quietly renames its span, so call sites import these constants
rather than passing literals.
"""

from __future__ import annotations

# ── span names ──────────────────────────────────────────────────────────────
# A complete audit reads, top to bottom:
#
#   GET|POST /api/v1/...                         (the submit call, ~50 ms)
#     └ linked to ──▶ audit.job                  (root of its own trace)
#                       ├ audit.python_stages
#                       │   ├ crawler.universal_snapshot
#                       │   │   └ crawler.page   (one per URL visited)
#                       │   ├ stage.image_audit
#                       │   │   ├ crawler.image
#                       │   │   │   └ crawler.page
#                       │   │   ├ stage.image_audit.ocr_scan
#                       │   │   ├ rules.alt_text (the rule engine's pass)
#                       │   │   └ rule.1.4.3     (one per rule converter)
#                       │   └ stage.media_audit
#                       │       └ rules.media
#                       ├ audit.node_axe
#                       └ enrichment.run
#                           └ enrichment.batch
#                               └ GenerateContent  (google-genai instrumentor)
#
# The crawler.* names are built from the crawler's own label by
# utils.crawler_timing, not from a constant here.
SPAN_HTTP_REQUEST = "http.request"


def http_span_name(method: str, route: str | None) -> str:
    """``POST /api/v1/combined/combined-audit`` — OTel's convention for HTTP
    server spans is "{method} {route template}". The *template* matters: using
    the raw path would give every job id its own span name and shatter the
    latency aggregates that make the panel useful."""
    return f"{method} {route}" if route else f"{method} {SPAN_HTTP_REQUEST}"
SPAN_AUDIT_JOB = "audit.job"
SPAN_PYTHON_STAGES = "audit.python_stages"
SPAN_NODE_AXE = "audit.node_axe"
SPAN_CRAWLER_PAGE = "crawler.page"
SPAN_ENRICHMENT_RUN = "enrichment.run"
SPAN_ENRICHMENT_BATCH = "enrichment.batch"

# Prefixes for the span names built at runtime from a stage / rule id.
SPAN_STAGE_PREFIX = "stage."
SPAN_RULE_PREFIX = "rule."
SPAN_AUDITOR_PREFIX = "rules."


def auditor_span_name(auditor: str) -> str:
    """``rules.alt_text`` — one span for a rule *engine*, which evaluates
    several success criteria over the same input in one pass. Distinct from
    ``rule.<sc>``, which is one criterion's own work."""
    return f"{SPAN_AUDITOR_PREFIX}{auditor}"


def stage_span_name(stage: str, sub_stage: str | None = None) -> str:
    """``stage.image_audit`` / ``stage.image_audit.ocr_scan``."""
    name = f"{SPAN_STAGE_PREFIX}{stage}"
    return f"{name}.{sub_stage}" if sub_stage else name


def rule_span_name(rule: str) -> str:
    """``rule.1.4.3`` — the WCAG success-criterion id, as the rest of the
    codebase spells it (dots, no ``wcag_`` prefix)."""
    return f"{SPAN_RULE_PREFIX}{rule}"


# ── job / run identity ──────────────────────────────────────────────────────
JOB_ID = "ka11y.job.id"
JOB_URL = "ka11y.job.url"
JOB_STATUS = "ka11y.job.status"
JOB_LANG = "ka11y.job.lang"
JOB_WCAG_LEVEL = "ka11y.job.wcag_level"
JOB_MAX_DEPTH = "ka11y.job.max_depth"
JOB_MAX_PAGES = "ka11y.job.max_pages"
JOB_FILTER_RULE = "ka11y.job.filter_rule"
JOB_RERUN_OF = "ka11y.job.rerun_of"
JOB_ACTIVE_STAGES = "ka11y.job.active_stages"
JOB_ERROR_ID = "ka11y.job.error_id"
JOB_ERROR_STAGE = "ka11y.job.error_stage"
JOB_NEEDS_REVIEW_COUNT = "ka11y.job.needs_review_count"
JOB_PASS_COUNT = "ka11y.job.pass_count"
# LLM spend rolled up from the job's enrichment subtree, so a job's cost is
# readable without opening it.
JOB_LLM_TOTAL_TOKENS = "ka11y.job.llm_total_tokens"
JOB_LLM_COST_USD = "ka11y.job.llm_cost_usd"
JOB_LLM_API_CALLS = "ka11y.job.llm_api_calls"

# ── stage / rule execution ──────────────────────────────────────────────────
STAGE = "ka11y.stage"
SUB_STAGE = "ka11y.sub_stage"
RULE = "ka11y.rule"
# The success criteria a rule engine covers in one pass, e.g. "1.1.1,4.1.2".
RULES = "ka11y.rules"
AUDITOR = "ka11y.auditor"
INPUT_COUNT = "ka11y.input_count"
RECORD_COUNT = "ka11y.record_count"
STATUS = "ka11y.status"
ERROR = "ka11y.error"
ITEM_COUNT = "ka11y.item_count"
FINDING_COUNT = "ka11y.finding_count"
VIOLATION_COUNT = "ka11y.violation_count"
DURATION_MS = "ka11y.duration_ms"
# Namespace for a caller's free-form timing extras, so they can't collide with
# a name defined here.
EXTRA_PREFIX = "ka11y.extra."

# ── crawler / page processing ───────────────────────────────────────────────
PAGE_URL = "ka11y.page.url"
PAGE_DEPTH = "ka11y.page.depth"
PAGE_LANG = "ka11y.page.lang"
PAGE_LINKS_FOUND = "ka11y.page.links_found"
PAGE_MEDIA_COUNT = "ka11y.page.media_count"
CRAWLER_NAME = "ka11y.crawler.name"
CRAWLER_PAGES_CRAWLED = "ka11y.crawler.pages_crawled"
CRAWLER_WARNINGS = "ka11y.crawler.warnings"

# ── the Node/axe-core engine ────────────────────────────────────────────────
NODE_ENDPOINT = "ka11y.node.endpoint"
NODE_TIMEOUT_S = "ka11y.node.timeout_s"
NODE_FINDING_COUNT = "ka11y.node.finding_count"

# ── LLM enrichment (alongside the OpenInference llm.* conventions) ──────────
ENRICH_BATCH_INDEX = "enrichment.batch_index"
ENRICH_BATCH_SIZE = "enrichment.batch_size"
ENRICH_VIOLATION_COUNT = "enrichment.violation_count"
ENRICH_LANGUAGE = "enrichment.language"
ENRICH_API_CALLS = "enrichment.api_calls"
ENRICH_RETRIES = "enrichment.retries"
ENRICH_FAILURES = "enrichment.failures"
ENRICH_COST_USD = "enrichment.estimated_cost_usd"
# Token kinds Gemini reports that OpenInference has no standard key for. The
# billable ones (prompt / completion / total) go through set_token_counts().
LLM_TOKEN_COUNT_THOUGHTS = "llm.token_count.thoughts"
LLM_TOKEN_COUNT_CACHED = "llm.token_count.cache_read"
LLM_TOKEN_COUNT_TOOL_USE = "llm.token_count.tool_use"

# ── span events ─────────────────────────────────────────────────────────────
# Point-in-time markers, for things that happen *during* a span rather than
# bounding it.
EVENT_DEGRADED = "ka11y.degraded"
EVENT_BATCHES_FAILED = "enrichment.batches_failed"


# ── HTTP (standard OTel names — do not rename) ──────────────────────────────
HTTP_METHOD = "http.request.method"
HTTP_ROUTE = "http.route"
HTTP_TARGET = "http.target"
HTTP_STATUS_CODE = "http.response.status_code"
HTTP_CLIENT_IP = "client.address"
HTTP_USER_AGENT = "user_agent.original"
HTTP_REQUEST_ID = "ka11y.request.id"

__all__ = [name for name in dir() if name.isupper()] + [
    "auditor_span_name",
    "http_span_name",
    "rule_span_name",
    "stage_span_name",
]
