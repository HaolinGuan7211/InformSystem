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
async def test_decision_repository_keeps_append_only_history_and_latest_view(
    decision_repository,
    load_golden,
) -> None:
    first = DecisionResult.model_validate(load_golden("05_decision_result.json"))
    second = first.model_copy(
        update={
            "decision_id": "dec_002",
            "priority_score": 88.0,
            "priority_level": "high",
            "generated_at": "2026-03-13T10:24:00+08:00",
        }
    )

    await decision_repository.save(first)
    await decision_repository.save(second)

    latest = await decision_repository.get_by_event_and_user("evt_001", "stu_001", policy_version="policy_v1")
    history = await decision_repository.list_by_event_and_user("evt_001", "stu_001", policy_version="policy_v1")

    assert latest is not None
    assert latest.decision_id == "dec_002"
    assert [item.decision_id for item in history] == ["dec_002", "dec_001"]


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
    assert result.reason_summary == "毕业审核材料提交通知，与你当前画像缺口匹配，且存在明确截止时间。"
    assert result.metadata == {
        "ai_degraded": True,
        "profile_signal_matches": {
            "attention_signal_keys": [],
            "pending_item_ids": ["pending_practice_001"],
        },
    }
    assert result.explanations[-1] == "AI 不可用时按规则结果降级决策"
    assert all(evidence.source != "ai" for evidence in result.evidences)


