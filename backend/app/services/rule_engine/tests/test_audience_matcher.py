from __future__ import annotations

import pytest

from backend.app.services.ingestion.models import SourceEvent
from backend.app.services.rule_engine.service import RuleEngineService
from backend.app.services.user_profile.models import CourseInfo, UserProfile


@pytest.mark.asyncio
async def test_graduate_identity_matches_graduation_notice(rule_engine_service: RuleEngineService, source_event, user_profile: UserProfile) -> None:
    result = await rule_engine_service.analyze(source_event, user_profile)

    assert result.relevance_status == "relevant"
    assert result.relevance_score == 0.92
    assert "graduation" in result.candidate_categories


@pytest.mark.asyncio
async def test_non_graduate_profile_is_marked_irrelevant_for_graduate_notice(
    rule_engine_service: RuleEngineService,
    source_event: SourceEvent,
    user_profile: UserProfile,
) -> None:
    non_graduate = user_profile.model_copy(update={"identity_tags": [], "graduation_stage": None})

    result = await rule_engine_service.analyze(source_event, non_graduate)

    assert result.relevance_status == "irrelevant"
    assert result.relevance_score <= 0.2
    assert result.should_continue is True
    assert result.required_profile_facets == []


@pytest.mark.asyncio
async def test_publisher_college_does_not_trigger_hard_reject_without_explicit_audience(
    rule_engine_service: RuleEngineService,
    source_event: SourceEvent,
    user_profile: UserProfile,
) -> None:
    open_notice = source_event.model_copy(
        update={
            "event_id": "evt_open_publisher",
            "source_type": "manual",
            "source_name": "计算机学院",
            "content_text": "计算机学院发布创新创业短课报名通知，欢迎对创新创业感兴趣的同学报名参加。",
            "published_at": "2026-03-15T09:00:00+08:00",
            "collected_at": "2026-03-15T09:00:01+08:00",
            "metadata": {},
        }
    )
    unrelated_college_profile = user_profile.model_copy(update={"college": "外国语学院", "major": "英语"})

    result = await rule_engine_service.analyze(open_notice, unrelated_college_profile)

    assert result.relevance_status == "unknown"
    assert result.should_invoke_ai is True


@pytest.mark.asyncio
async def test_explicit_college_restriction_is_hard_filtered_on_mismatch(
    rule_engine_service: RuleEngineService,
    source_event: SourceEvent,
    user_profile: UserProfile,
) -> None:
    restricted_notice = source_event.model_copy(
        update={
            "event_id": "evt_restricted_college",
            "source_type": "manual",
            "content_text": "仅限计算机学院学生报名参加本次创新创业训练营。",
            "published_at": "2026-03-15T10:00:00+08:00",
            "collected_at": "2026-03-15T10:00:01+08:00",
            "metadata": {},
        }
    )
    unrelated_college_profile = user_profile.model_copy(update={"college": "外国语学院", "major": "英语"})

    result = await rule_engine_service.analyze(restricted_notice, unrelated_college_profile)

    assert result.relevance_status == "irrelevant"
    assert result.relevance_score <= 0.2


@pytest.mark.asyncio
async def test_open_opportunity_notice_prefers_unknown_candidate_state(
    rule_engine_service: RuleEngineService,
    source_event: SourceEvent,
    user_profile: UserProfile,
) -> None:
    open_notice = source_event.model_copy(
        update={
            "event_id": "evt_open_opportunity",
            "source_type": "manual",
            "content_text": "创新创业短课报名开启，欢迎感兴趣的同学自主报名参加。",
            "published_at": "2026-03-15T11:00:00+08:00",
            "collected_at": "2026-03-15T11:00:01+08:00",
            "metadata": {},
        }
    )

    result = await rule_engine_service.analyze(open_notice, user_profile)

    assert result.relevance_status == "unknown"
    assert result.relevance_score < 0.7
    assert result.should_invoke_ai is True
    assert "open_opportunity" in result.candidate_categories
    assert "identity_core" in result.required_profile_facets


