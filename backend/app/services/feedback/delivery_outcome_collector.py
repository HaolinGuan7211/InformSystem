from __future__ import annotations

from backend.app.shared.models import DeliveryLog
from backend.app.services.feedback.repositories.delivery_log_repository import (
    SQLiteDeliveryLogRepository,
)
from backend.app.services.feedback.repositories.sample_repository import (
    SQLiteOptimizationSampleRepository,
)
from backend.app.services.feedback.sample_assembler import SampleAssembler


class DeliveryOutcomeCollector:
    def __init__(
        self,
        delivery_log_repository: SQLiteDeliveryLogRepository,
        sample_assembler: SampleAssembler,
        sample_repository: SQLiteOptimizationSampleRepository,
    ) -> None:
        self._delivery_log_repository = delivery_log_repository
        self._sample_assembler = sample_assembler
        self._sample_repository = sample_repository

    async def collect(self, delivery_log: DeliveryLog) -> None:
        await self._delivery_log_repository.save(delivery_log)
        sample = await self._sample_assembler.build_sample(
            delivery_log.event_id,
            delivery_log.user_id,
            delivery_log=delivery_log,
        )
        if sample is not None:
            await self._sample_repository.save(sample)
