from __future__ import annotations

from typing import Any

from backend.app.services.ingestion.connectors.base import Connector
from backend.app.services.ingestion.models import SourceEvent
from backend.app.services.ingestion.normalizer import Normalizer


class WecomWebhookConnector(Connector):
    def __init__(self, normalizer: Normalizer) -> None:
        self._normalizer = normalizer

    async def normalize(
        self,
        raw_data: dict[str, Any],
        source_config: dict[str, Any],
    ) -> list[SourceEvent]:
        text = raw_data.get("text") or raw_data.get("content_text")
        if not text:
            raise ValueError("WeCom payload missing text")

        consumed_keys = {"msgid", "chat_name", "sender", "time", "text", "content_text", "title", "url"}
        metadata = {
            "raw_msgid": raw_data.get("msgid"),
            "chat_name": raw_data.get("chat_name"),
            **self._normalizer.extra_metadata(raw_data, consumed_keys),
        }

        event = self._normalizer.build_source_event(
            source_config,
            raw_identifier=raw_data.get("msgid"),
            source_name=raw_data.get("chat_name") or source_config["source_name"],
            channel_type=source_config.get("parse_config", {}).get("channel_type", "group_message"),
            title=raw_data.get("title"),
            content_text=text,
            author=raw_data.get("sender"),
            published_at=raw_data.get("time"),
            url=raw_data.get("url"),
            metadata=metadata,
        )
        return [event]