@pytest.mark.asyncio
async def test_general_course_launch_notice_with_course_title_stays_unknown(
    rule_engine_service: RuleEngineService,
    source_event: SourceEvent,
    user_profile: UserProfile,
) -> None:
    open_course_notice = source_event.model_copy(
        update={
            "event_id": "evt_general_course_launch",
            "source_type": "manual",
            "content_text": "《人工智能导论》通识课已上线，欢迎感兴趣的同学报名学习。",
            "published_at": "2026-03-16T09:00:00+08:00",
            "collected_at": "2026-03-16T09:00:01+08:00",
            "metadata": {},
        }
    )
    other_course_profile = user_profile.model_copy(
        update={
            "enrolled_courses": [CourseInfo(course_id="course_os", course_name="操作系统", teacher=None, semester="2025-fall")]
        }
    )

    result = await rule_engine_service.analyze(open_course_notice, other_course_profile)

    assert result.relevance_status == "unknown"
    assert result.should_invoke_ai is True
    assert "open_opportunity" in result.candidate_categories


@pytest.mark.asyncio
async def test_research_camp_notice_prefers_unknown_instead_of_hard_reject(
    rule_engine_service: RuleEngineService,
    source_event: SourceEvent,
    user_profile: UserProfile,
) -> None:
    camp_notice = source_event.model_copy(
        update={
            "event_id": "evt_camp_notice",
            "source_type": "manual",
            "content_text": "暑期研习营报名开启，欢迎感兴趣的同学申请参加。",
            "published_at": "2026-03-16T10:00:00+08:00",
            "collected_at": "2026-03-16T10:00:01+08:00",
            "metadata": {},
        }
    )

    result = await rule_engine_service.analyze(camp_notice, user_profile)

    assert result.relevance_status == "unknown"
    assert result.should_invoke_ai is True
    assert "open_opportunity" in result.candidate_categories


@pytest.mark.asyncio
async def test_explicit_graduate_only_notice_is_hard_filtered_for_undergraduate_profile(
    rule_engine_service: RuleEngineService,
    source_event: SourceEvent,
    user_profile: UserProfile,
) -> None:
    graduate_only_notice = source_event.model_copy(
        update={
            "event_id": "evt_graduate_only",
            "source_type": "manual",
            "content_text": "仅限研究生报名参加本次学术工作坊。",
            "published_at": "2026-03-16T11:00:00+08:00",
            "collected_at": "2026-03-16T11:00:01+08:00",
            "metadata": {},
        }
    )
    undergraduate_profile = user_profile.model_copy(
        update={
            "degree_level": "undergraduate",
            "identity_tags": ["student"],
            "graduation_stage": None,
        }
    )

    result = await rule_engine_service.analyze(graduate_only_notice, undergraduate_profile)

    assert result.relevance_status == "irrelevant"
    assert result.relevance_score <= 0.2


@pytest.mark.asyncio
async def test_explicit_course_notice_is_hard_filtered_when_course_does_not_match(
    rule_engine_service: RuleEngineService,
    source_event: SourceEvent,
    user_profile: UserProfile,
) -> None:
    course_notice = source_event.model_copy(
        update={
            "event_id": "evt_course_notice",
            "source_type": "manual",
            "content_text": "《大学英语》课程停课通知，请选课同学知悉。",
            "published_at": "2026-03-15T12:00:00+08:00",
            "collected_at": "2026-03-15T12:00:01+08:00",
            "metadata": {},
        }
    )
    other_course_profile = user_profile.model_copy(
        update={
            "enrolled_courses": [CourseInfo(course_id="course_os", course_name="操作系统", teacher=None, semester="2025-fall")]
        }
    )

    result = await rule_engine_service.analyze(course_notice, other_course_profile)

    assert result.relevance_status == "irrelevant"
    assert result.relevance_score <= 0.2
