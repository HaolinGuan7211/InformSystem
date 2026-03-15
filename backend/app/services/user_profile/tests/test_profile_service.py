from __future__ import annotations

import pytest

from backend.app.services.user_profile.models import UserProfile


@pytest.mark.asyncio
async def test_upsert_and_build_snapshot_matches_golden_flow(
    user_profile_service,
    load_user_profile_mock,
    load_golden,
) -> None:
    payload = load_user_profile_mock(
        "upstream_inputs",
        "graduation_material_submission__input__manual_profile_request.json",
    )
    await user_profile_service.upsert_profile(UserProfile.model_validate(payload))

    snapshot = await user_profile_service.build_snapshot("stu_001")
    expected = UserProfile.model_validate(load_golden("02_user_profile.json"))

    assert snapshot is not None
    assert snapshot.model_dump() == expected.model_dump()


@pytest.mark.asyncio
async def test_list_active_users_returns_complete_snapshots(
    user_profile_service,
    load_user_profile_mock,
) -> None:
    graduation_user = UserProfile.model_validate(
        load_user_profile_mock(
            "upstream_inputs",
            "graduation_material_submission__input__manual_profile_request.json",
        )
    )
    course_user = UserProfile.model_validate(
        load_user_profile_mock(
            "upstream_inputs",
            "course_schedule_change__input__manual_profile_request.json",
        )
    )

    await user_profile_service.upsert_profile(graduation_user)
    await user_profile_service.upsert_profile(course_user)

    snapshots = await user_profile_service.list_active_users(limit=10)
    snapshots_by_id = {snapshot.user_id: snapshot for snapshot in snapshots}

    assert set(snapshots_by_id) == {"stu_001", "stu_002"}
    assert snapshots_by_id["stu_001"].notification_preference.channels == ["app_push"]
    assert [course.course_id for course in snapshots_by_id["stu_002"].enrolled_courses] == [
        "CS210",
        "CS305",
    ]


@pytest.mark.asyncio
async def test_build_profile_context_returns_minimal_facets(
    user_profile_service,
    load_user_profile_mock,
) -> None:
    graduation_user = UserProfile.model_validate(
        load_user_profile_mock(
            "upstream_inputs",
            "graduation_material_submission__input__manual_profile_request.json",
        )
    )
    await user_profile_service.upsert_profile(graduation_user)
    snapshot = await user_profile_service.build_snapshot("stu_001")

    assert snapshot is not None

    profile_context = await user_profile_service.build_profile_context(
        profile=snapshot,
        required_facets=["identity_core", "graduation_progress"],
        context={"generated_at": "2026-03-13T10:21:30+08:00"},
    )

    assert profile_context.facets == ["identity_core", "graduation_progress"]
    assert set(profile_context.payload) == {"identity_core", "graduation_progress"}
    assert "enrolled_courses" not in profile_context.payload
    assert profile_context.payload["identity_core"]["name"] == "张三"
    assert profile_context.payload["identity_core"]["major"] == "软件工程"
    assert profile_context.payload["graduation_progress"]["graduation_stage"] == "graduation_review"


