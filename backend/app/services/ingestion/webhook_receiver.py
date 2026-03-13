from __future__ import annotations

from typing import Any

from backend.app.services.ingestion.connector_manager import ConnectorManager
from backend.app.services.ingestion.models import SourceEvent
from backend.app.services.ingestion.registry import SourceRegistry
from backend.app.services.ingestion.service import IngestionService


class WebhookReceiver:
    def __init__(
        self,
        source_registry: SourceRegistry,
        connector_manager: ConnectorManager,
        ingestion_service: IngestionService,
    ) -> None:
        self._source_registry = source_registry
        self._connector_manager = connector_manager
        self._ingestion_service = ingestion_service

    async def receive(self, source_id: str, payload: dict[str, Any]) -> list[SourceEvent]:
        source_config = await self._source_registry.get_source_by_id(source_id)
        if source_config is None:
            raise LookupError(f"Unknown source_id: {source_id}")
        if not source_config.get("enabled", True):
            raise ValueError(f"Source is disabled: {source_id}")

        self._connector_manager.get_connector(source_config["connector_type"])
        self._validate_payload(payload, source_config)
        return await self._ingestion_service.ingest(payload, source_config)

    def _validate_payload(self, payload: dict[str, Any], source_config: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise ValueError("Webhook payload must be a JSON object")
        if not payload.get("text") and not payload.get("content_text"):
            raise ValueError("Webhook payload missing text/content_text")

        auth_config = source_config.get("auth_config", {})
        expected_token = auth_config.get("token")
        require_token = auth_config.get("require_token", False)
        provided_token = payload.get("token") or payload.get("signature")
        if require_token and expected_token and provided_token != expected_token:
            raise PermissionError("Invalid webhook signature")

