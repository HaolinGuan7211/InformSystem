from __future__ import annotations

from abc import ABC, abstractmethod

from backend.app.services.ai_processing.models import AIAnalysisResult


class AICache(ABC):
    @abstractmethod
    async def get(self, cache_key: str) -> AIAnalysisResult | None:
        raise NotImplementedError

    @abstractmethod
    async def set(self, cache_key: str, result: AIAnalysisResult) -> None:
        raise NotImplementedError


class MemoryAICache(AICache):
    def __init__(self) -> None:
        self._store: dict[str, AIAnalysisResult] = {}

    async def get(self, cache_key: str) -> AIAnalysisResult | None:
        return self._store.get(cache_key)

    async def set(self, cache_key: str, result: AIAnalysisResult) -> None:
        self._store[cache_key] = result
