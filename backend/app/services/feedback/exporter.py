from __future__ import annotations

from backend.app.shared.models import OptimizationSample
from backend.app.services.feedback.repositories.sample_repository import (
    SQLiteOptimizationSampleRepository,
)


class FeedbackExporter:
    def __init__(self, sample_repository: SQLiteOptimizationSampleRepository) -> None:
        self._sample_repository = sample_repository

    async def export(
        self,
        limit: int = 1000,
        source: str | None = None,
        outcome_label: str | None = None,
    ) -> list[OptimizationSample]:
        return await self._sample_repository.list(
            limit=limit,
            source=source,
            outcome_label=outcome_label,
        )
