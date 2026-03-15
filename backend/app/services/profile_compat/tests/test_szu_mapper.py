from __future__ import annotations

from backend.app.services.profile_compat.mappers.szu_mapper import SzuProfileMapper
from backend.app.services.profile_sampling.models import (
    ProfileSamplingResult,
    ProfileSyncRequest,
    RawProfileFragment,
)
from backend.app.services.user_profile.models import NotificationPreference, UserProfile


def test_szu_mapper_merges_partial_sampling_result_with_existing_profile() -> None:
    mapper = SzuProfileMapper()
    existing_profile = UserProfile(
        user_id="szu_2020124040",
        student_id="2020124040",
        name="Old Name",
        college="Computer Science",
        major="Software Engineering",
        degree_level="undergraduate",
        identity_tags=["student"],
        enrolled_courses=[],
        notification_preference=NotificationPreference(channels=["app_push"]),
        metadata={"existing": True},
    )
    sampling_result = ProfileSamplingResult(
        school_code="szu",
        auth_mode="szu_http_cas",
        fragments=[
            RawProfileFragment(
                fragment_type="identity",
                source_system="szu_board_identity",
                payload={"student_id": "2020124040", "name": "Test Student"},
                collected_at="2026-03-14T00:00:00+00:00",
            )
        ],
    )

    draft = mapper.map(
        request=ProfileSyncRequest(school_code="szu", auth_mode="szu_http_cas"),
        sampling_result=sampling_result,
        existing_profile=existing_profile,
    )

    assert draft.profile.user_id == "szu_2020124040"
    assert draft.profile.name == "Test Student"
    assert draft.profile.college == "Computer Science"
    assert draft.profile.major == "Software Engineering"
    assert draft.profile.grade == "2020"
    assert draft.profile.notification_preference.channels == ["app_push"]
    assert draft.field_sources["student_id"] == "szu_board_identity"
    assert draft.field_sources["grade"] == "derived:student_id"
    assert "enrolled_courses" in draft.missing_fields


def test_szu_mapper_builds_usable_profile_from_identity_credit_and_course_fragments() -> None:
    mapper = SzuProfileMapper()
    sampling_result = ProfileSamplingResult(
        school_code="szu",
        auth_mode="offline_fixture",
        fragments=[
            RawProfileFragment(
                fragment_type="identity",
                source_system="szu_student_profile_hint",
                payload={
                    "student_id": "2020124040",
                    "name": "Test Student",
                    "college": "Computer Science",
                    "major": "Software Engineering",
                    "grade": "2020",
                    "degree_level": "undergraduate",
                },
                collected_at="2026-03-14T00:00:00+00:00",
            ),
            RawProfileFragment(
                fragment_type="credit_status",
                source_system="szu_student_profile_hint",
                payload={"totalCredit": 160, "getCredit": 112, "needCredit": 48},
                collected_at="2026-03-14T00:00:00+00:00",
            ),
            RawProfileFragment(
                fragment_type="courses",
                source_system="szu_selected_courses_hint",
                payload={
                    "courses": [
                        {
                            "course_id": "CS305",
                            "course_name": "Operating Systems",
                            "teacher": "Prof. Lin",
                            "semester": "2025-2026-2",
                        }
                    ]
                },
                collected_at="2026-03-14T00:00:00+00:00",
            ),
        ],
    )

    draft = mapper.map(
        request=ProfileSyncRequest(school_code="szu", auth_mode="offline_fixture"),
        sampling_result=sampling_result,
    )

    assert draft.profile.college == "Computer Science"
    assert draft.profile.major == "Software Engineering"
    assert draft.profile.degree_level == "undergraduate"
    assert draft.profile.credit_status["program_summary"]["required_total_credits"] == 160
    assert draft.profile.credit_status["program_summary"]["completed_total_credits"] == 112
    assert draft.profile.credit_status["program_summary"]["outstanding_total_credits"] == 48
    assert draft.profile.credit_status["source_snapshot"]["source_system"] == "szu_student_profile_hint"
    assert draft.profile.enrolled_courses[0].course_id == "CS305"
    assert draft.missing_fields == []


