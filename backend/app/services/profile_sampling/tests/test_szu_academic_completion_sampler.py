from __future__ import annotations

import requests
import pytest

from backend.app.services.profile_sampling.models import ProfileSyncRequest, SchoolSessionHandle
from backend.app.services.profile_sampling.samplers.szu.academic_completion_sampler import (
    SzuAcademicCompletionSampler,
)


class _FakeEhallClient:
    def collect_academic_completion(self, handle, *, bynjdm: str, page_size: int) -> dict[str, object]:
        assert bynjdm == "-"
        assert page_size == 999
        return {
            "by_njdm": bynjdm,
            "context": {
                "student_id": "2020124040",
                "name": "Test Student",
                "plan_id": "plan_001",
                "plan_name": "Test Plan",
            },
            "overview": {"XM": "Test Student", "XH": "2020124040"},
            "student_info": {"XM": "Test Student"},
            "plan_snapshots": [{"PYFADM": "plan_001"}],
            "root_nodes": [{"KZH": "root_1", "KZM": "专业模块"}],
            "child_nodes": [{"KZH": "child_1", "FKZH": "root_1", "KZM": "专业核心课"}],
            "child_nodes_by_parent": {"root_1": ["child_1"]},
            "root_summaries": [{"root_module": "专业模块", "child_course_total": 2}],
            "course_groups": [
                {
                    "parent_module": "专业模块",
                    "parent_kzh": "root_1",
                    "child_module": "专业核心课",
                    "child_kzh": "child_1",
                    "course_total": 2,
                    "courses": [{"KCM": "Operating Systems", "KCH": "CS301"}],
                }
            ],
            "course_rows": [
                {
                    "parent_module": "专业模块",
                    "child_module": "专业核心课",
                    "KCM": "Operating Systems",
                    "KCH": "CS301",
                }
            ],
            "summary": {"root_module_count": 1, "child_module_count": 1, "course_row_count": 1},
        }


@pytest.mark.asyncio
async def test_szu_academic_completion_sampler_supports_ehall_session_only() -> None:
    sampler = SzuAcademicCompletionSampler(ehall_client=_FakeEhallClient())

    assert sampler.supports(
        SchoolSessionHandle(
            school_code="szu",
            auth_mode="szu_http_cas_ehall",
            session=requests.Session(),
            entry_url="https://ehall.szu.edu.cn/appShow?appId=4980269146247992",
            authenticated_url="https://ehall.szu.edu.cn/jwapp/sys/xywccx/*default/index.do",
            metadata={"target_system": "ehall"},
        ),
        ProfileSyncRequest(school_code="szu", auth_mode="szu_http_cas_ehall"),
    )
    assert not sampler.supports(
        SchoolSessionHandle(
            school_code="szu",
            auth_mode="szu_http_cas",
            session=requests.Session(),
            entry_url="https://www1.szu.edu.cn/board/",
            authenticated_url="https://www1.szu.edu.cn/board/",
            metadata={"target_system": "board"},
        ),
        ProfileSyncRequest(school_code="szu", auth_mode="szu_http_cas"),
    )


@pytest.mark.asyncio
async def test_szu_academic_completion_sampler_emits_three_fragments() -> None:
    sampler = SzuAcademicCompletionSampler(ehall_client=_FakeEhallClient())
    session_handle = SchoolSessionHandle(
        school_code="szu",
        auth_mode="szu_http_cas_ehall",
        session=requests.Session(),
        entry_url="https://ehall.szu.edu.cn/appShow?appId=4980269146247992",
        authenticated_url="https://ehall.szu.edu.cn/jwapp/sys/xywccx/*default/index.do",
        metadata={"target_system": "ehall"},
    )

    fragments = await sampler.sample(
        session_handle,
        ProfileSyncRequest(school_code="szu", auth_mode="szu_http_cas_ehall"),
    )

    assert [fragment.fragment_type for fragment in fragments] == [
        "academic_completion_overview",
        "academic_completion_nodes",
        "academic_completion_courses",
    ]
    assert fragments[0].payload["context"]["plan_id"] == "plan_001"
    assert fragments[1].payload["root_nodes"][0]["KZM"] == "专业模块"
    assert fragments[2].payload["summary"]["course_row_count"] == 1
    assert fragments[2].payload["course_rows"][0]["KCM"] == "Operating Systems"
