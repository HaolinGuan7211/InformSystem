from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from backend.app.services.ingestion.models import SourceEvent


class Connector(ABC):
    async def fetch(self, source_config: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError(f"{self.__class__.__name__} does not support pull-based fetch")

    @abstractmethod
    async def normalize(
        self,
        raw_data: dict[str, Any],
        source_config: dict[str, Any],
    ) -> list[SourceEvent]:
        raise NotImplementedError

    async def health_check(self, source_config: dict[str, Any]) -> bool:
        return bool(source_config.get("enabled", True))

