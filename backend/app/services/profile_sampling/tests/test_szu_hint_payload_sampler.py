from __future__ import annotations

import pytest

from backend.app.services.profile_sampling.models import ProfileSyncRequest, SchoolSessionHandle
from backend.app.services.profile_sampling.samplers.szu.hint_payload_sampler import (
    SzuHintPayloadSampler,
)


@pytest.mark.asyncio
async def test_szu_hint_payload_sampler_builds_identity_credit_and_course_fragments() -> None:
    sampler = SzuHintPayloadSampler()
    session_handle = SchoolSessionHandle(
        school_code="szu",
        auth_mode="offline_fixture",
        session=None,
        entry_url="offline://fixture",
        authenticated_url="offline://fixture",
    )
    request = ProfileSyncRequest(
        school_code="szu",
        auth_mode="offline_fixture",
        hints={
            "szu_personal_info": {
                "code": "0",
                "data": {
                    "cn": "Test Student",
                    "uid": "2020124040",
                    "mobile": "180****1730",
                },
            },
            "szu_student_profile": {
                "code": "1",
                "data": {
                    "name": "Test Student",
                    "number": "2020124040",
                    "grade": "2020",
                    "collegeName": "Computer Science",
                    "majorName": "Software Engineering",
                    "studentTypeName": "本科生",
                    "totalCredit": 160,
                    "getCredit": 112,
                    "needCredit": 48,
                    "electiveBatch": {
                        "name": "2025-2026-2 选课",
                        "typeName": "正选阶段",
                    },
                },
            },
            "szu_selected_courses": {
                "dataList": [
                    {
                        "courseNumber": "CS305",
                        "courseName": "Operating Systems",
                        "teacherName": "Prof. Lin",
                        "semesterName": "2025-2026-2",
                    }
                ]
            },
        },
    )

    fragments = await sampler.sample(session_handle, request)
    fragments_by_type = {fragment.fragment_type: fragment for fragment in fragments}

    assert {fragment.fragment_type for fragment in fragments} == {
        "identity",
        "credit_status",
        "courses",
    }
    assert fragments_by_type["identity"].payload["student_id"] == "2020124040"
    assert fragments_by_type["identity"].payload["college"] == "Computer Science"
    assert fragments_by_type["identity"].payload["degree_level"] == "undergraduate"
    assert fragments_by_type["credit_status"].payload["totalCredit"] == 160
    assert fragments_by_type["courses"].payload["courses"][0]["course_id"] == "CS305"
