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
