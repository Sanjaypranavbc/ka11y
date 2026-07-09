from typing import List, Dict, Any, Iterable, Tuple, Optional

from ka11y.crawler.browser_pool import leased_context

from .extractors.element_context_extractor import ElementContextExtractor
from .extractors.semantic_relationship_engine import SemanticRelationshipEngine
from .models import ElementContext
from .decisions.engine import DecisionEngine
from .decisions.policies.policy_1_1_1 import Policy111
from .decisions.policies.policy_1_4_3 import Policy143
from .decisions.policies.policy_1_4_5 import Policy145
from .decisions.policies.policy_1_4_6 import Policy146
from .decisions.policies.policy_1_4_11 import Policy1411
from .formatters.evidence_formatter import EvidenceFormatter
from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="pipeline_stage")


def _build_policies(
    *,
    run_image_audit: bool,
    run_contrast_audit: bool,
) -> Dict[str, Any]:
    """Pick the active WCAG policies for this run.

    Mirrors the previous inline wiring in :func:`_run_pipeline_stage` and is
    shared between the snapshot-driven path and the single-URL fallback.
    """
    policies: Dict[str, Any] = {}
    if run_image_audit:
        policies["1.1.1"] = Policy111()
        policies["1.4.5"] = Policy145()
    if run_contrast_audit:
        policies["1.4.3"] = Policy143()
        policies["1.4.6"] = Policy146()
        policies["1.4.11"] = Policy1411()
    return policies


def _evaluate_pages(
    pages: Iterable[Tuple[str, List[ElementContext]]],
    policies: Dict[str, Any],
    lang: str,
) -> List[Dict[str, Any]]:
    """Run DecisionEngine + EvidenceFormatter against one ``(page_url, contexts)``
    pair at a time and stamp each finding with its originating page URL.

    Doing this per page is the multi-page fix: previously every verdict was
    stamped with the entry URL, so deep pages lost their pipeline findings
    even when contexts had been extracted. Here ``page_url`` is closed over
    each loop iteration so verdicts belong to the page that produced them.
    """
    engine = DecisionEngine(policies)
    out: List[Dict[str, Any]] = []
    for page_url, contexts in pages:
        if not contexts:
            continue
        verdicts: List[Any] = []
        for ctx in contexts:
            verdicts.extend(engine.evaluate_element(ctx))
        if not verdicts:
            continue
        legacy = EvidenceFormatter.to_legacy_findings(verdicts, lang=lang)
        for finding in legacy:
            element = finding.get("element")
            if isinstance(element, dict):
                element["page_url"] = page_url
        out.extend(legacy)
    return out


async def _extract_contexts_for_url(url: str) -> List[ElementContext]:
    """Single-URL fallback used when no universal snapshot was built (e.g.
    image-only audit at depth=0). Opens its own page in the shared browser
    pool, mirroring the legacy behaviour."""
    contexts: List[ElementContext] = []
    async with leased_context() as context:
        page = await context.new_page()
        page.set_default_timeout(30000)
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        contexts = await ElementContextExtractor.extract_contexts(page)
        if contexts:
            await SemanticRelationshipEngine.enrich_semantics(page, contexts)
    return contexts


async def _run_pipeline_stage(
    url: str,
    job_id: str,
    run_image_audit: bool,
    run_contrast_audit: bool = True,
    lang: str = "en",
    snapshot: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """
    Entry point for the Unified Accessibility Pipeline.

    Multi-page behaviour: if ``snapshot`` is provided and carries
    ``pipeline_pages``, DecisionEngine runs against every page's contexts in
    a single CPU pass — no extra browser navigation. Each finding is stamped
    with the originating page's URL.

    Single-page fallback: when no snapshot is available (e.g. an image-only
    audit at ``max_depth=0`` does not build the universal snapshot), the
    extractors run live against ``url`` exactly like before so that path
    remains supported.
    """
    logger.info("Starting Unified Accessibility Pipeline...")
    try:
        policies = _build_policies(
            run_image_audit=run_image_audit,
            run_contrast_audit=run_contrast_audit,
        )
        if not policies:
            return []

        pages: List[Tuple[str, List[ElementContext]]] = []
        snapshot_pages = getattr(snapshot, "pipeline_pages", None) if snapshot else None
        if snapshot_pages:
            total_contexts = 0
            for entry in snapshot_pages:
                page_url = entry.get("page_url") if isinstance(entry, dict) else None
                contexts = entry.get("contexts") if isinstance(entry, dict) else None
                if not page_url or not contexts:
                    continue
                pages.append((page_url, contexts))
                total_contexts += len(contexts)
            logger.info(
                f"Pipeline running against {len(pages)} page(s) "
                f"({total_contexts} contexts) from the universal snapshot."
            )
        else:
            contexts = await _extract_contexts_for_url(url)
            logger.info(
                f"Pipeline single-URL fallback extracted {len(contexts)} contexts."
            )
            pages.append((url, contexts))

        legacy_findings = _evaluate_pages(pages, policies, lang)
        logger.info(f"Pipeline generated {len(legacy_findings)} legacy finding(s).")
        return legacy_findings

    except Exception:
        logger.exception("Unified Pipeline failed")
        return []
