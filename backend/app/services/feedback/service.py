from __future__ import annotations

from typing import Any

from backend.app.shared.models import DeliveryLog, OptimizationSample, UserFeedbackRecord
from backend.app.services.feedback.delivery_outcome_collector import DeliveryOutcomeCollector
from backend.app.services.feedback.exporter import FeedbackExporter
from backend.app.services.feedback.receiver import FeedbackReceiver
from backend.app.services.feedback.repositories.feedback_repository import (
    SQLiteFeedbackRepository,
)
from backend.app.services.feedback.repositories.sample_repository import (
    SQLiteOptimizationSampleRepository,
)
from backend.app.services.feedback.sample_assembler import SampleAssembler


class FeedbackService:
    def __init__(
        self,
        receiver: FeedbackReceiver,
        feedback_repository: SQLiteFeedbackRepository,
        delivery_outcome_collector: DeliveryOutcomeCollector,
        sample_assembler: SampleAssembler,
        sample_repository: SQLiteOptimizationSampleRepository,
        exporter: FeedbackExporter,
    ) -> None:
        self._receiver = receiver
        self._feedback_repository = feedback_repository
        self._delivery_outcome_collector = delivery_outcome_collector
        self._sample_assembler = sample_assembler
        self._sample_repository = sample_repository
        self._exporter = exporter

    async def record_user_feedback(self, payload: dict[str, Any]) -> UserFeedbackRecord:
        record = await self._receiver.receive(payload)
        existing = await self._feedback_repository.get_by_feedback_id(record.feedback_id)
        if existing is not None:
            return existing

        await self._feedback_repository.save(record)
        sample = await self._sample_assembler.build_sample(
            record.event_id,
            record.user_id,
            feedback_record=record,
        )
        if sample is not None:
            await self._sample_repository.save(sample)

        return record

    async def record_delivery_outcome(
        self,
        delivery_log: DeliveryLog,
        *,
        persist_delivery_fact: bool = False,
    ) -> None:
        await self._delivery_outcome_collector.collect(
            delivery_log,
            persist_delivery_fact=persist_delivery_fact,
        )

    async def export_optimization_samples(
        self,
        limit: int = 1000,
        source: str | None = None,
        outcome_label: str | None = None,
    ) -> list[OptimizationSample]:
        return await self._exporter.export(
            limit=limit,
            source=source,
            outcome_label=outcome_label,
        )
