from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.app.services.ingestion.connectors.base import Connector
from backend.app.services.ingestion.models import SourceEvent
from backend.app.services.ingestion.normalizer import Normalizer


class WebsiteHtmlConnector(Connector):
    def __init__(self, normalizer: Normalizer) -> None:
        self._normalizer = normalizer

    async def fetch(self, source_config: dict[str, Any]) -> list[dict[str, Any]]:
        if source_config.get("mock_payloads"):
            return list(source_config["mock_payloads"])

        mock_data_path = source_config.get("mock_data_path")
        if not mock_data_path:
            return []

        payload_path = Path(mock_data_path)
        if not payload_path.exists():
            raise FileNotFoundError(f"Mock payload file not found: {payload_path}")

        with payload_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)

        if isinstance(payload, list):
            return payload
        return [payload]

    async def normalize(
        self,
        raw_data: dict[str, Any],
        source_config: dict[str, Any],
    ) -> list[SourceEvent]:
        html_content = raw_data.get("html")
        content_text = raw_data.get("content_text") or self._normalizer.html_to_text(html_content)
        if not content_text:
            raise ValueError("Website payload missing content")

        consumed_keys = {"url", "title", "html", "content_text", "published_at", "attachments", "author"}
        metadata = self._normalizer.extra_metadata(raw_data, consumed_keys)
        event = self._normalizer.build_source_event(
            source_config,
            raw_identifier=raw_data.get("url"),
            channel_type=source_config.get("parse_config", {}).get("channel_type", "website_notice"),
            title=raw_data.get("title"),
            content_text=content_text,
            content_html=html_content,
            author=raw_data.get("author"),
            published_at=raw_data.get("published_at"),
            url=raw_data.get("url"),
            attachments=raw_data.get("attachments"),
            metadata=metadata,
        )
        return [event]

    async def health_check(self, source_config: dict[str, Any]) -> bool:
        mock_data_path = source_config.get("mock_data_path")
        if not mock_data_path:
            return True
        return Path(mock_data_path).exists()

