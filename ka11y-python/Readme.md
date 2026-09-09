# Accessbility Checker Backend API

This is an mimic of a11y of axe-core + lighthouse + visual accessbility test

## Installation
```
poetry install
```

## Observability (Arize tracing)

`ka11y/observability/tracing.py` exports OpenTelemetry traces of the LLM path
to [Arize](https://arize.com). Every Gemini call made by `enrich_audit.py` is
captured as an OpenInference LLM span — prompt, response, model, token counts,
latency, errors — nested under `enrichment.run → enrichment.batch`, with the
audit job id as the Arize session id.

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

The API initialises tracing in its lifespan startup; the `enrich_audit.py` CLI
does it on its own. Wrap any other work in a span with:

```python
from ka11y.observability import traced_span, set_span_output

with traced_span("my.step", attributes={"page": url}) as span:
    ...
    set_span_output(span, result)
```

Tracing never fails a run: missing keys, a missing dependency or an unreachable
collector degrade to no-op spans.
