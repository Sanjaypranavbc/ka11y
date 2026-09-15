"""
ka11y/observability/spans.py
============================
Span shapes shared by more than one part of the engine.

Right now that means page processing. ka11y has two crawlers — the universal
BFS loader (:mod:`ka11y.crawler.universal_page`) and the image crawler's engine
(:mod:`ka11y.crawler.optimized.engine`) — with different code paths but the
same observability question: for each URL we visited, how long did it take and
how did it end? Both emit ``crawler.page`` with the same attributes from here,
so one dashboard panel covers both.

Every function is import-guarded and exception-swallowing, matching the rest of
the package: telemetry never costs an audit.
"""

from __future__ import annotations

import functools
import inspect
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Optional, Sequence

from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="tracing")


@contextmanager
def page_span(
    url: str,
    depth: Optional[int] = None,
    *,
    crawler: Optional[str] = None,
) -> Iterator[Any]:
    """Open ``crawler.page`` around the processing of one URL.

    Yields the span, or None if tracing isn't importable — callers pass the
    result straight to :func:`stamp_page_outcome`, which tolerates None.
    """
    try:
        from . import attributes as attrs
        from .tracing import SpanKind, traced_span
    except Exception:  # noqa: BLE001
        yield None
        return

    with traced_span(
        attrs.SPAN_CRAWLER_PAGE,
        kind=SpanKind.CHAIN,
        attributes={
            attrs.PAGE_URL: url,
            attrs.PAGE_DEPTH: depth,
            attrs.CRAWLER_NAME: crawler,
        },
    ) as span:
        yield span


def stamp_page_outcome(
    span: Any = None,
    *,
    status: Optional[str] = None,
    resolved_url: Optional[str] = None,
    http_status: Optional[int] = None,
    page_lang: Optional[str] = None,
    element_count: Optional[int] = None,
    links_found: Optional[int] = None,
    media_count: Optional[int] = None,
    warnings: Optional[int] = None,
    error: Optional[str] = None,
) -> None:
    """Record how one page ended on its span.

    ``span=None`` targets the current span, which is what the crawlers use:
    the outcome is known deep inside the call stack (in a JSON writer, or after
    a redirect resolves), far from where the span was opened.

    A page that failed or was skipped is marked ERROR, because a crawl that
    quietly visits nothing is the failure mode this instrumentation exists to
    catch — the audit itself carries on regardless.
    """
    try:
        from . import attributes as attrs
        from .tracing import current_span, set_span_attributes

        target = span if span is not None else current_span()
        set_span_attributes(
            target,
            {
                attrs.STATUS: status,
                attrs.PAGE_URL: resolved_url,
                attrs.PAGE_LANG: page_lang,
                attrs.HTTP_STATUS_CODE: http_status,
                attrs.PAGE_LINKS_FOUND: links_found,
                attrs.PAGE_MEDIA_COUNT: media_count,
                attrs.ITEM_COUNT: element_count,
                attrs.CRAWLER_WARNINGS: warnings,
                attrs.ERROR: error,
            },
        )
        if status in ("failed", "skipped", "error"):
            from opentelemetry.trace import Status, StatusCode

            target.set_status(
                Status(StatusCode.ERROR, error or f"page {status}")
            )
    except Exception:  # noqa: BLE001
        logger.debug("could not stamp page outcome", exc_info=True)


def traced_auditor(
    auditor: str,
    *,
    rules: Sequence[str] = (),
    input_arg: Optional[str] = None,
):
    """Wrap a synchronous rule-engine entry point in a ``rules.<name>`` span.

    The auditors run on a worker thread (``asyncio.to_thread``), which copies
    the caller's context, so the span still lands under the stage that
    dispatched it — no explicit propagation needed.

    ``rules`` records which success criteria the pass evaluates: an auditor
    covers several at once (alt-text does 1.1.1, 4.1.2, 1.4.5 and 1.4.11 in a
    single sweep), so a per-criterion span would be a fiction. ``input_arg``
    names the parameter holding the work items, so the span can report how
    much input produced how many records — the ratio that tells you a crawl
    came back empty rather than the rules being slow.
    """

    def decorator(fn: Callable) -> Callable:
        signature = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                from . import attributes as attrs
                from .tracing import SpanKind, set_span_attributes, traced_span
            except Exception:  # noqa: BLE001
                return fn(*args, **kwargs)

            input_count = None
            if input_arg:
                try:
                    bound = signature.bind_partial(*args, **kwargs)
                    bound.apply_defaults()
                    value = bound.arguments.get(input_arg)
                    input_count = len(value) if value is not None else None
                except (TypeError, AttributeError):
                    input_count = None

            with traced_span(
                attrs.auditor_span_name(auditor),
                kind=SpanKind.TOOL,
                attributes={
                    attrs.AUDITOR: auditor,
                    attrs.RULES: ",".join(rules) or None,
                    attrs.INPUT_COUNT: input_count,
                },
            ) as span:
                records = fn(*args, **kwargs)
                try:
                    set_span_attributes(
                        span, {attrs.RECORD_COUNT: len(records)}
                    )
                except TypeError:
                    pass
                return records

        return wrapper

    return decorator


__all__ = ["page_span", "stamp_page_outcome", "traced_auditor"]
