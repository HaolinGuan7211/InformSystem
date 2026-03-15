from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable
from uuid import uuid4

from backend.app.services.ai_processing.cache import AICache
from backend.app.services.ai_processing.field_extractor import FieldExtractor
from backend.app.services.ai_processing.model_gateway import (
    ModelGateway,
    ModelGatewayError,
)
from backend.app.services.ai_processing.models import (
    AICallLog,
    AIAnalysisResult,
    AIModelConfig,
    AIStage1Result,
    GatewayResponse,
    ProfileContext,
    RuleAnalysisResult,
)
from backend.app.services.ai_processing.prompt_builder import PromptBuilder
from backend.app.services.ai_processing.repositories.ai_analysis_repository import (
    SQLiteAIAnalysisRepository,
)
from backend.app.services.ai_processing.result_validator import (
    ResultValidationError,
    ResultValidator,
)
from backend.app.services.ai_processing.summary_generator import SummaryGenerator
from backend.app.services.ingestion.models import SourceEvent
from backend.app.services.user_profile.light_profile_tag_builder import (
    LightProfileTags,
)


class AIRuntimeDisabledError(RuntimeError):
    pass


class AIProcessingService:
    DISABLED_ERROR_MESSAGE = "AI runtime disabled by configuration"
    _SUPPORTED_PROFILE_FACETS = {
        "identity_core",
        "current_courses",
        "academic_completion",
        "graduation_progress",
        "activity_based_credit_gap",
        "online_platform_credit_gap",
        "custom_watch_items",
        "notification_preference",
    }

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

    @property
    def runtime_enabled(self) -> bool:
        return self._model_config.enabled

    async def analyze(
        self,
        event: SourceEvent,
        rule_result: RuleAnalysisResult,
        profile_context: ProfileContext,
    ) -> AIAnalysisResult:
        if not self._model_config.enabled:
            raise AIRuntimeDisabledError(self.DISABLED_ERROR_MESSAGE)

        profile_context = self._coerce_profile_context(profile_context)
        cache_key = self._build_cache_key(event.event_id, profile_context.user_id)
        cached = await self._get_cached_result(event.event_id, profile_context.user_id, cache_key)
        if cached is not None:
            return cached

        validated, gateway_response = await self._run_stage2(
            event=event,
            rule_result=rule_result,
            profile_context=profile_context,
            stage1_result=None,
        )
        await self._persist_result(
            cache_key=cache_key,
            result=validated,
            gateway_response=gateway_response,
        )
        return validated

    async def analyze_or_fallback(
        self,
        event: SourceEvent,
        rule_result: RuleAnalysisResult,
        profile_context: ProfileContext,
    ) -> AIAnalysisResult | None:
        user_id = self._resolve_profile_user_id(profile_context)
        try:
            return await self.analyze(event, rule_result, profile_context)
        except AIRuntimeDisabledError as exc:
            await self.record_runtime_disabled_skip(event=event, user_id=user_id, error_message=str(exc))
            return None
        except (ModelGatewayError, ResultValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
            await self._save_call_log(
                event_id=event.event_id,
                user_id=user_id,
                model_name=self._model_config.model_name,
                prompt_version=self._model_config.prompt_version,
                status="failed",
                latency_ms=None,
                error_message=str(exc),
                raw_request_ref=None,
                raw_response_ref=None,
                created_at=self._now_iso(),
            )
            return None

    async def analyze_two_stage(
        self,
        event: SourceEvent,
        rule_result: RuleAnalysisResult,
        light_profile_tags: LightProfileTags,
        profile_context_loader: Callable[[list[str]], Awaitable[ProfileContext]],
    ) -> AIAnalysisResult:
        if not self._model_config.enabled:
            raise AIRuntimeDisabledError(self.DISABLED_ERROR_MESSAGE)

        light_profile_tags = self._coerce_light_profile_tags(light_profile_tags)
        cache_key = self._build_cache_key(event.event_id, light_profile_tags.user_id)
        cached = await self._get_cached_result(event.event_id, light_profile_tags.user_id, cache_key)
        if cached is not None:
            return cached

        stage1_result, stage1_gateway_response = await self._run_stage1(
            event=event,
            rule_result=rule_result,
            light_profile_tags=light_profile_tags,
        )
        if stage1_result.relevance_hint_stage1 == "irrelevant":
            terminal_result = await self._build_stage1_terminal_result(
                event=event,
                rule_result=rule_result,
                stage1_result=stage1_result,
                gateway_metadata=stage1_gateway_response.metadata,
            )
            await self._persist_result(
                cache_key=cache_key,
                result=terminal_result,
                gateway_response=stage1_gateway_response,
            )
            return terminal_result

        required_facets = (
            list(stage1_result.required_profile_facets)
            or list(getattr(rule_result, "required_profile_facets", []) or [])
        )
        profile_context = self._coerce_profile_context(await profile_context_loader(required_facets))
        validated, gateway_response = await self._run_stage2(
            event=event,
            rule_result=rule_result,
            profile_context=profile_context,
            stage1_result=stage1_result,
        )
        await self._persist_result(
            cache_key=cache_key,
            result=validated,
            gateway_response=gateway_response,
        )
        return validated

    async def analyze_two_stage_or_fallback(
        self,
        event: SourceEvent,
        rule_result: RuleAnalysisResult,
        light_profile_tags: LightProfileTags,
        profile_context_loader: Callable[[list[str]], Awaitable[ProfileContext]],
    ) -> AIAnalysisResult | None:
        light_profile_tags = self._coerce_light_profile_tags(light_profile_tags)
        try:
            return await self.analyze_two_stage(
                event=event,
                rule_result=rule_result,
                light_profile_tags=light_profile_tags,
                profile_context_loader=profile_context_loader,
            )
        except AIRuntimeDisabledError as exc:
            await self.record_runtime_disabled_skip(
                event=event,
                user_id=light_profile_tags.user_id,
                error_message=str(exc),
            )
            return None
        except (ModelGatewayError, ResultValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
            await self._save_call_log(
                event_id=event.event_id,
                user_id=light_profile_tags.user_id,
                model_name=self._model_config.model_name,
                prompt_version=self._model_config.prompt_version,
                status="failed",
                latency_ms=None,
                error_message=str(exc),
                raw_request_ref=None,
                raw_response_ref=None,
                created_at=self._now_iso(),
            )
            return None

    async def record_runtime_disabled_skip(
        self,
        event: SourceEvent,
        user_id: str,
        error_message: str | None = None,
    ) -> None:
        if self._model_config.enabled:
            return
        await self._save_call_log(
            event_id=event.event_id,
            user_id=user_id,
            model_name=self._model_config.model_name,
            prompt_version=self._model_config.prompt_version,
            status="skipped",
            latency_ms=None,
            error_message=error_message or self.DISABLED_ERROR_MESSAGE,
            raw_request_ref=None,
            raw_response_ref=None,
            created_at=self._now_iso(),
        )

    async def _run_stage1(
        self,
        *,
        event: SourceEvent,
        rule_result: RuleAnalysisResult,
        light_profile_tags: LightProfileTags,
    ) -> tuple[AIStage1Result, GatewayResponse]:
        prompt = await self._prompt_builder.build_stage1(event, rule_result, light_profile_tags)
        gateway_response = await self._invoke_gateway_with_retries(prompt)
        raw_output = self._coerce_raw_output(gateway_response.content)
        stage1_result = AIStage1Result(
            user_id=light_profile_tags.user_id,
            relevance_hint_stage1=self._coerce_stage1_relevance_hint(
                raw_output.get("relevance_hint_stage1")
                or raw_output.get("relevance_status")
                or raw_output.get("relevance_hint")
            ),
            required_profile_facets=self._coerce_profile_facets(
                raw_output.get("required_profile_facets"),
                fallback=rule_result.required_profile_facets,
            ),
            reason_summary_stage1=self._optional_text(
                raw_output.get("reason_summary_stage1")
                or raw_output.get("summary")
                or raw_output.get("reason_summary")
            ),
            confidence=self._coerce_confidence(
                raw_output.get("confidence", rule_result.relevance_score)
            ),
            generated_at=self._now_iso(),
        )
        return stage1_result, gateway_response

    async def _run_stage2(
        self,
        *,
        event: SourceEvent,
        rule_result: RuleAnalysisResult,
        profile_context: ProfileContext,
        stage1_result: AIStage1Result | None,
    ) -> tuple[AIAnalysisResult, GatewayResponse]:
        prompt = await self._prompt_builder.build_stage2(
            event=event,
            rule_result=rule_result,
            profile_context=profile_context,
            stage1_result=stage1_result,
        )
        gateway_response = await self._invoke_gateway_with_retries(prompt)
        raw_output = self._coerce_raw_output(gateway_response.content)
        ai_result = AIAnalysisResult(
            ai_result_id=self._id_factory(),
            event_id=event.event_id,
            user_id=profile_context.user_id,
            model_name=gateway_response.model_name or self._model_config.model_name,
            prompt_version=self._model_config.prompt_version,
            summary=await self._summary_generator.summarize(
                raw_output,
                fallback_text=event.content_text,
            ),
            normalized_category=self._optional_text(raw_output.get("normalized_category")),
            action_items=self._coerce_action_items(raw_output.get("action_items")),
            extracted_fields=await self._field_extractor.extract(raw_output),
            relevance_hint=self._optional_text(raw_output.get("relevance_hint")),
            urgency_hint=self._optional_text(raw_output.get("urgency_hint")),
            risk_hint=self._optional_text(raw_output.get("risk_hint")),
            confidence=self._coerce_confidence(
                raw_output.get("confidence", rule_result.relevance_score)
            ),
            needs_human_review=bool(raw_output.get("needs_human_review", False)),
            raw_response_ref=gateway_response.raw_response_ref,
            metadata={},
            generated_at=self._now_iso(),
        )
        validated = await self._result_validator.validate(ai_result)
        return (
            validated.model_copy(
                update={
                    "metadata": self._build_result_metadata(
                        gateway_metadata=gateway_response.metadata,
                        profile_context=profile_context,
                        stage1_result=stage1_result,
                    )
                }
            ),
            gateway_response,
        )

    async def _build_stage1_terminal_result(
        self,
        *,
        event: SourceEvent,
        rule_result: RuleAnalysisResult,
        stage1_result: AIStage1Result,
        gateway_metadata: dict[str, Any] | None = None,
    ) -> AIAnalysisResult:
        ai_result = AIAnalysisResult(
            ai_result_id=self._id_factory(),
            event_id=event.event_id,
            user_id=stage1_result.user_id,
            model_name=self._model_config.model_name,
            prompt_version=self._model_config.prompt_version,
            summary=stage1_result.reason_summary_stage1 or "轻画像粗筛判定当前通知与用户无关。",
            normalized_category=self._first_category(rule_result),
            action_items=[],
            extracted_fields=[],
            relevance_hint="irrelevant",
            urgency_hint=None,
            risk_hint=None,
            confidence=stage1_result.confidence,
            needs_human_review=False,
            raw_response_ref=None,
            metadata={},
            generated_at=self._now_iso(),
        )
        validated = await self._result_validator.validate(ai_result)
        return validated.model_copy(
            update={
                "metadata": {
                    **(gateway_metadata or {}),
                    "analysis_stage": "stage1",
                    "analysis_path": "stage1_terminal",
                    "stage1_relevance_hint": stage1_result.relevance_hint_stage1,
                    "stage1_required_profile_facets": list(stage1_result.required_profile_facets),
                    "stage1_reason_summary": stage1_result.reason_summary_stage1,
                }
            }
        )

    async def _persist_result(
        self,
        *,
        cache_key: str,
        result: AIAnalysisResult,
        gateway_response: GatewayResponse,
    ) -> None:
        if self._repository is not None:
            await self._repository.save(result)
            await self._save_call_log(
                event_id=result.event_id,
                user_id=result.user_id,
                model_name=result.model_name,
                prompt_version=result.prompt_version,
                status="success",
                latency_ms=gateway_response.latency_ms,
                error_message=None,
                raw_request_ref=gateway_response.raw_request_ref,
                raw_response_ref=gateway_response.raw_response_ref,
                created_at=result.generated_at,
            )
        if self._cache is not None:
            await self._cache.set(cache_key, result)

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

    def _coerce_stage1_relevance_hint(self, value: Any) -> str:
        if not isinstance(value, str):
            return "candidate"
        cleaned = value.strip().lower()
        if cleaned in {"irrelevant", "candidate", "relevant"}:
            return cleaned
        if any(keyword in value for keyword in ("无关", "不相关", "不匹配", "不是目标")):
            return "irrelevant"
        if any(keyword in value for keyword in ("高度相关", "明确相关", "值得继续", "相关")):
            return "relevant"
        return "candidate"

    def _coerce_profile_facets(self, value: Any, fallback: list[str] | None = None) -> list[str]:
        candidates = value if isinstance(value, list) else fallback or []
        facets: list[str] = []
        for item in candidates:
            cleaned = str(item).strip()
            if cleaned and cleaned in self._SUPPORTED_PROFILE_FACETS and cleaned not in facets:
                facets.append(cleaned)
        return facets

    def _build_result_metadata(
        self,
        gateway_metadata: dict[str, Any],
        profile_context: ProfileContext,
        stage1_result: AIStage1Result | None,
    ) -> dict[str, Any]:
        metadata = dict(gateway_metadata)
        for key in ("compat_mode_reason", "context_expansion_reason"):
            if key in profile_context.metadata:
                metadata[key] = profile_context.metadata[key]
        if stage1_result is not None:
            metadata["analysis_stage"] = "stage2"
            metadata["analysis_path"] = "stage1_to_stage2"
            metadata["stage1_relevance_hint"] = stage1_result.relevance_hint_stage1
            metadata["stage1_required_profile_facets"] = list(stage1_result.required_profile_facets)
            metadata["stage1_reason_summary"] = stage1_result.reason_summary_stage1
        return metadata

    async def _invoke_gateway_with_retries(self, prompt: dict[str, Any]) -> GatewayResponse:
        retry_budget = max(0, self._model_config.max_retries)
        for attempt in range(retry_budget + 1):
            try:
                return await self._model_gateway.invoke(prompt, self._model_config)
            except ModelGatewayError:
                if attempt >= retry_budget:
                    raise
        raise ModelGatewayError("Model gateway request failed after retry exhaustion")

    async def _save_call_log(
        self,
        *,
        event_id: str,
        user_id: str,
        model_name: str,
        prompt_version: str,
        status: str,
        latency_ms: int | None,
        error_message: str | None,
        raw_request_ref: str | None,
        raw_response_ref: str | None,
        created_at: str,
    ) -> None:
        if self._repository is None:
            return
        await self._repository.save_call_log(
            AICallLog(
                call_id=self._call_id_factory(),
                event_id=event_id,
                user_id=user_id,
                model_name=model_name,
                prompt_version=prompt_version,
                status=status,
                latency_ms=latency_ms,
                error_message=error_message,
                raw_request_ref=raw_request_ref,
                raw_response_ref=raw_response_ref,
                created_at=created_at,
            )
        )

    def _now_iso(self) -> str:
        return self._now_provider().isoformat()

    @staticmethod
    def _parse_timezone(value: str) -> timezone:
        sign = -1 if value.startswith("-") else 1
        normalized = value[1:] if value[:1] in {"+", "-"} else value
        hours_text, minutes_text = normalized.split(":", maxsplit=1)
        offset = timedelta(hours=int(hours_text), minutes=int(minutes_text))
        return timezone(sign * offset)

    @staticmethod
    def _resolve_profile_user_id(profile_context: ProfileContext | Any) -> str:
        if isinstance(profile_context, ProfileContext):
            return profile_context.user_id
        if isinstance(profile_context, dict):
            return str(profile_context.get("user_id", "unknown"))
        user_id = getattr(profile_context, "user_id", "unknown")
        return str(user_id)

    @staticmethod
    def _coerce_profile_context(profile_context: ProfileContext | Any) -> ProfileContext:
        if isinstance(profile_context, ProfileContext):
            return profile_context
        payload = (
            profile_context.model_dump()
            if hasattr(profile_context, "model_dump")
            else profile_context
        )
        return ProfileContext.model_validate(payload)

    @staticmethod
    def _coerce_light_profile_tags(light_profile_tags: LightProfileTags | Any) -> LightProfileTags:
        if isinstance(light_profile_tags, LightProfileTags):
            return light_profile_tags
        payload = (
            light_profile_tags.model_dump()
            if hasattr(light_profile_tags, "model_dump")
            else light_profile_tags
        )
        return LightProfileTags.model_validate(payload)

    @staticmethod
    def _first_category(rule_result: RuleAnalysisResult) -> str | None:
        for category in rule_result.candidate_categories:
            cleaned = str(category).strip()
            if cleaned:
                return cleaned
        return None
