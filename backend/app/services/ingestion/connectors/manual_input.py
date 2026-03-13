from __future__ import annotations

from typing import Any

from backend.app.services.ingestion.connectors.base import Connector
from backend.app.services.ingestion.models import SourceEvent
from backend.app.services.ingestion.normalizer import Normalizer


class ManualConnector(Connector):
    def __init__(self, normalizer: Normalizer) -> None:
        self._normalizer = normalizer

    async def normalize(
        self,
        raw_data: dict[str, Any],
        source_config: dict[str, Any],
    ) -> list[SourceEvent]:
        content_text = raw_data.get("content_text")
        if not content_text:
            raise ValueError("Manual input missing content_text")

        consumed_keys = {"source_name", "title", "content_text", "published_at", "author", "attachments", "url"}
        metadata = self._normalizer.extra_metadata(raw_data, consumed_keys)
        event = self._normalizer.build_source_event(
            source_config,
            channel_type=source_config.get("parse_config", {}).get("channel_type", "manual"),
            source_name=raw_data.get("source_name") or source_config["source_name"],
            title=raw_data.get("title"),
            content_text=content_text,
            author=raw_data.get("author"),
            published_at=raw_data.get("published_at"),
            url=raw_data.get("url"),
            attachments=raw_data.get("attachments"),
            metadata=metadata,
        )
        return [event]

