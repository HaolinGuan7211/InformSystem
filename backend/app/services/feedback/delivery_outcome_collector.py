from __future__ import annotations

from backend.app.shared.models import DeliveryLog
from backend.app.services.delivery.repositories.delivery_log_repository import (
    DeliveryLogRepository,
)
from backend.app.services.feedback.repositories.sample_repository import (
    SQLiteOptimizationSampleRepository,
)
from backend.app.services.feedback.sample_assembler import SampleAssembler


class DeliveryOutcomeCollector:
    def __init__(
        self,
        delivery_log_repository: DeliveryLogRepository,
        sample_assembler: SampleAssembler,
        sample_repository: SQLiteOptimizationSampleRepository,
    ) -> None:
        self._delivery_log_repository = delivery_log_repository
        self._sample_assembler = sample_assembler
        self._sample_repository = sample_repository

    async def collect(
        self,
        delivery_log: DeliveryLog,
        *,
        persist_delivery_fact: bool = False,
    ) -> None:
        resolved_log = delivery_log
        if persist_delivery_fact:
            existing = await self._delivery_log_repository.get_by_log_id(delivery_log.log_id)
            if existing is None:
                await self._delivery_log_repository.save(delivery_log)
            else:
                resolved_log = existing

        sample = await self._sample_assembler.build_sample(
            resolved_log.event_id,
            resolved_log.user_id,
            delivery_log=resolved_log,
        )
        if sample is not None:
            await self._sample_repository.save(sample)