def test_szu_mapper_builds_structured_credit_status_from_academic_completion_fragments() -> None:
    mapper = SzuProfileMapper()
    sampling_result = ProfileSamplingResult(
        school_code="szu",
        auth_mode="offline_fixture",
        fragments=[
            RawProfileFragment(
                fragment_type="academic_completion_overview",
                source_system="szu_ehall_academic_completion",
                payload={
                    "by_njdm": "-",
                    "context": {
                        "student_id": "2020124040",
                        "name": "Test Student",
                        "college": "Computer Science",
                        "major": "Software Engineering",
                        "grade": "2020级",
                        "plan_id": "plan_001",
                        "plan_name": "2022级软件工程主修培养方案",
                        "required_credits": 160.0,
                        "completed_credits": 112.0,
                    },
                    "overview": {
                        "PYFADM": "plan_001",
                        "PYFAMC": "2022级软件工程主修培养方案",
                        "YQXF": 160.0,
                        "WCXF": 112.0,
                    },
                    "plan_snapshots": [{"PYFADM": "plan_001"}],
                },
                collected_at="2026-03-15T10:00:00+08:00",
            ),
            RawProfileFragment(
                fragment_type="academic_completion_nodes",
                source_system="szu_ehall_academic_completion",
                payload={
                    "root_nodes": [
                        {
                            "KZH": "root_practice",
                            "FKZH": "-1",
                            "KZM": "实践模块",
                            "YQXF": "16",
                            "WCXF": "2",
                            "YQMS": 4,
                            "WCMS": 1,
                        }
                    ],
                    "child_nodes": [
                        {
                            "KZH": "child_practice",
                            "FKZH": "root_practice",
                            "KZM": "实践类课程",
                            "YQXF": "16",
                            "WCXF": "2",
                            "YQMS": 4,
                            "WCMS": 1,
                        },
                        {
                            "KZH": "child_innovation",
                            "FKZH": "root_practice",
                            "KZM": "创新创业（必修）",
                            "YQXF": "2",
                            "WCXF": "1",
                            "YQMS": 2,
                            "WCMS": 1,
                        },
                    ],
                },
                collected_at="2026-03-15T10:00:01+08:00",
            ),
            RawProfileFragment(
                fragment_type="academic_completion_courses",
                source_system="szu_ehall_academic_completion",
                payload={
                    "course_rows": [
                        {
                            "child_kzh": "child_practice",
                            "KCM": "毕业论文（设计）",
                            "KCH": "P001",
                            "XF": 6.0,
                            "SFTG_DISPLAY": "未通过",
                            "KCXZDM_DISPLAY": "必修",
                            "KCLBDM_DISPLAY": "实践类课程",
                        },
                        {
                            "child_kzh": "child_innovation",
                            "KCM": "创新领航讲座",
                            "KCH": "I001",
                            "XF": 1.0,
                            "SFTG_DISPLAY": "未通过",
                            "KCXZDM_DISPLAY": "必修",
                            "KCLBDM_DISPLAY": "创新创业（必修）",
                        },
                    ],
                    "summary": {
                        "root_module_count": 1,
                        "child_module_count": 2,
                        "course_row_count": 2,
                    },
                },
                collected_at="2026-03-15T10:00:02+08:00",
            ),
        ],
    )

    draft = mapper.map(
        request=ProfileSyncRequest(school_code="szu", auth_mode="offline_fixture"),
        sampling_result=sampling_result,
    )

    credit_status = draft.profile.credit_status

    assert draft.profile.student_id == "2020124040"
    assert draft.profile.grade == "2020"
    assert credit_status["program_summary"]["program_name"] == "2022级软件工程主修培养方案"
    assert credit_status["program_summary"]["required_total_credits"] == 160.0
    assert credit_status["program_summary"]["completed_total_credits"] == 112.0
    assert credit_status["program_summary"]["outstanding_total_credits"] == 48.0
    assert credit_status["source_snapshot"]["source_system"] == "szu_ehall_academic_completion"
    assert credit_status["source_snapshot"]["metadata"]["course_row_count"] == 2
    assert any(
        module["module_name"] == "实践类课程" and module["completion_status"] == "in_progress"
        for module in credit_status["module_progress"]
    )
    assert any(item["title"] == "毕业论文（设计）" for item in credit_status["pending_items"])
    assert any(signal["signal_type"] == "activity_based_credit_gap" for signal in credit_status["attention_signals"])
