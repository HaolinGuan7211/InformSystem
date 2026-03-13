from __future__ import annotations

import pytest

from backend.app.services.ai_processing.models import AIAnalysisResult, AIExtractedField
from backend.app.services.ai_processing.result_validator import ResultValidationError, ResultValidator


@pytest.mark.asyncio
async def test_result_validator_clamps_confidence_and_marks_review() -> None:
    validator = ResultValidator(low_confidence_threshold=0.6, low_field_confidence_threshold=0.4)
    raw_result = AIAnalysisResult(
        ai_result_id="ai_test",
        event_id="evt_001",
        user_id="stu_001",
        model_name="gpt-5-mini",
        prompt_version="prompt_v1",
        summary="  需要补交材料  ",
        normalized_category=" graduation_material_submission ",
        action_items=["提交材料", "提交材料", " "],
        extracted_fields=[
            AIExtractedField(field_name=" deadline_at ", field_value="2026-03-15T23:59:59+08:00", confidence=-0.2)
        ],
        relevance_hint="  高度相关 ",
        urgency_hint=None,
        risk_hint=None,
        confidence=1.2,
        needs_human_review=False,
        raw_response_ref=" raw_001 ",
        metadata={},
        generated_at="2026-03-13T10:22:00+08:00",
    )

    validated = await validator.validate(raw_result)

    assert validated.confidence == 1.0
    assert validated.extracted_fields[0].confidence == 0.0
    assert validated.needs_human_review is True
    assert validated.summary == "需要补交材料"
    assert validated.normalized_category == "graduation_material_submission"
    assert validated.action_items == ["提交材料"]


@pytest.mark.asyncio
async def test_result_validator_rejects_empty_ai_output() -> None:
    validator = ResultValidator()
    raw_result = AIAnalysisResult(
        ai_result_id="ai_test",
        event_id="evt_001",
        user_id="stu_001",
        model_name="gpt-5-mini",
        prompt_version="prompt_v1",
        summary=None,
        normalized_category=None,
        action_items=[],
        extracted_fields=[],
        relevance_hint=None,
        urgency_hint=None,
        risk_hint=None,
        confidence=0.0,
        needs_human_review=False,
        raw_response_ref=None,
        metadata={},
        generated_at="2026-03-13T10:22:00+08:00",
    )

    with pytest.raises(ResultValidationError):
        await validator.validate(raw_result)
