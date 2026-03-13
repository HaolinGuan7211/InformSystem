from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from backend.app.services.ingestion.connector_manager import ConnectorManager
from backend.app.services.ingestion.registry import SourceRegistry
from backend.app.services.ingestion.service import IngestionService


class Scheduler:
    def __init__(
        self,
        source_registry: SourceRegistry,
        connector_manager: ConnectorManager,
        ingestion_service: IngestionService,
        *,
        max_failures: int = 3,
        cooldown_minutes: int = 5,
    ) -> None:
        self._source_registry = source_registry
        self._connector_manager = connector_manager
        self._ingestion_service = ingestion_service
        self._max_failures = max_failures
        self._cooldown = timedelta(minutes=cooldown_minutes)
        self._consecutive_failures: dict[str, int] = defaultdict(int)
        self._last_failure_at: dict[str, datetime] = {}
        self._last_status: dict[str, dict[str, str | int]] = {}

    async def run_source(self, source_id: str) -> int:
        source_config = await self._source_registry.get_source_by_id(source_id)
        if source_config is None:
            raise LookupError(f"Unknown source_id: {source_id}")
        if not source_config.get("enabled", True):
            return 0
        if self._circuit_open(source_id):
            raise RuntimeError(f"Source circuit breaker is open: {source_id}")

        connector = self._connector_manager.get_connector(source_config["connector_type"])
        retries = int(source_config.get("max_retries", 1))
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                raw_items = await connector.fetch(source_config)
                accepted_events = await self._ingestion_service.ingest_many(raw_items, source_config)
                self._mark_success(source_id, len(accepted_events))
                return len(accepted_events)
            except Exception as exc:
                last_error = exc
                self._mark_failure(source_id, attempt + 1)
        if last_error is not None:
            raise last_error
        return 0

    async def run_all_enabled_sources(self) -> int:
        total_events = 0
        for source_config in await self._source_registry.list_enabled_sources():
            try:
                total_events += await self.run_source(source_config["source_id"])
            except Exception:
                continue
        return total_events

    def _circuit_open(self, source_id: str) -> bool:
        failures = self._consecutive_failures[source_id]
        if failures < self._max_failures:
            return False
        last_failed_at = self._last_failure_at.get(source_id)
        if last_failed_at is None:
            return False
        return datetime.now(timezone.utc) - last_failed_at < self._cooldown

    def _mark_success(self, source_id: str, accepted: int) -> None:
        self._consecutive_failures[source_id] = 0
        self._last_status[source_id] = {
            "status": "success",
            "accepted": accepted,
        }

    def _mark_failure(self, source_id: str, attempt: int) -> None:
        self._consecutive_failures[source_id] += 1
        self._last_failure_at[source_id] = datetime.now(timezone.utc)
        self._last_status[source_id] = {
            "status": "failed",
            "attempt": attempt,
        }

