from __future__ import annotations

from backend.app.services.ai_processing.models import AIAnalysisResult, AIExtractedField


class ResultValidationError(ValueError):
    pass


class ResultValidator:
    def __init__(
        self,
        low_confidence_threshold: float = 0.6,
        low_field_confidence_threshold: float = 0.4,
    ) -> None:
        self._low_confidence_threshold = low_confidence_threshold
        self._low_field_confidence_threshold = low_field_confidence_threshold

    async def validate(self, ai_result: AIAnalysisResult) -> AIAnalysisResult:
        if not ai_result.model_name.strip():
            raise ResultValidationError("model_name is required")
        if not ai_result.prompt_version.strip():
            raise ResultValidationError("prompt_version is required")
        if not any(
            [
                ai_result.summary,
                ai_result.normalized_category,
                ai_result.action_items,
                ai_result.extracted_fields,
                ai_result.relevance_hint,
                ai_result.urgency_hint,
                ai_result.risk_hint,
            ]
        ):
            raise ResultValidationError("AI output is empty after normalization")

        confidence = self._clamp(ai_result.confidence)
        extracted_fields: list[AIExtractedField] = []
        has_low_field_confidence = False
        for field in ai_result.extracted_fields:
            field_name = field.field_name.strip()
            if not field_name:
                continue
            field_confidence = self._clamp(field.confidence)
            has_low_field_confidence = has_low_field_confidence or (
                field_confidence < self._low_field_confidence_threshold
            )
            extracted_fields.append(
                AIExtractedField(
                    field_name=field_name,
                    field_value=field.field_value,
                    confidence=field_confidence,
                )
            )

        action_items: list[str] = []
        for item in ai_result.action_items:
            cleaned = item.strip()
            if cleaned and cleaned not in action_items:
                action_items.append(cleaned)

        needs_review = (
            ai_result.needs_human_review
            or confidence < self._low_confidence_threshold
            or has_low_field_confidence
        )

        return AIAnalysisResult(
            ai_result_id=ai_result.ai_result_id,
            event_id=ai_result.event_id,
            user_id=ai_result.user_id,
            model_name=ai_result.model_name.strip(),
            prompt_version=ai_result.prompt_version.strip(),
            summary=self._optional_text(ai_result.summary),
            normalized_category=self._optional_text(ai_result.normalized_category),
            action_items=action_items,
            extracted_fields=extracted_fields,
            relevance_hint=self._normalize_relevance_hint(ai_result.relevance_hint),
            urgency_hint=self._optional_text(ai_result.urgency_hint),
            risk_hint=self._optional_text(ai_result.risk_hint),
            confidence=confidence,
            needs_human_review=needs_review,
            raw_response_ref=self._optional_text(ai_result.raw_response_ref),
            metadata=dict(ai_result.metadata),
            generated_at=ai_result.generated_at,
        )

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(float(value), 1.0))

    @staticmethod
    def _optional_text(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    def _normalize_relevance_hint(self, value: str | None) -> str | None:
        cleaned = self._optional_text(value)
        if cleaned is None:
            return None

        normalized = cleaned.lower()
        if normalized in {"relevant", "irrelevant", "uncertain"}:
            return normalized
        if any(token in cleaned for token in ("无关", "不相关", "不匹配", "不是目标", "无需关注")):
            return "irrelevant"
        if any(token in cleaned for token in ("不确定", "待确认", "可能相关", "候选")):
            return "uncertain"
        if any(token in cleaned for token in ("相关", "匹配", "面向", "命中", "适合", "高度相关")):
            return "relevant"
        return "uncertain"