@pytest.mark.asyncio
async def test_build_light_profile_tags_returns_only_simple_profile_projection(
    user_profile_service,
) -> None:
    await user_profile_service.upsert_profile(
        UserProfile(
            user_id="stu_light",
            student_id="20260004",
            name="赵六",
            college="计算机学院",
            major="软件工程",
            grade="2022",
            degree_level="undergraduate",
            identity_tags=["学生", "毕业生"],
            graduation_stage="graduation_review",
            enrolled_courses=[
                {
                    "course_id": "CS301",
                    "course_name": "操作系统",
                    "teacher": "林老师",
                    "semester": "2025-2026-2",
                },
                {
                    "course_id": "CS302",
                    "course_name": "编译原理",
                    "teacher": "陈老师",
                    "semester": "2025-2026-2",
                },
            ],
            credit_status={
                "program_summary": {"required_total_credits": 160.0},
                "module_progress": [{"module_id": "heavy_module"}],
                "pending_items": [{"item_id": "heavy_pending"}],
                "attention_signals": [{"signal_type": "credit_gap"}],
                "source_snapshot": {"source_system": "szu_ehall_academic_completion"},
            },
            current_tasks=["毕业资格审核", "上传实践材料"],
        )
    )

    snapshot = await user_profile_service.build_snapshot("stu_light")
    assert snapshot is not None

    light_tags = await user_profile_service.build_light_profile_tags(
        profile=snapshot,
        context={"generated_at": "2026-03-15T15:00:00+08:00"},
    )

    assert light_tags.user_id == "stu_light"
    assert light_tags.college == "计算机学院"
    assert light_tags.major == "软件工程"
    assert light_tags.identity_tags == ["学生", "毕业生"]
    assert light_tags.graduation_tags == ["graduation_review", "graduating_student"]
    assert light_tags.current_course_tags == ["操作系统", "编译原理"]
    assert light_tags.current_task_tags == ["毕业资格审核", "上传实践材料"]
    assert light_tags.generated_at == "2026-03-15T15:00:00+08:00"
    assert light_tags.metadata["excluded_heavy_fields"] == [
        "credit_status",
        "full_current_tasks",
        "notification_preference",
    ]
    assert "credit_status" not in light_tags.model_dump()


@pytest.mark.asyncio
async def test_build_light_profile_tags_projects_graduation_stage_into_light_tags(
    user_profile_service,
) -> None:
    await user_profile_service.upsert_profile(
        UserProfile(
            user_id="stu_graduation_light",
            student_id="20260006",
            college="计算机学院",
            major="软件工程",
            grade="2022",
            degree_level="undergraduate",
            identity_tags=["student"],
            graduation_stage="graduation_review",
            current_tasks=["graduation_material_submission"],
        )
    )

    snapshot = await user_profile_service.build_snapshot("stu_graduation_light")
    assert snapshot is not None

    light_tags = await user_profile_service.build_light_profile_tags(profile=snapshot)

    assert light_tags.identity_tags == ["student"]
    assert light_tags.graduation_tags == ["graduation_review", "graduating_student"]
    assert light_tags.current_task_tags == ["graduation_material_submission"]
    assert "credit_status" not in light_tags.model_dump()
    assert "payload" not in light_tags.model_dump()


@pytest.mark.asyncio
async def test_build_profile_context_filters_activity_based_credit_gap(
    user_profile_service,
) -> None:
    await user_profile_service.upsert_profile(
        UserProfile(
            user_id="stu_activity",
            student_id="20260003",
            name="王五",
            college="计算机学院",
            major="软件工程",
            grade="2022",
            degree_level="undergraduate",
            credit_status={
                "program_summary": {
                    "program_name": "2022级软件工程主修培养方案",
                    "required_total_credits": 160.0,
                    "completed_total_credits": 150.0,
                    "outstanding_total_credits": 10.0,
                    "exempted_total_credits": 0.0,
                    "plan_version": "2022",
                },
                "module_progress": [
                    {
                        "module_id": "parent_innovation",
                        "module_name": "创新创业模块",
                        "parent_module_id": None,
                        "parent_module_name": None,
                        "module_level": "parent",
                        "required_credits": 3.0,
                        "completed_credits": 1.0,
                        "outstanding_credits": 2.0,
                        "required_course_count": 2,
                        "completed_course_count": 1,
                        "outstanding_course_count": 1,
                        "completion_status": "in_progress",
                        "attention_tags": ["credit_gap", "activity_based"],
                        "metadata": {},
                    },
                    {
                        "module_id": "child_innovation",
                        "module_name": "创新创业（必修）",
                        "parent_module_id": "parent_innovation",
                        "parent_module_name": "创新创业模块",
                        "module_level": "child",
                        "required_credits": 2.0,
                        "completed_credits": 1.0,
                        "outstanding_credits": 1.0,
                        "required_course_count": 2,
                        "completed_course_count": 1,
                        "outstanding_course_count": 1,
                        "completion_status": "in_progress",
                        "attention_tags": ["credit_gap", "activity_based"],
                        "metadata": {},
                    },
                ],
                "pending_items": [
                    {
                        "item_id": "child_innovation:I001",
                        "item_type": "activity_credit_opportunity",
                        "title": "创新领航讲座",
                        "module_id": "child_innovation",
                        "module_name": "创新创业（必修）",
                        "credits": 1.0,
                        "status": "pending",
                        "priority_hint": "medium",
                        "metadata": {},
                    }
                ],
                "attention_signals": [
                    {
                        "signal_type": "activity_based_credit_gap",
                        "signal_key": "innovation_credit_gap",
                        "signal_value": "1",
                        "severity": "medium",
                        "evidence": ["创新创业（必修）未完成"],
                    }
                ],
                "source_snapshot": {
                    "school_code": "szu",
                    "source_system": "szu_ehall_academic_completion",
                    "synced_at": "2026-03-15T10:00:00+08:00",
                    "source_version": "ehall_academic_completion_v1",
                    "freshness_status": "fresh",
                    "metadata": {},
                },
            },
        )
    )

    snapshot = await user_profile_service.build_snapshot("stu_activity")
    assert snapshot is not None

    profile_context = await user_profile_service.build_profile_context(
        profile=snapshot,
        required_facets=["activity_based_credit_gap"],
        context={"generated_at": "2026-03-15T10:01:00+08:00"},
    )

    activity_payload = profile_context.payload["activity_based_credit_gap"]
    assert len(activity_payload["module_progress"]) == 2
    assert activity_payload["pending_items"][0]["title"] == "创新领航讲座"
    assert activity_payload["attention_signals"][0]["signal_type"] == "activity_based_credit_gap"