@pytest.mark.asyncio
async def test_decision_service_escalates_profile_matched_medium_priority_to_push_high(
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

    assert result.priority_level == "high"
    assert result.decision_action == "push_high"
    assert result.delivery_timing == "immediate"
    assert result.delivery_channels == ["app_push"]
    assert result.reason_summary == "课程安排调整通知，与你当前画像缺口匹配，且需要及时处理。"
    assert result.metadata == {
        "profile_signal_matches": {
            "attention_signal_keys": ["practice_credit_gap"],
            "pending_item_ids": ["pending_practice_001"],
        },
    }


@pytest.mark.asyncio
async def test_decision_service_routes_medium_priority_to_digest_without_profile_gap_match(
    decision_service,
    flow_inputs,
) -> None:
    rule_result = flow_inputs["rule_result"].model_copy(
        update={
            "analysis_id": "rule_digest_clean",
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
            "ai_result_id": "ai_digest_clean",
            "normalized_category": "course_schedule_change",
            "confidence": 0.0,
            "risk_hint": None,
        }
    )
    user_profile = flow_inputs["user_profile"].model_copy(update={"credit_status": {}})

    result = await decision_service.decide(
        flow_inputs["event"].model_copy(update={"event_id": "evt_digest_clean"}),
        user_profile,
        rule_result.model_copy(update={"event_id": "evt_digest_clean"}),
        ai_result.model_copy(update={"event_id": "evt_digest_clean"}),
        context={
            "current_time": "2026-03-13T14:00:00+08:00",
            "generated_at": "2026-03-13T14:00:00+08:00",
        },
    )

    assert result.priority_level == "medium"
    assert result.decision_action == "digest"
    assert result.delivery_timing == "digest_window"
    assert result.delivery_channels == ["app_push"]
    assert result.reason_summary == "课程安排调整通知，与你身份匹配，且需要及时处理。"
    assert result.metadata == {}


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
    assert result.reason_summary == "毕业审核材料提交通知，与你当前画像缺口匹配，且存在明确截止时间。"
    assert result.metadata == {
        "scheduled_for": "2026-03-14T07:00:00+08:00",
        "profile_signal_matches": {
            "attention_signal_keys": [],
            "pending_item_ids": ["pending_practice_001"],
        },
    }


@pytest.mark.asyncio
async def test_decision_service_archives_candidate_when_ai_stage1_marks_irrelevant(
    decision_service,
    flow_inputs,
) -> None:
    user_profile = flow_inputs["user_profile"].model_copy(update={"credit_status": {}})
    rule_result = flow_inputs["rule_result"].model_copy(
        update={
            "analysis_id": "rule_stage1_irrelevant",
            "event_id": "evt_stage1_irrelevant",
            "relevance_status": "unknown",
            "relevance_score": 0.68,
            "action_required": False,
            "deadline_at": None,
            "urgency_level": "low",
            "risk_level": "low",
            "should_invoke_ai": True,
            "explanation": ["规则粗筛命中候选范围"],
        }
    )
    ai_result = flow_inputs["ai_result"].model_copy(
        update={
            "ai_result_id": "ai_stage1_irrelevant",
            "event_id": "evt_stage1_irrelevant",
            "summary": "轻画像粗筛已明确判定无关。",
            "relevance_hint": "irrelevant",
            "urgency_hint": None,
            "risk_hint": None,
            "confidence": 0.86,
            "metadata": {
                "analysis_stage": "stage1",
                "analysis_path": "stage1_terminal",
            },
        }
    )

    result = await decision_service.decide(
        flow_inputs["event"].model_copy(update={"event_id": "evt_stage1_irrelevant"}),
        user_profile,
        rule_result,
        ai_result,
        context={
            "current_time": "2026-03-13T16:00:00+08:00",
            "generated_at": "2026-03-13T16:00:00+08:00",
        },
    )

    assert result.relevance_status == "irrelevant"
    assert result.priority_level == "low"
    assert result.decision_action == "archive"
    assert result.delivery_channels == []
    assert result.reason_summary == "规则粗筛命中候选范围，但 AI 第一阶段粗筛判定当前通知与用户无关，已归档观察。"
    assert "AI 第一阶段粗筛判定当前通知与用户无关" in result.explanations
    assert any(
        evidence.source == "ai" and evidence.key == "relevance_hint" and evidence.value == "irrelevant"
        for evidence in result.evidences
    )


@pytest.mark.asyncio
async def test_decision_service_archives_candidate_when_ai_stage2_marks_irrelevant(
    decision_service,
    flow_inputs,
) -> None:
    user_profile = flow_inputs["user_profile"].model_copy(update={"credit_status": {}})
    rule_result = flow_inputs["rule_result"].model_copy(
        update={
            "analysis_id": "rule_stage2_irrelevant",
            "event_id": "evt_stage2_irrelevant",
            "relevance_status": "unknown",
            "relevance_score": 0.7,
            "action_required": True,
            "deadline_at": None,
            "urgency_level": "medium",
            "risk_level": "medium",
            "should_invoke_ai": True,
            "explanation": ["规则粗筛命中候选范围"],
        }
    )
    ai_result = flow_inputs["ai_result"].model_copy(
        update={
            "ai_result_id": "ai_stage2_irrelevant",
            "event_id": "evt_stage2_irrelevant",
            "summary": "结合重画像后判定当前通知与用户无关。",
            "relevance_hint": "irrelevant",
            "urgency_hint": None,
            "risk_hint": None,
            "confidence": 0.82,
            "metadata": {
                "analysis_stage": "stage2",
                "analysis_path": "stage1_to_stage2",
            },
        }
    )

    result = await decision_service.decide(
        flow_inputs["event"].model_copy(update={"event_id": "evt_stage2_irrelevant"}),
        user_profile,
        rule_result,
        ai_result,
        context={
            "current_time": "2026-03-13T16:30:00+08:00",
            "generated_at": "2026-03-13T16:30:00+08:00",
        },
    )

    assert result.relevance_status == "irrelevant"
    assert result.priority_level == "low"
    assert result.decision_action == "archive"
    assert result.reason_summary == "规则粗筛命中候选范围，但 AI 第二阶段精筛判定当前通知与用户无关，已归档观察。"
    assert "AI 第二阶段精筛判定当前通知与用户无关" in result.explanations


@pytest.mark.asyncio
async def test_decision_service_archives_ai_uncertain_public_info_without_keep_reason(
    decision_service,
    flow_inputs,
) -> None:
    user_profile = flow_inputs["user_profile"].model_copy(update={"credit_status": {}})
    rule_result = flow_inputs["rule_result"].model_copy(
        update={
            "analysis_id": "rule_uncertain_public_info",
            "event_id": "evt_uncertain_public_info",
            "relevance_status": "unknown",
            "relevance_score": 0.2,
            "action_required": False,
            "deadline_at": None,
            "urgency_level": "low",
            "risk_level": "low",
            "should_invoke_ai": True,
            "explanation": ["规则粗筛命中候选范围"],
        }
    )
    ai_result = flow_inputs["ai_result"].model_copy(
        update={
            "ai_result_id": "ai_uncertain_public_info",
            "event_id": "evt_uncertain_public_info",
            "summary": "通知属于一般公共信息，未能确认与当前用户存在明确个人关联。",
            "relevance_hint": "uncertain",
            "urgency_hint": None,
            "risk_hint": None,
            "confidence": 0.61,
            "metadata": {
                "analysis_stage": "stage2",
            },
        }
    )

    result = await decision_service.decide(
        flow_inputs["event"].model_copy(
            update={
                "event_id": "evt_uncertain_public_info",
                "title": "医保知多少―深圳医保异地就医报可以销多少钱？",
                "content_text": "医保知多少―深圳医保异地就医报可以销多少钱？本文介绍医保政策与异地就医报销常见问题。",
            }
        ),
        user_profile,
        rule_result,
        ai_result,
        context={
            "current_time": "2026-03-13T17:00:00+08:00",
            "generated_at": "2026-03-13T17:00:00+08:00",
        },
    )

    assert result.relevance_status == "unknown"
    assert result.priority_level == "low"
    assert result.decision_action == "archive"
    assert result.delivery_timing == "scheduled"
    assert result.reason_summary == "规则粗筛命中候选范围，但 AI 未确认达到保留关注阈值，已归档观察。"
    assert "AI 第二阶段精筛未确认达到保留关注阈值，按归档处理" in result.explanations
    assert "经 AI 精筛确认与你相关" not in result.reason_summary
    assert any(
        evidence.source == "ai" and evidence.key == "relevance_hint" and evidence.value == "uncertain"
        for evidence in result.evidences
    )


@pytest.mark.asyncio
async def test_decision_service_archives_ai_uncertain_teaching_research_unit_task(
    decision_service,
    flow_inputs,
) -> None:
    user_profile = flow_inputs["user_profile"].model_copy(update={"credit_status": {}})
    rule_result = flow_inputs["rule_result"].model_copy(
        update={
            "analysis_id": "rule_uncertain_task_submission",
            "event_id": "evt_uncertain_task_submission",
            "relevance_status": "unknown",
            "relevance_score": 0.45,
            "candidate_categories": [],
            "action_required": True,
            "deadline_at": None,
            "urgency_level": "medium",
            "risk_level": "medium",
            "should_invoke_ai": True,
            "explanation": ["规则粗筛命中候选范围"],
        }
    )
    ai_result = flow_inputs["ai_result"].model_copy(
        update={
            "ai_result_id": "ai_uncertain_task_submission",
            "event_id": "evt_uncertain_task_submission",
            "summary": "通知涉及教学科研单位考核任务指标征集，未能确认与普通学生存在直接个人关系。",
            "normalized_category": "task_submission",
            "relevance_hint": "uncertain",
            "urgency_hint": None,
            "risk_hint": None,
            "confidence": 0.6,
            "metadata": {"analysis_stage": "stage2"},
        }
    )

    result = await decision_service.decide(
        flow_inputs["event"].model_copy(
            update={
                "event_id": "evt_uncertain_task_submission",
                "title": "关于征集2026年度教学科研单位考核任务指标的通知",
                "content_text": "请各教学科研单位按要求报送年度考核任务指标材料。",
            }
        ),
        user_profile,
        rule_result,
        ai_result,
        context={
            "current_time": "2026-03-13T17:10:00+08:00",
            "generated_at": "2026-03-13T17:10:00+08:00",
        },
    )

    assert result.decision_action == "archive"
    assert result.reason_summary == "规则粗筛命中候选范围，但 AI 未确认达到保留关注阈值，已归档观察。"


@pytest.mark.asyncio
async def test_decision_service_archives_ai_uncertain_general_academic_event(
    decision_service,
    flow_inputs,
) -> None:
    user_profile = flow_inputs["user_profile"].model_copy(update={"credit_status": {}})
    rule_result = flow_inputs["rule_result"].model_copy(
        update={
            "analysis_id": "rule_uncertain_academic_event",
            "event_id": "evt_uncertain_academic_event",
            "relevance_status": "unknown",
            "relevance_score": 0.5,
            "candidate_categories": [],
            "action_required": True,
            "deadline_at": None,
            "urgency_level": "medium",
            "risk_level": "medium",
            "should_invoke_ai": True,
            "explanation": ["规则粗筛命中候选范围"],
        }
    )
    ai_result = flow_inputs["ai_result"].model_copy(
        update={
            "ai_result_id": "ai_uncertain_academic_event",
            "event_id": "evt_uncertain_academic_event",
            "summary": "这是一般访问学者信息，未能确认与当前用户存在明确动作关系。",
            "normalized_category": "academic_event",
            "relevance_hint": "uncertain",
            "urgency_hint": None,
            "risk_hint": None,
            "confidence": 0.6,
            "metadata": {"analysis_stage": "stage2"},
        }
    )

    result = await decision_service.decide(
        flow_inputs["event"].model_copy(
            update={
                "event_id": "evt_uncertain_academic_event",
                "title": "访问学者信息：姜清元 助理教授（香港科技大学数学系）",
                "content_text": "介绍访问学者学术背景与研究方向，欢迎感兴趣师生了解。",
            }
        ),
        user_profile,
        rule_result,
        ai_result,
        context={
            "current_time": "2026-03-13T17:20:00+08:00",
            "generated_at": "2026-03-13T17:20:00+08:00",
        },
    )

    assert result.decision_action == "archive"
    assert result.priority_level == "low"


@pytest.mark.asyncio
async def test_decision_service_keeps_ai_uncertain_open_opportunity_with_deadline_in_digest(
    decision_service,
    flow_inputs,
) -> None:
    user_profile = flow_inputs["user_profile"].model_copy(update={"credit_status": {}})
    rule_result = flow_inputs["rule_result"].model_copy(
        update={
            "analysis_id": "rule_uncertain_open_opportunity",
            "event_id": "evt_uncertain_open_opportunity",
            "relevance_status": "unknown",
            "relevance_score": 0.62,
            "candidate_categories": ["student_opportunity", "open_opportunity"],
            "action_required": True,
            "deadline_at": "2026-03-31T23:59:59+08:00",
            "urgency_level": "high",
            "risk_level": "high",
            "should_invoke_ai": True,
            "explanation": ["命中开放机会候选信号", "存在报名与截止时间"],
        }
    )
    ai_result = flow_inputs["ai_result"].model_copy(
        update={
            "ai_result_id": "ai_uncertain_open_opportunity",
            "event_id": "evt_uncertain_open_opportunity",
            "summary": "通知是开放型学生招募机会，但未能确认是否一定值得即时触达。",
            "normalized_category": "open_opportunity",
            "relevance_hint": "uncertain",
            "urgency_hint": None,
            "risk_hint": None,
            "confidence": 0.62,
            "metadata": {"analysis_stage": "stage2"},
        }
    )

    result = await decision_service.decide(
        flow_inputs["event"].model_copy(
            update={
                "event_id": "evt_uncertain_open_opportunity",
                "title": "《中药抗肿瘤纳米药物前沿与科研实践》创新创业短课学生招募公告",
                "content_text": "面向全校学生招募创新创业短课学员，请于3月31日前完成报名。",
            }
        ),
        user_profile,
        rule_result,
        ai_result,
        context={
            "current_time": "2026-03-13T17:30:00+08:00",
            "generated_at": "2026-03-13T17:30:00+08:00",
        },
    )

    assert result.decision_action == "digest"
    assert result.priority_level == "medium"
    assert result.reason_summary == "规则粗筛命中候选范围，且可能值得保留关注（开放机会且存在明确截止时间），但 AI 未确认达到强触达阈值，已进入汇总提醒。"
    assert "保留 digest 的原因：开放机会且存在明确截止时间" in result.explanations
    assert "经 AI 精筛确认与你相关" not in result.reason_summary


@pytest.mark.asyncio
async def test_decision_service_uses_conservative_digest_when_candidate_lacks_ai_result(
    decision_service,
    flow_inputs,
) -> None:
    user_profile = flow_inputs["user_profile"].model_copy(update={"credit_status": {}})
    rule_result = flow_inputs["rule_result"].model_copy(
        update={
            "analysis_id": "rule_candidate_without_ai",
            "event_id": "evt_candidate_without_ai",
            "relevance_status": "unknown",
            "relevance_score": 0.66,
            "action_required": True,
            "deadline_at": None,
            "urgency_level": "medium",
            "risk_level": "low",
            "should_invoke_ai": True,
            "explanation": ["规则粗筛命中候选范围"],
        }
    )

    result = await decision_service.decide(
        flow_inputs["event"].model_copy(update={"event_id": "evt_candidate_without_ai"}),
        user_profile,
        rule_result,
        None,
        context={
            "current_time": "2026-03-13T17:30:00+08:00",
            "generated_at": "2026-03-13T17:30:00+08:00",
        },
    )

    assert result.relevance_status == "unknown"
    assert result.priority_level == "medium"
    assert result.decision_action == "digest"
    assert result.delivery_timing == "digest_window"
    assert result.reason_summary == "规则粗筛命中候选范围，但当前缺少 AI 精筛结果，已按保守策略进入汇总提醒。"
    assert result.metadata == {"ai_degraded": True}
    assert "当前缺少 AI 精筛结果，按保守策略处理" in result.explanations


@pytest.mark.asyncio
async def test_decision_service_turns_unknown_into_positive_only_after_ai_confirms_relevance(
    decision_service,
    flow_inputs,
) -> None:
    user_profile = flow_inputs["user_profile"].model_copy(update={"credit_status": {}})
    rule_result = flow_inputs["rule_result"].model_copy(
        update={
            "analysis_id": "rule_ai_confirmed",
            "event_id": "evt_ai_confirmed",
            "relevance_status": "unknown",
            "relevance_score": 0.92,
            "should_invoke_ai": True,
            "explanation": ["规则粗筛命中候选范围"],
        }
    )
    ai_result = flow_inputs["ai_result"].model_copy(
        update={
            "ai_result_id": "ai_confirmed_relevant",
            "event_id": "evt_ai_confirmed",
            "relevance_hint": "relevant",
            "metadata": {
                "analysis_stage": "stage2",
            },
        }
    )

    result = await decision_service.decide(
        flow_inputs["event"].model_copy(update={"event_id": "evt_ai_confirmed"}),
        user_profile,
        rule_result,
        ai_result,
        context={
            "current_time": "2026-03-13T18:00:00+08:00",
            "generated_at": "2026-03-13T18:00:00+08:00",
        },
    )

    assert result.relevance_status == "relevant"
    assert result.decision_action == "push_high"
    assert result.reason_summary == "毕业审核材料提交通知，经 AI 精筛确认与你相关，且存在明确截止时间。"
    assert "与你可能相关" not in result.reason_summary
    assert "AI 精筛确认与当前用户相关" in result.explanations


@pytest.mark.asyncio
async def test_decision_service_keeps_ai_relevant_open_opportunity_as_digest(
    decision_service,
    flow_inputs,
) -> None:
    user_profile = flow_inputs["user_profile"].model_copy(update={"credit_status": {}})
    rule_result = flow_inputs["rule_result"].model_copy(
        update={
            "analysis_id": "rule_relevant_open_opportunity",
            "event_id": "evt_relevant_open_opportunity",
            "relevance_status": "unknown",
            "relevance_score": 0.58,
            "candidate_categories": ["open_opportunity"],
            "action_required": True,
            "deadline_at": None,
            "urgency_level": "medium",
            "risk_level": "medium",
            "should_invoke_ai": True,
            "explanation": ["命中开放机会候选信号"],
        }
    )
    ai_result = flow_inputs["ai_result"].model_copy(
        update={
            "ai_result_id": "ai_relevant_open_opportunity",
            "event_id": "evt_relevant_open_opportunity",
            "summary": "这是与学生有关的开放型讲座机会。",
            "normalized_category": "open_opportunity",
            "relevance_hint": "relevant",
            "urgency_hint": None,
            "risk_hint": None,
            "confidence": 0.7,
            "metadata": {"analysis_stage": "stage2"},
        }
    )

    result = await decision_service.decide(
        flow_inputs["event"].model_copy(
            update={
                "event_id": "evt_relevant_open_opportunity",
                "title": "荔园杰出学者讲座第三十九期：人工智能时代的数学研究",
                "content_text": "面向全校学生开放报名参加讲座。",
            }
        ),
        user_profile,
        rule_result,
        ai_result,
        context={
            "current_time": "2026-03-13T18:05:00+08:00",
            "generated_at": "2026-03-13T18:05:00+08:00",
        },
    )

    assert result.relevance_status == "relevant"
    assert result.decision_action == "digest"
    assert result.reason_summary == "荔园杰出学者讲座第三十九期：人工智能时代的数学研究，经 AI 精筛确认与你相关，且需要及时处理。"


@pytest.mark.asyncio
async def test_decision_service_keeps_low_priority_ai_confirmed_candidate_in_digest(
    decision_service,
    flow_inputs,
) -> None:
    user_profile = flow_inputs["user_profile"].model_copy(update={"credit_status": {}})
    rule_result = flow_inputs["rule_result"].model_copy(
        update={
            "analysis_id": "rule_ai_confirmed_low",
            "event_id": "evt_ai_confirmed_low",
            "relevance_status": "unknown",
            "relevance_score": 0.1,
            "action_required": False,
            "deadline_at": None,
            "urgency_level": "low",
            "risk_level": "low",
            "should_invoke_ai": True,
            "candidate_categories": [],
            "matched_rules": [],
            "extracted_signals": {},
            "explanation": ["规则粗筛保留候选通知"],
        }
    )
    ai_result = flow_inputs["ai_result"].model_copy(
        update={
            "ai_result_id": "ai_confirmed_relevant_low",
            "event_id": "evt_ai_confirmed_low",
            "normalized_category": None,
            "summary": "AI 精筛确认该通知与当前用户相关，但无需即时触达。",
            "relevance_hint": "relevant",
            "urgency_hint": None,
            "risk_hint": None,
            "confidence": 0.7,
            "metadata": {
                "analysis_stage": "stage2",
            },
        }
    )

    result = await decision_service.decide(
        flow_inputs["event"].model_copy(
            update={
                "event_id": "evt_ai_confirmed_low",
                "title": "低优先级候选通知",
            }
        ),
        user_profile,
        rule_result,
        ai_result,
        context={
            "current_time": "2026-03-13T18:30:00+08:00",
            "generated_at": "2026-03-13T18:30:00+08:00",
        },
    )

    assert result.relevance_status == "relevant"
    assert result.priority_level == "low"
    assert result.decision_action == "digest"
    assert result.delivery_timing == "digest_window"
    assert result.reason_summary == "低优先级候选通知，经 AI 精筛确认与你相关。"


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


@pytest.mark.asyncio
async def test_decision_service_uses_profile_gap_signals_without_ai(
    decision_service,
    flow_inputs,
) -> None:
    event = flow_inputs["event"].model_copy(
        update={
            "event_id": "evt_credit_gap",
            "content_text": "关于实践模块补修与补足学分安排的通知，请相关同学及时处理。",
        }
    )
    user_profile = flow_inputs["user_profile"].model_copy(
        update={
            "credit_status": {
                "program_summary": {
                    "required_total_credits": 160.0,
                    "completed_total_credits": 154.0,
                    "outstanding_total_credits": 6.0,
                },
                "pending_items": [
                    {
                        "item_id": "pending_practice_001",
                        "item_type": "module_credit_gap",
                        "title": "实践模块仍需补足 4 学分",
                        "module_id": "mod_practice",
                        "module_name": "实践模块",
                        "credits": 4.0,
                        "status": "pending",
                        "priority_hint": "high",
                        "metadata": {},
                    }
                ],
                "attention_signals": [
                    {
                        "signal_type": "credit_gap",
                        "signal_key": "practice_credit_gap",
                        "signal_value": "4.0",
                        "severity": "high",
                        "evidence": ["实践模块未完成"],
                    }
                ],
                "source_snapshot": {
                    "freshness_status": "fresh",
                },
            }
        }
    )
    rule_result = flow_inputs["rule_result"].model_copy(
        update={
            "analysis_id": "rule_credit_gap",
            "event_id": "evt_credit_gap",
            "candidate_categories": ["credit"],
            "extracted_signals": {
                "attention_signal_keys": ["practice_credit_gap"],
                "pending_item_ids": ["pending_practice_001"],
                "action_keywords": ["补修", "补足学分"],
            },
            "required_profile_facets": ["academic_completion", "activity_based_credit_gap"],
            "relevance_score": 0.72,
            "action_required": True,
            "deadline_at": None,
            "urgency_level": "medium",
            "risk_level": "medium",
            "should_invoke_ai": True,
            "explanation": ["命中学分缺口通知", "需要补足实践模块学分"],
        }
    )

    result = await decision_service.decide(
        event,
        user_profile,
        rule_result,
        None,
        context={
            "current_time": "2026-03-15T10:00:00+08:00",
            "generated_at": "2026-03-15T10:00:00+08:00",
        },
    )

    assert result.priority_level == "high"
    assert result.decision_action == "push_high"
    assert result.delivery_timing == "immediate"
    assert result.reason_summary == "学分相关通知，与你当前画像缺口匹配，且需要及时处理。"
    assert "命中画像 attention_signals 中的结构化缺口信号" in result.explanations
    assert "命中画像 pending_items 中的待处理缺口项" in result.explanations
    assert result.metadata == {
        "ai_degraded": True,
        "profile_signal_matches": {
            "attention_signal_keys": ["practice_credit_gap"],
            "pending_item_ids": ["pending_practice_001"],
        },
    }
    assert [evidence.source for evidence in result.evidences].count("profile") == 2


@pytest.mark.asyncio
async def test_decision_service_appends_history_for_same_natural_key(
    decision_service,
    decision_repository,
    flow_inputs,
) -> None:
    first = await decision_service.decide(
        flow_inputs["event"],
        flow_inputs["user_profile"],
        flow_inputs["rule_result"],
        flow_inputs["ai_result"],
        context={
            "current_time": "2026-03-13T10:23:00+08:00",
            "generated_at": "2026-03-13T10:23:00+08:00",
        },
    )
    second = await decision_service.decide(
        flow_inputs["event"],
        flow_inputs["user_profile"],
        flow_inputs["rule_result"],
        flow_inputs["ai_result"],
        context={
            "current_time": "2026-03-13T10:25:00+08:00",
            "generated_at": "2026-03-13T10:25:00+08:00",
        },
    )

    history = await decision_repository.list_by_event_and_user("evt_001", "stu_001", policy_version="policy_v1")
    latest = await decision_repository.get_by_event_and_user("evt_001", "stu_001", policy_version="policy_v1")

    assert first.decision_id != second.decision_id
    assert len(history) == 2
    assert latest is not None
    assert latest.decision_id == second.decision_id
