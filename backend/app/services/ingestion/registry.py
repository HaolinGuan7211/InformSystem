from __future__ import annotations

from typing import Any

from backend.app.services.ingestion.repositories.source_config_repository import SourceConfigRepository


class SourceRegistry:
    def __init__(self, repository: SourceConfigRepository | Any) -> None:
        self._repository = repository

    async def list_enabled_sources(self) -> list[dict[str, Any]]:
        sources = await self._repository.list_enabled_sources()
        return [self._as_dict(source) for source in sources]

    async def get_source_by_id(self, source_id: str) -> dict[str, Any] | None:
        getter = getattr(self._repository, "get_source_by_id", None) or getattr(
            self._repository,
            "get_source_config",
        )
        source = await getter(source_id)
        return self._as_dict(source)

    def _as_dict(self, source: Any) -> dict[str, Any] | None:
        if source is None:
            return None
        if isinstance(source, dict):
            return source
        if hasattr(source, "model_dump"):
            return source.model_dump(mode="json", exclude_none=True)
        return dict(source)