@pytest.mark.asyncio
async def test_light_profile_tags_and_profile_context_keep_stage_boundaries(
    user_profile_service,
) -> None:
    await user_profile_service.upsert_profile(
        UserProfile(
            user_id="stu_boundary",
            student_id="20260005",
            college="计算机学院",
            major="软件工程",
            grade="2022",
            degree_level="undergraduate",
            identity_tags=["学生"],
            graduation_stage="graduation_review",
            current_tasks=["毕业资格审核"],
            credit_status={
                "program_summary": {"program_name": "2022级软件工程主修培养方案"},
                "module_progress": [
                    {
                        "module_id": "parent_practice",
                        "module_name": "实践模块",
                        "parent_module_id": None,
                        "parent_module_name": None,
                        "module_level": "parent",
                        "completion_status": "in_progress",
                    },
                    {
                        "module_id": "child_practice",
                        "module_name": "实践类课程",
                        "parent_module_id": "parent_practice",
                        "parent_module_name": "实践模块",
                        "module_level": "child",
                        "completion_status": "in_progress",
                        "attention_tags": ["credit_gap"],
                    },
                ],
                "pending_items": [
                    {
                        "item_id": "practice_001",
                        "item_type": "course_requirement",
                        "title": "毕业论文（设计）",
                        "module_id": "child_practice",
                        "module_name": "实践类课程",
                    }
                ],
                "attention_signals": [
                    {
                        "signal_type": "credit_gap",
                        "signal_key": "practice_credit_gap",
                        "signal_value": "1",
                        "severity": "high",
                        "evidence": ["实践类课程未完成"],
                    }
                ],
                "source_snapshot": {"source_system": "szu_ehall_academic_completion"},
            },
        )
    )

    snapshot = await user_profile_service.build_snapshot("stu_boundary")
    assert snapshot is not None

    light_tags = await user_profile_service.build_light_profile_tags(profile=snapshot)
    profile_context = await user_profile_service.build_profile_context(
        profile=snapshot,
        required_facets=["academic_completion"],
        context={"generated_at": "2026-03-15T15:30:00+08:00"},
    )

    assert light_tags.graduation_tags == ["graduation_review", "graduating_student"]
    assert light_tags.current_task_tags == ["毕业资格审核"]
    assert "academic_completion" not in light_tags.model_dump()
    assert "credit_status" not in light_tags.model_dump()

    assert profile_context.facets == ["academic_completion"]
    assert set(profile_context.payload) == {"academic_completion"}
    assert profile_context.payload["academic_completion"]["program_summary"]["program_name"] == (
        "2022级软件工程主修培养方案"
    )
    assert profile_context.payload["academic_completion"]["pending_items"][0]["title"] == "毕业论文（设计）"
