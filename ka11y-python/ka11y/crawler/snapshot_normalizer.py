from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Type

from pydantic import BaseModel, Field, ValidationError

from ka11y.config.logger import setup_logger
from ka11y.crawler.media_crawler import MediaElementData
from ka11y.crawler.universal_page import PageSnapshot
from ka11y.utils.step_logger import ExecutionStepLogger

logger = setup_logger(name="KAC", tag="snapshot_normalizer")


class NormalizedPageSnapshot(BaseModel):
    page_url: str
    media: List[MediaElementData] = Field(default_factory=list)
    warnings: List[Dict[str, Any]] = Field(default_factory=list)
    element_refs: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    page_summaries: List[Dict[str, Any]] = Field(default_factory=list)
    partial: bool = False
    pages_crawled: int = 0
    har_path: str | None = None


class SnapshotNormalizer:
    MODEL_MAP: Dict[str, Type[BaseModel]] = {
        "media": MediaElementData,
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
                    "media": len(normalized.media),
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
            "media": [item.model_dump() for item in snapshot.media],
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
