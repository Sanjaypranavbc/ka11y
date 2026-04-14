from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Type

from pydantic import BaseModel, ValidationError

from ka11y.config.logger import setup_logger
from ka11y.crawler.forms_crawler import FormInputData
from ka11y.crawler.interactive_crawler import InteractiveElementData
from ka11y.crawler.media_crawler import MediaElementData
from ka11y.crawler.moving_content_crawler import MovingContentData
from ka11y.crawler.sensory_crawler import SensoryElementData
from ka11y.crawler.target_size_crawler import TargetSizeData
from ka11y.crawler.text_spacing_crawler import TextSpacingData
from ka11y.crawler.universal_page import PageSnapshot
from ka11y.utils.step_logger import ExecutionStepLogger

logger = setup_logger(name="KAC", tag="snapshot_normalizer")


@dataclass
class NormalizedPageSnapshot:
    page_url: str
    forms: List[FormInputData] = field(default_factory=list)
    interactive: List[InteractiveElementData] = field(default_factory=list)
    target_sizes: List[TargetSizeData] = field(default_factory=list)
    moving_content: List[MovingContentData] = field(default_factory=list)
    media: List[MediaElementData] = field(default_factory=list)
    text_spacing: List[TextSpacingData] = field(default_factory=list)
    sensory: List[SensoryElementData] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    element_refs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    page_summaries: List[Dict[str, Any]] = field(default_factory=list)
    partial: bool = False
    pages_crawled: int = 0
    har_path: str | None = None


class SnapshotNormalizer:
    MODEL_MAP: Dict[str, Type[BaseModel]] = {
        "forms": FormInputData,
        "interactive": InteractiveElementData,
        "target_sizes": TargetSizeData,
        "moving_content": MovingContentData,
        "media": MediaElementData,
        "text_spacing": TextSpacingData,
        "sensory": SensoryElementData,
    }

    @classmethod
    def normalize(
        cls,
        snapshot: PageSnapshot,
        *,
        output_dir: Path | None = None,
        step_logger: ExecutionStepLogger | None = None,
    ) -> NormalizedPageSnapshot:
        normalized = NormalizedPageSnapshot(
            page_url=snapshot.page_url,
            warnings=list(snapshot.warnings),
            element_refs=dict(snapshot.element_refs),
            page_summaries=list(snapshot.page_summaries),
            partial=snapshot.partial,
            pages_crawled=snapshot.pages_crawled,
            har_path=snapshot.har_path,
        )

        for field_name, model_cls in cls.MODEL_MAP.items():
            items = getattr(snapshot, field_name)
            parsed = cls._parse_items(
                field_name=field_name,
                items=items,
                model_cls=model_cls,
                page_url=snapshot.page_url,
                step_logger=step_logger,
                warnings=normalized.warnings,
            )
            setattr(normalized, field_name, parsed)

        if output_dir:
            cls.save(normalized, output_dir)

        if step_logger:
            step_logger.record(
                step="snapshot_normalizer",
                status="completed",
                message="Normalized universal snapshot into existing crawler models",
                context={
                    "forms": len(normalized.forms),
                    "interactive": len(normalized.interactive),
                    "target_sizes": len(normalized.target_sizes),
                    "moving_content": len(normalized.moving_content),
                    "media": len(normalized.media),
                    "text_spacing": len(normalized.text_spacing),
                    "sensory": len(normalized.sensory),
                    "warnings": len(normalized.warnings),
                },
            )

        return normalized

    @classmethod
    def _parse_items(
        cls,
        *,
        field_name: str,
        items: List[Dict[str, Any]],
        model_cls: Type[BaseModel],
        page_url: str,
        warnings: List[Dict[str, Any]],
        step_logger: ExecutionStepLogger | None,
    ) -> List[Any]:
        parsed: List[Any] = []
        for index, item in enumerate(items):
            payload = dict(item)
            payload.setdefault("page_url", page_url)
            try:
                parsed.append(model_cls(**payload))
            except ValidationError as exc:
                warning = {
                    "code": "normalization_error",
                    "snapshot_field": field_name,
                    "index": index,
                    "message": str(exc),
                }
                warnings.append(warning)
                logger.warning(
                    f"[snapshot_normalizer] skipped invalid {field_name}[{index}]: {exc}"
                )
                if step_logger:
                    step_logger.record(
                        step="snapshot_normalizer",
                        status="warning",
                        message=f"Skipped invalid {field_name} record",
                        context=warning,
                    )
        return parsed

    @staticmethod
    def save(snapshot: NormalizedPageSnapshot, output_dir: Path) -> str:
        path = Path(output_dir) / "universal_snapshot_normalized.json"
        payload = {
            "page_url": snapshot.page_url,
            "forms": [item.model_dump() for item in snapshot.forms],
            "interactive": [item.model_dump() for item in snapshot.interactive],
            "target_sizes": [item.model_dump() for item in snapshot.target_sizes],
            "moving_content": [item.model_dump() for item in snapshot.moving_content],
            "media": [item.model_dump() for item in snapshot.media],
            "text_spacing": [item.model_dump() for item in snapshot.text_spacing],
            "warnings": snapshot.warnings,
            "element_refs": snapshot.element_refs,
            "page_summaries": snapshot.page_summaries,
            "partial": snapshot.partial,
            "pages_crawled": snapshot.pages_crawled,
            "har_path": snapshot.har_path,
        }
        with path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        return str(path)
