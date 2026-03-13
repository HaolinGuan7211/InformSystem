from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4

from backend.app.services.ai_processing.cache import AICache
from backend.app.services.ai_processing.field_extractor import FieldExtractor
from backend.app.services.ai_processing.model_gateway import ModelGateway, ModelGatewayError
from backend.app.services.ai_processing.models import (
    AICallLog,
    AIAnalysisResult,
    AIModelConfig,
    RuleAnalysisResult,
    UserProfile,
)
from backend.app.services.ai_processing.prompt_builder import PromptBuilder
from backend.app.services.ai_processing.repositories.ai_analysis_repository import (
    SQLiteAIAnalysisRepository,
)
from backend.app.services.ai_processing.result_validator import ResultValidationError, ResultValidator
from backend.app.services.ai_processing.summary_generator import SummaryGenerator
from backend.app.services.ingestion.models import SourceEvent


class AIProcessingService:
    def __init__(
        self,
        prompt_builder: PromptBuilder,
        model_gateway: ModelGateway,
        field_extractor: FieldExtractor,
        summary_generator: SummaryGenerator,
        result_validator: ResultValidator,
        repository: SQLiteAIAnalysisRepository | None = None,
        cache: AICache | None = None,
        model_config: AIModelConfig | None = None,
        timezone: str = "+08:00",
        id_factory: Callable[[], str] | None = None,
        call_id_factory: Callable[[], str] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._prompt_builder = prompt_builder
        self._model_gateway = model_gateway
        self._field_extractor = field_extractor
        self._summary_generator = summary_generator
        self._result_validator = result_validator
        self._repository = repository
        self._cache = cache
        self._model_config = model_config or AIModelConfig(
            provider="mock",
            model_name="gpt-5-mini",
            prompt_version=prompt_builder.prompt_version,
        )
        self._timezone = self._parse_timezone(timezone)
        self._id_factory = id_factory or (lambda: f"ai_{uuid4().hex[:12]}")
        self._call_id_factory = call_id_factory or (lambda: f"call_{uuid4().hex[:12]}")
        self._now_provider = now_provider or (lambda: datetime.now(self._timezone))

    async def analyze(
        self,
        event: SourceEvent,
        rule_result: RuleAnalysisResult,
        user_profile: UserProfile,
    ) -> AIAnalysisResult:
        cache_key = self._build_cache_key(event.event_id, user_profile.user_id)
        cached = await self._get_cached_result(event.event_id, user_profile.user_id, cache_key)
        if cached is not None:
            return cached

        prompt = await self._prompt_builder.build(event, rule_result, user_profile)
        gateway_response = await self._model_gateway.invoke(prompt, self._model_config)
        raw_output = self._coerce_raw_output(gateway_response.content)
        ai_result = AIAnalysisResult(
            ai_result_id=self._id_factory(),
            event_id=event.event_id,
            user_id=user_profile.user_id,
            model_name=gateway_response.model_name or self._model_config.model_name,
            prompt_version=self._model_config.prompt_version,
            summary=await self._summary_generator.summarize(raw_output, fallback_text=event.content_text),
            normalized_category=self._optional_text(raw_output.get("normalized_category")),
            action_items=self._coerce_action_items(raw_output.get("action_items")),
            extracted_fields=await self._field_extractor.extract(raw_output),
            relevance_hint=self._optional_text(raw_output.get("relevance_hint")),
            urgency_hint=self._optional_text(raw_output.get("urgency_hint")),
            risk_hint=self._optional_text(raw_output.get("risk_hint")),
            confidence=self._coerce_confidence(raw_output.get("confidence", rule_result.relevance_score)),
            needs_human_review=bool(raw_output.get("needs_human_review", False)),
            raw_response_ref=gateway_response.raw_response_ref,
            metadata=self._build_result_metadata(rule_result, gateway_response.metadata),
            generated_at=self._now_iso(),
        )
        validated = await self._result_validator.validate(ai_result)

        if self._repository is not None:
            await self._repository.save(validated)
            await self._repository.save_call_log(
                AICallLog(
                    call_id=self._call_id_factory(),
                    event_id=event.event_id,
                    user_id=user_profile.user_id,
                    model_name=validated.model_name,
                    prompt_version=validated.prompt_version,
                    status="success",
                    latency_ms=gateway_response.latency_ms,
                    error_message=None,
                    raw_request_ref=gateway_response.raw_request_ref,
                    raw_response_ref=gateway_response.raw_response_ref,
                    created_at=validated.generated_at,
                )
            )
        if self._cache is not None:
            await self._cache.set(cache_key, validated)
        return validated

    async def analyze_or_fallback(
        self,
        event: SourceEvent,
        rule_result: RuleAnalysisResult,
        user_profile: UserProfile,
    ) -> AIAnalysisResult | None:
        try:
            return await self.analyze(event, rule_result, user_profile)
        except (ModelGatewayError, ResultValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
            if self._repository is not None:
                await self._repository.save_call_log(
                    AICallLog(
                        call_id=self._call_id_factory(),
                        event_id=event.event_id,
                        user_id=user_profile.user_id,
                        model_name=self._model_config.model_name,
                        prompt_version=self._model_config.prompt_version,
                        status="failed",
                        latency_ms=None,
                        error_message=str(exc),
                        raw_request_ref=None,
                        raw_response_ref=None,
                        created_at=self._now_iso(),
                    )
                )
            return None

    async def _get_cached_result(
        self,
        event_id: str,
        user_id: str,
        cache_key: str,
    ) -> AIAnalysisResult | None:
        if self._cache is not None:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                return cached
        if self._repository is None:
            return None
        persisted = await self._repository.get_by_event_and_user(
            event_id,
            user_id,
            model_name=self._model_config.model_name,
            prompt_version=self._model_config.prompt_version,
        )
        if persisted is not None and self._cache is not None:
            await self._cache.set(cache_key, persisted)
        return persisted

    def _build_cache_key(self, event_id: str, user_id: str) -> str:
        return ":".join(
            [
                event_id,
                user_id,
                self._model_config.model_name,
                self._model_config.prompt_version,
            ]
        )

    def _coerce_raw_output(self, content: dict[str, Any] | str | None) -> dict[str, Any]:
        if isinstance(content, dict):
            return content
        if isinstance(content, str):
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise ResultValidationError("Model output must be a JSON object")
            return parsed
        raise ResultValidationError("Model output is empty")

    @staticmethod
    def _coerce_action_items(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        action_items: list[str] = []
        for item in value:
            if not isinstance(item, str):
                continue
            cleaned = item.strip()
            if cleaned and cleaned not in action_items:
                action_items.append(cleaned)
        return action_items

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        cleaned = value.strip()
        return cleaned or None

    @staticmethod
    def _coerce_confidence(value: Any) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(parsed, 1.0))

    def _build_result_metadata(
        self,
        rule_result: RuleAnalysisResult,
        gateway_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        return dict(gateway_metadata)

    def _now_iso(self) -> str:
        return self._now_provider().isoformat()

    @staticmethod
    def _parse_timezone(value: str) -> timezone:
        sign = -1 if value.startswith("-") else 1
        normalized = value[1:] if value[:1] in {"+", "-"} else value
        hours_text, minutes_text = normalized.split(":", maxsplit=1)
        offset = timedelta(hours=int(hours_text), minutes=int(minutes_text))
        return timezone(sign * offset)
