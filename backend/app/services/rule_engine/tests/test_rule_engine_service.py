from __future__ import annotations

import pytest

from backend.app.services.ingestion.models import SourceEvent
from backend.app.services.rule_engine.models import RuleAnalysisResult
from backend.app.services.rule_engine.service import RuleEngineService
from backend.app.services.user_profile.models import UserProfile


@pytest.mark.asyncio
async def test_rule_engine_matches_golden_flow_semantics(
    rule_engine_service: RuleEngineService,
    source_event: SourceEvent,
    user_profile: UserProfile,
    load_rule_mock,
) -> None:
    result = await rule_engine_service.analyze(
        source_event,
        user_profile,
        context={"generated_at": "2026-03-13T10:21:00+08:00"},
    )
    expected = RuleAnalysisResult.model_validate(
        load_rule_mock("downstream_outputs/graduation_material_submission__output__rule_analysis_result.json")
    )

    assert result.event_id == expected.event_id
    assert result.user_id == expected.user_id
    assert result.rule_version == expected.rule_version
    assert result.candidate_categories == expected.candidate_categories
    assert [rule.rule_id for rule in result.matched_rules] == [rule.rule_id for rule in expected.matched_rules]
    assert result.extracted_signals == expected.extracted_signals
    assert result.relevance_status == expected.relevance_status
    assert result.relevance_score == expected.relevance_score
    assert result.action_required == expected.action_required
    assert result.deadline_at == expected.deadline_at
    assert result.urgency_level == expected.urgency_level
    assert result.risk_level == expected.risk_level
    assert result.should_invoke_ai == expected.should_invoke_ai
    assert result.should_continue == expected.should_continue
    assert result.explanation == expected.explanation


@pytest.mark.asyncio
async def test_rule_engine_result_is_persisted(rule_engine_service: RuleEngineService, source_event: SourceEvent, user_profile: UserProfile) -> None:
    result = await rule_engine_service.analyze(source_event, user_profile)

    stored = await rule_engine_service._repository.get_by_event_and_user(source_event.event_id, user_profile.user_id)
    assert stored is not None
    assert stored.analysis_id == result.analysis_id
    assert stored.relevance_status == result.relevance_status


@pytest.mark.asyncio
async def test_analyze_batch_keeps_single_event_single_result_semantics(
    rule_engine_service: RuleEngineService,
    source_event: SourceEvent,
    user_profile: UserProfile,
) -> None:
    second_event = source_event.model_copy(
        update={
            "event_id": "evt_002",
            "content_text": "计算机学院2022级学生请确认本学期课程安排",
            "collected_at": "2026-03-13T12:00:00+08:00",
        }
    )

    results = await rule_engine_service.analyze_batch([source_event, second_event], user_profile)

    assert len(results) == 2
    assert {result.event_id for result in results} == {"evt_001", "evt_002"}


@pytest.mark.asyncio
async def test_empty_optional_fields_do_not_break_analysis(
    rule_engine_service: RuleEngineService,
    user_profile: UserProfile,
) -> None:
    sparse_event = SourceEvent(
        event_id="evt_sparse",
        source_id="manual_input_default",
        source_type="manual",
        source_name="manual_input",
        channel_type="manual",
        title=None,
        content_text="请及时查看课程通知",
        content_html=None,
        author=None,
        published_at="2026-03-13T09:00:00+08:00",
        collected_at="2026-03-13T09:00:01+08:00",
        url=None,
        attachments=[],
        metadata={},
    )
    sparse_profile = user_profile.model_copy(
        update={
            "college": None,
            "major": None,
            "grade": None,
            "identity_tags": [],
            "current_tasks": [],
        }
    )

    result = await rule_engine_service.analyze(sparse_event, sparse_profile)

    assert result.event_id == "evt_sparse"
    assert result.relevance_status in {"unknown", "irrelevant"}
    assert isinstance(result.explanation, list)
