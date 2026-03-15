from __future__ import annotations

from typing import Any

from backend.app.services.ai_processing.service import AIProcessingService
from backend.app.services.decision_engine.service import DecisionEngineService
from backend.app.services.delivery.service import DeliveryService
from backend.app.services.feedback.service import FeedbackService
from backend.app.services.ingestion.repositories.raw_event_repository import RawEventRepository
from backend.app.services.ingestion.models import SourceEvent
from backend.app.services.rule_engine.service import RuleEngineService
from backend.app.services.user_profile.service import UserProfileService
from backend.app.shared.models import (
    AIAnalysisResult,
    DecisionResult,
    DeliveryLog,
    RuleAnalysisResult,
    UserProfile,
)
from backend.app.workflows.models import WorkflowRunResult, WorkflowUserError, WorkflowUserRun


class WorkflowOrchestrator:
    def __init__(
        self,
        raw_event_repository: RawEventRepository,
        user_profile_service: UserProfileService,
        rule_engine_service: RuleEngineService,
        ai_processing_service: AIProcessingService,
        decision_service: DecisionEngineService,
        delivery_service: DeliveryService,
        feedback_service: FeedbackService | None = None,
    ) -> None:
        self._raw_event_repository = raw_event_repository
        self._user_profile_service = user_profile_service
        self._rule_engine_service = rule_engine_service
        self._ai_processing_service = ai_processing_service
        self._decision_service = decision_service
        self._delivery_service = delivery_service
        self._feedback_service = feedback_service

    async def replay_event(
        self,
        event_id: str,
        user_ids: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> WorkflowRunResult | None:
        event = await self._raw_event_repository.get_event_by_id(event_id)
        if event is None:
            return None
        return await self.run_event(event, user_ids=user_ids, context=context)

    async def run_event(
        self,
        event: SourceEvent,
        user_ids: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> WorkflowRunResult:
        active_users = await self._resolve_candidate_users(user_ids)
        results: list[WorkflowUserRun] = []
        errors: list[WorkflowUserError] = []

        for user_profile in active_users["users"]:
            try:
                user_run = await self._run_for_user(event, user_profile, context=context)
            except Exception as exc:
                errors.append(
                    WorkflowUserError(
                        user_id=user_profile.user_id,
                        stage=self._infer_stage(exc),
                        error_message=str(exc),
                    )
                )
                continue
            results.append(user_run)

        return WorkflowRunResult(
            event=self._normalize_event(event),
            total_candidate_users=active_users["total_candidate_users"],
            processed_user_count=len(results),
            skipped_user_ids=active_users["skipped_user_ids"],
            errors=errors,
            results=results,
        )

    async def _run_for_user(
        self,
        event: SourceEvent,
        user_profile,
        context: dict[str, Any] | None = None,
    ) -> WorkflowUserRun:
        rule_result = await self._rule_engine_service.analyze(
            event=event,
            user_profile=user_profile,
            context=context,
        )
        ai_result = await self._maybe_run_ai(event, user_profile, rule_result, context=context)
        decision_result = await self._decision_service.decide(
            event=event,
            user_profile=user_profile,
            rule_result=rule_result,
            ai_result=ai_result,
            context=context,
        )
        delivery_logs = await self._delivery_service.dispatch(
            decision_result=decision_result,
            event=event,
            user_profile=user_profile,
            context=context,
        )
        await self._record_delivery_outcomes(delivery_logs)

        return WorkflowUserRun(
            user_profile=self._normalize_user_profile(user_profile),
            rule_result=self._normalize_rule_result(rule_result),
            ai_result=self._normalize_ai_result(ai_result),
            decision_result=self._normalize_decision_result(decision_result),
            delivery_logs=[self._normalize_delivery_log(log) for log in delivery_logs],
        )

    async def _maybe_run_ai(
        self,
        event: SourceEvent,
        user_profile,
        rule_result,
        context: dict[str, Any] | None = None,
    ) -> AIAnalysisResult | None:
        if not rule_result.should_continue:
            return None
        if rule_result.relevance_status == "irrelevant":
            return None
        if not rule_result.should_invoke_ai:
            return None
        if not self._ai_processing_service.runtime_enabled:
            await self._ai_processing_service.record_runtime_disabled_skip(
                event=event,
                user_id=user_profile.user_id,
            )
            return None

        light_profile_tags = await self._user_profile_service.build_light_profile_tags(
            profile=user_profile,
            context=context,
        )

        async def _load_profile_context(required_facets: list[str]):
            return await self._user_profile_service.build_profile_context(
                profile=user_profile,
                required_facets=required_facets,
                context=context,
            )

        ai_result = await self._ai_processing_service.analyze_two_stage_or_fallback(
            event=event,
            rule_result=rule_result,
            light_profile_tags=light_profile_tags,
            profile_context_loader=_load_profile_context,
        )
        return self._normalize_ai_result(ai_result)

    async def _record_delivery_outcomes(self, delivery_logs: list[DeliveryLog]) -> None:
        if self._feedback_service is None:
            return
        for log in delivery_logs:
            await self._feedback_service.record_delivery_outcome(log)

    async def _resolve_candidate_users(
        self,
        user_ids: list[str] | None,
    ) -> dict[str, Any]:
        skipped_user_ids: list[str] = []

        if user_ids:
            users: list[Any] = []
            for user_id in user_ids:
                snapshot = await self._user_profile_service.build_snapshot(user_id)
                if snapshot is None:
                    skipped_user_ids.append(user_id)
                    continue
                users.append(snapshot)
            return {
                "users": users,
                "total_candidate_users": len(user_ids),
                "skipped_user_ids": skipped_user_ids,
            }

        users = await self._user_profile_service.list_active_users()
        return {
            "users": users,
            "total_candidate_users": len(users),
            "skipped_user_ids": skipped_user_ids,
        }

    @staticmethod
    def _infer_stage(_: Exception) -> str:
        return "pipeline"

    @staticmethod
    def _normalize_event(event: SourceEvent) -> SourceEvent:
        return SourceEvent.model_validate(event.model_dump())

    @staticmethod
    def _normalize_user_profile(user_profile) -> UserProfile:
        return UserProfile.model_validate(user_profile.model_dump())

    @staticmethod
    def _normalize_rule_result(rule_result) -> RuleAnalysisResult:
        return RuleAnalysisResult.model_validate(rule_result.model_dump())

    @staticmethod
    def _normalize_ai_result(ai_result) -> AIAnalysisResult | None:
        if ai_result is None:
            return None
        return AIAnalysisResult.model_validate(ai_result.model_dump())

    @staticmethod
    def _normalize_decision_result(decision_result) -> DecisionResult:
        return DecisionResult.model_validate(decision_result.model_dump())

    @staticmethod
    def _normalize_delivery_log(delivery_log) -> DeliveryLog:
        return DeliveryLog.model_validate(delivery_log.model_dump())
