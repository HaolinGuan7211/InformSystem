from __future__ import annotations

from typing import Any

from backend.app.services.ingestion.connector_manager import ConnectorManager
from backend.app.services.ingestion.deduplicator import Deduplicator
from backend.app.services.ingestion.models import SourceEvent
from backend.app.services.ingestion.repositories.raw_event_repository import RawEventRepository


class IngestionService:
    def __init__(
        self,
        connector_manager: ConnectorManager,
        raw_event_repository: RawEventRepository,
        deduplicator: Deduplicator,
    ) -> None:
        self._connector_manager = connector_manager
        self._raw_event_repository = raw_event_repository
        self._deduplicator = deduplicator

    async def ingest(self, raw_input: dict[str, Any], source_config: dict[str, Any]) -> list[SourceEvent]:
        connector = self._connector_manager.get_connector(source_config["connector_type"])
        normalized_events = await connector.normalize(raw_input, source_config)

        accepted_events: list[SourceEvent] = []
        for event in normalized_events:
            await self._deduplicator.assign_canonical_id(event)
            if await self._deduplicator.is_duplicate(event):
                continue
            accepted_events.append(event)

        await self._raw_event_repository.save_events(accepted_events)
        return accepted_events

    async def ingest_many(
        self,
        raw_inputs: list[dict[str, Any]],
        source_config: dict[str, Any],
    ) -> list[SourceEvent]:
        accepted_events: list[SourceEvent] = []
        for raw_input in raw_inputs:
            accepted_events.extend(await self.ingest(raw_input, source_config))
        return accepted_events

    async def replay(self, event_id: str) -> SourceEvent | None:
        return await self._raw_event_repository.get_event_by_id(event_id)

