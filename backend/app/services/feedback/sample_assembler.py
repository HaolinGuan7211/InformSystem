from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from backend.app.services.ai_processing.repositories.ai_analysis_repository import (
    SQLiteAIAnalysisRepository,
)
from backend.app.services.decision_engine.repositories.decision_repository import (
    SQLiteDecisionRepository,
)
from backend.app.services.feedback.repositories.delivery_log_repository import (
    SQLiteDeliveryLogRepository,
)
from backend.app.services.feedback.repositories.feedback_repository import (
    SQLiteFeedbackRepository,
)
from backend.app.services.ingestion.repositories.raw_event_repository import RawEventRepository
from backend.app.services.rule_engine.repositories.rule_analysis_repository import (
    RuleAnalysisRepository,
)
from backend.app.shared.models import DeliveryLog, OptimizationSample, UserFeedbackRecord


class SampleAssembler:
    _FEEDBACK_OUTCOME_MAP = {
        "useful": "useful_delivery",
        "not_relevant": "false_positive",
        "too_late": "late_delivery",
        "too_frequent": "over_delivery",
        "missed_important": "false_negative",
    }
    _DELIVERY_OUTCOME_MAP = {
        "failed": "delivery_failed",
        "skipped": "delivery_skipped",
    }

    def __init__(
        self,
        raw_event_repository: RawEventRepository,
        rule_analysis_repository: RuleAnalysisRepository,
        ai_analysis_repository: SQLiteAIAnalysisRepository,
        decision_repository: SQLiteDecisionRepository,
        delivery_log_repository: SQLiteDeliveryLogRepository,
        feedback_repository: SQLiteFeedbackRepository,
        timezone_offset: str = "+08:00",
    ) -> None:
        self._raw_event_repository = raw_event_repository
        self._rule_analysis_repository = rule_analysis_repository
        self._ai_analysis_repository = ai_analysis_repository
        self._decision_repository = decision_repository
        self._delivery_log_repository = delivery_log_repository
        self._feedback_repository = feedback_repository
        self._timezone_offset = timezone_offset

    async def build_sample(
        self,
        event_id: str,
        user_id: str,
        feedback_record: UserFeedbackRecord | None = None,
        delivery_log: DeliveryLog | None = None,
    ) -> OptimizationSample | None:
        if feedback_record is None:
            feedback_record = await self._feedback_repository.get_latest_by_event_and_user(
                event_id,
                user_id,
            )

        if delivery_log is None:
            if feedback_record is not None and feedback_record.delivery_log_id is not None:
                delivery_log = await self._delivery_log_repository.get_by_log_id(
                    feedback_record.delivery_log_id
                )
            else:
                delivery_log = await self._delivery_log_repository.get_latest_by_event_and_user(
                    event_id,
                    user_id,
                )

        resolved = self._resolve_outcome(feedback_record, delivery_log)
        if resolved is None:
            return None

        source, outcome_label, trigger_ref, generated_at = resolved
        event = await self._raw_event_repository.get_event_by_id(event_id)
        rule_result = await self._rule_analysis_repository.get_by_event_and_user(event_id, user_id)
        ai_result = await self._ai_analysis_repository.get_by_event_and_user(event_id, user_id)
        decision_result = await self._decision_repository.get_by_event_and_user(event_id, user_id)

        return OptimizationSample(
            sample_id=self._build_sample_id(source, event_id, user_id, trigger_ref),
            event_id=event_id,
            user_id=user_id,
            rule_analysis_id=rule_result.analysis_id if rule_result else None,
            ai_result_id=ai_result.ai_result_id if ai_result else None,
            decision_id=decision_result.decision_id if decision_result else None,
            delivery_log_id=delivery_log.log_id if delivery_log else None,
            outcome_label=outcome_label,
            source=source,
            metadata=self._build_metadata(
                event=event,
                rule_result=rule_result,
                ai_result=ai_result,
                decision_result=decision_result,
                feedback_record=feedback_record,
                delivery_log=delivery_log,
            ),
            generated_at=generated_at,
        )

    def _resolve_outcome(
        self,
        feedback_record: UserFeedbackRecord | None,
        delivery_log: DeliveryLog | None,
    ) -> tuple[str, str, str, str] | None:
        if feedback_record is not None:
            outcome_label = self._FEEDBACK_OUTCOME_MAP[feedback_record.feedback_type]
            return (
                "user_feedback",
                outcome_label,
                feedback_record.feedback_id,
                feedback_record.created_at,
            )

        if delivery_log is None:
            return None

        outcome_label = self._DELIVERY_OUTCOME_MAP.get(delivery_log.status)
        if outcome_label is None:
            return None

        return (
            "delivery_outcome",
            outcome_label,
            delivery_log.log_id,
            delivery_log.delivered_at or self._default_timestamp(),
        )

    @staticmethod
    def _build_sample_id(source: str, event_id: str, user_id: str, trigger_ref: str) -> str:
        payload = f"{source}:{event_id}:{user_id}:{trigger_ref}".encode("utf-8")
        return f"sample_{hashlib.sha1(payload).hexdigest()[:12]}"

    @staticmethod
    def _build_metadata(
        event,
        rule_result,
        ai_result,
        decision_result,
        feedback_record: UserFeedbackRecord | None,
        delivery_log: DeliveryLog | None,
    ) -> dict[str, object]:
        metadata: dict[str, object] = {}

        if event is not None:
            metadata["event_title"] = event.title or event.content_text[:80]
            metadata["source_name"] = event.source_name

        if rule_result is not None:
            metadata["rule_relevance_status"] = rule_result.relevance_status
            metadata["rule_categories"] = rule_result.candidate_categories

        if ai_result is not None:
            metadata["normalized_category"] = ai_result.normalized_category
            metadata["ai_confidence"] = ai_result.confidence

        if decision_result is not None:
            metadata["decision_action"] = decision_result.decision_action
            metadata["priority_level"] = decision_result.priority_level

        if feedback_record is not None:
            metadata["feedback_id"] = feedback_record.feedback_id
            metadata["feedback_type"] = feedback_record.feedback_type
            if feedback_record.rating is not None:
                metadata["rating"] = feedback_record.rating
            if feedback_record.comment:
                metadata["comment"] = feedback_record.comment
            if feedback_record.metadata:
                metadata["feedback_metadata"] = feedback_record.metadata

        if delivery_log is not None:
            metadata["delivery_status"] = delivery_log.status
            metadata["delivery_channel"] = delivery_log.channel
            metadata["retry_count"] = delivery_log.retry_count
            if delivery_log.metadata:
                metadata["delivery_metadata"] = delivery_log.metadata

        return {
            key: value
            for key, value in metadata.items()
            if value is not None and value != [] and value != {}
        }

    def _default_timestamp(self) -> str:
        offset = self._parse_timezone_offset(self._timezone_offset)
        return datetime.now(timezone.utc).astimezone(offset).isoformat()

    @staticmethod
    def _parse_timezone_offset(value: str) -> timezone:
        sign = 1 if value.startswith("+") else -1
        hour_text, minute_text = value[1:].split(":", maxsplit=1)
        delta = timedelta(hours=int(hour_text), minutes=int(minute_text))
        return timezone(sign * delta)
