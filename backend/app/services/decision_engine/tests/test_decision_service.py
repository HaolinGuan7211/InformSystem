from __future__ import annotations

import pytest

from backend.app.shared.models import DecisionResult


@pytest.mark.asyncio
async def test_decision_service_matches_golden_flow(
    decision_service,
    decision_repository,
    flow_inputs,
    load_golden,
) -> None:
    result = await decision_service.decide(
        flow_inputs["event"],
        flow_inputs["user_profile"],
        flow_inputs["rule_result"],
        flow_inputs["ai_result"],
        context={
            "current_time": "2026-03-13T10:23:00+08:00",
            "generated_at": "2026-03-13T10:23:00+08:00",
            "decision_id": "dec_001",
        },
    )
    expected = DecisionResult.model_validate(load_golden("05_decision_result.json"))
    stored = await decision_repository.get_by_event_and_user("evt_001", "stu_001", policy_version="policy_v1")

    assert result.model_dump() == expected.model_dump()
    assert stored is not None
    assert stored.model_dump() == expected.model_dump()


@pytest.mark.asyncio
async def test_decision_service_supports_no_ai_fallback(
    decision_service,
    flow_inputs,
) -> None:
    result = await decision_service.decide(
        flow_inputs["event"],
        flow_inputs["user_profile"],
        flow_inputs["rule_result"],
        None,
        context={
            "current_time": "2026-03-13T10:23:00+08:00",
            "generated_at": "2026-03-13T10:23:00+08:00",
        },
    )

    assert result.decision_action == "push_now"
    assert result.priority_level == "critical"
    assert result.metadata == {"ai_degraded": True}
    assert result.explanations[-1] == "AI 不可用时按规则结果降级决策"
    assert all(evidence.source != "ai" for evidence in result.evidences)


@pytest.mark.asyncio
async def test_decision_service_routes_medium_priority_to_digest(
    decision_service,
    flow_inputs,
) -> None:
    rule_result = flow_inputs["rule_result"].model_copy(
        update={
            "analysis_id": "rule_digest",
            "candidate_categories": ["course_schedule_change"],
            "relevance_score": 0.85,
            "action_required": True,
            "deadline_at": None,
            "urgency_level": "medium",
            "risk_level": "low",
            "should_invoke_ai": False,
            "explanation": ["命中课程调整信号", "存在后续确认动作"],
        }
    )
    ai_result = flow_inputs["ai_result"].model_copy(
        update={
            "ai_result_id": "ai_digest",
            "normalized_category": "course_schedule_change",
            "confidence": 0.0,
            "risk_hint": None,
        }
    )

    result = await decision_service.decide(
        flow_inputs["event"].model_copy(update={"event_id": "evt_digest"}),
        flow_inputs["user_profile"],
        rule_result.model_copy(update={"event_id": "evt_digest"}),
        ai_result.model_copy(update={"event_id": "evt_digest"}),
        context={
            "current_time": "2026-03-13T14:00:00+08:00",
            "generated_at": "2026-03-13T14:00:00+08:00",
        },
    )

    assert result.priority_level == "medium"
    assert result.decision_action == "digest"
    assert result.delivery_timing == "digest_window"
    assert result.delivery_channels == ["app_push"]


@pytest.mark.asyncio
async def test_decision_service_schedules_push_high_during_quiet_hours(
    decision_service,
    flow_inputs,
) -> None:
    rule_result = flow_inputs["rule_result"].model_copy(
        update={
            "analysis_id": "rule_quiet",
            "relevance_score": 0.85,
            "deadline_at": "2026-03-17T09:00:00+08:00",
            "urgency_level": "high",
            "risk_level": "medium",
            "should_invoke_ai": False,
        }
    )

    result = await decision_service.decide(
        flow_inputs["event"].model_copy(update={"event_id": "evt_quiet"}),
        flow_inputs["user_profile"],
        rule_result.model_copy(update={"event_id": "evt_quiet"}),
        None,
        context={
            "current_time": "2026-03-13T23:30:00+08:00",
            "generated_at": "2026-03-13T23:30:00+08:00",
        },
    )

    assert result.priority_level == "high"
    assert result.decision_action == "push_high"
    assert result.delivery_timing == "scheduled"
    assert result.metadata == {"scheduled_for": "2026-03-14T07:00:00+08:00"}


@pytest.mark.asyncio
async def test_decision_service_ignores_irrelevant_or_stopped_flow(
    decision_service,
    flow_inputs,
) -> None:
    rule_result = flow_inputs["rule_result"].model_copy(
        update={
            "analysis_id": "rule_ignore",
            "relevance_status": "irrelevant",
            "relevance_score": 0.05,
            "action_required": False,
            "deadline_at": None,
            "urgency_level": "low",
            "risk_level": "low",
            "should_continue": False,
            "should_invoke_ai": False,
        }
    )

    result = await decision_service.decide(
        flow_inputs["event"].model_copy(update={"event_id": "evt_ignore"}),
        flow_inputs["user_profile"],
        rule_result.model_copy(update={"event_id": "evt_ignore"}),
        None,
        context={
            "current_time": "2026-03-13T15:00:00+08:00",
            "generated_at": "2026-03-13T15:00:00+08:00",
        },
    )

    assert result.decision_action == "ignore"
    assert result.delivery_channels == []
    assert result.reason_summary == "规则层判定该通知与当前用户无关，结束当前处理链路。"
