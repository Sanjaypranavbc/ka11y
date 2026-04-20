import asyncio
from playwright.async_api import async_playwright, Page
from typing import List, Dict, Any

from .extractors.element_context_extractor import ElementContextExtractor
from .extractors.semantic_relationship_engine import SemanticRelationshipEngine
from .runners.interaction_state_runner import InteractionStateRunner
from .decisions.engine import DecisionEngine
from .decisions.policies.policy_1_1_1 import Policy111
from .decisions.policies.policy_1_3_1 import Policy131
from .decisions.policies.policy_1_4_3 import Policy143
from .decisions.policies.policy_1_4_5 import Policy145
from .decisions.policies.policy_1_4_6 import Policy146
from .decisions.policies.policy_1_4_11 import Policy1411
from .decisions.policies.policy_2_4_7 import Policy247
from .decisions.policies.policy_2_4_13 import Policy2413
from .decisions.policies.policy_2_5_3 import Policy253
from .decisions.policies.policy_2_5_8 import Policy258
from .formatters.evidence_formatter import EvidenceFormatter
from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="pipeline_stage")

async def _run_pipeline_stage(url: str, job_id: str, run_image_audit: bool, run_label_in_name_audit: bool, run_target_size_audit: bool = True, run_focus_audit: bool = True, run_contrast_audit: bool = True) -> List[Dict[str, Any]]:
    """
    Entry point for the new Unified Accessibility Pipeline.
    Evaluates context-aware WCAG rules using rich DOM/Visual context.
    """
    logger.info("Starting Unified Accessibility Pipeline...")
    try:
        legacy_findings = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            
            page.set_default_timeout(30000)
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000) 

            # 1. Extract raw element contexts
            element_contexts = await ElementContextExtractor.extract_contexts(page)
            logger.info(f"Extracted {len(element_contexts)} element contexts.")

            # 2. Enrich with deep semantic relationships
            await SemanticRelationshipEngine.enrich_semantics(page, element_contexts)

            # 3. Enrich with interaction states (e.g., Focus rings)
            if run_focus_audit:
                # Execute batched JS to simulate focus across all interactive nodes natively
                await InteractionStateRunner.batch_evaluate_focus(page, element_contexts)

            await browser.close()

            # 4. Setup Decision Engine with active policies
            policies = {}
            if run_image_audit:
                policies["1.1.1"] = Policy111()
                policies["1.4.5"] = Policy145()
            if run_label_in_name_audit:
                policies["2.5.3"] = Policy253()
                policies["1.3.1"] = Policy131()
            if run_target_size_audit:
                policies["2.5.8"] = Policy258()
            if run_focus_audit:
                policies["2.4.7"] = Policy247()
                policies["2.4.13"] = Policy2413()
            if run_contrast_audit:
                policies["1.4.3"] = Policy143()
                policies["1.4.6"] = Policy146()
                policies["1.4.11"] = Policy1411()
                
            engine = DecisionEngine(policies)

            # 4. Evaluate all elements
            all_verdicts = []
            for ctx in element_contexts:
                verdicts = engine.evaluate_element(ctx)
                all_verdicts.extend(verdicts)

            logger.info(f"Pipeline generated {len(all_verdicts)} verdicts.")

            # 5. Format to legacy schema
            legacy_findings = EvidenceFormatter.to_legacy_findings(all_verdicts)
            
            # Ensure page_url is injected just like other stages
            for finding in legacy_findings:
                if "element" in finding and finding["element"]:
                    finding["element"]["page_url"] = url

            return legacy_findings

    except Exception as e:
        logger.error(f"Unified Pipeline failed: {e}")
        return []
