from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.routes.profile_sync import router as profile_sync_router
from backend.app.container import build_container
from backend.app.core.config import Settings
from backend.app.core.database import init_database
from backend.app.services.profile_compat.mappers.szu_mapper import SzuProfileMapper
from backend.app.services.profile_compat.service import ProfileCompatibilityService
from backend.app.services.profile_sampling.auth.base import AuthProvider
from backend.app.services.profile_sampling.models import ProfileSyncRequest, SchoolSessionHandle
from backend.app.services.profile_sampling.samplers.szu.board_identity_sampler import (
    SzuBoardIdentitySampler,
)
from backend.app.services.profile_sampling.service import ProfileSamplingService
from backend.app.services.user_profile.course_sync_adapter import CourseSyncAdapter
from backend.app.services.user_profile.credit_status_manager import CreditStatusManager
from backend.app.services.user_profile.graduation_status_manager import GraduationStatusManager
from backend.app.services.user_profile.preference_manager import PreferenceManager
from backend.app.services.user_profile.repositories import SQLiteUserProfileRepository
from backend.app.services.user_profile.service import UserProfileService
from backend.app.services.user_profile.snapshot_builder import SnapshotBuilder
from backend.app.workflows.profile_sync_orchestrator import ProfileSyncOrchestrator

PROJECT_ROOT = Path(__file__).resolve().parents[5]
SAMPLE_BOARD_HTML = """
<html>
  <body>
    <a href="https://authserver.szu.edu.cn/personalInfo"
       title="Test Student\uff082020124040\uff09\uff5c修改密码、绑定手机和邮箱等">profile</a>
  </body>
</html>
"""


class StaticAuthProvider(AuthProvider):
    async def authenticate(self, request: ProfileSyncRequest) -> SchoolSessionHandle:
        import requests

        return SchoolSessionHandle(
            school_code="szu",
            auth_mode=request.auth_mode,
            session=requests.Session(),
            entry_url="https://www1.szu.edu.cn/board/",
            authenticated_url="https://www1.szu.edu.cn/board/",
            metadata={"authenticated_html": SAMPLE_BOARD_HTML},
        )


def test_profile_sync_api_runs_end_to_end(tmp_path: Path) -> None:
    settings = Settings(
        project_root=PROJECT_ROOT,
        data_dir=tmp_path / "data",
        database_path=tmp_path / "data" / "profile_sync_api.db",
    )
    settings.ensure_directories()
    init_database(settings.database_path)

    repository = SQLiteUserProfileRepository(settings.database_path, settings.timezone)
    user_profile_service = UserProfileService(
        repository=repository,
        snapshot_builder=SnapshotBuilder(
            repository=repository,
            course_sync_adapter=CourseSyncAdapter(repository),
            credit_status_manager=CreditStatusManager(repository),
            graduation_status_manager=GraduationStatusManager(repository),
            preference_manager=PreferenceManager(repository),
        ),
    )

    sampling_service = ProfileSamplingService()
    sampling_service.register_auth_provider("szu", "szu_http_cas", StaticAuthProvider())
    sampling_service.register_sampler("szu", SzuBoardIdentitySampler())

    compatibility_service = ProfileCompatibilityService()
    compatibility_service.register_mapper("szu", SzuProfileMapper())

    orchestrator = ProfileSyncOrchestrator(
        sampling_service=sampling_service,
        compatibility_service=compatibility_service,
        user_profile_repository=repository,
        user_profile_service=user_profile_service,
    )

    app = FastAPI()
    app.state.container = SimpleNamespace(profile_sync_orchestrator=orchestrator)
    app.include_router(profile_sync_router)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/profile-sync/szu/run",
            json={
                "auth_mode": "szu_http_cas",
                "hints": {
                    "college": "Computer Science",
                    "major": "Software Engineering",
                    "degree_level": "undergraduate",
                },
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["result"]["profile"]["student_id"] == "2020124040"
    assert body["result"]["profile"]["name"] == "Test Student"
    assert body["result"]["profile"]["college"] == "Computer Science"


def test_profile_sync_api_supports_offline_fixture_full_profile(tmp_path: Path) -> None:
    settings = Settings(
        project_root=PROJECT_ROOT,
        data_dir=tmp_path / "data",
        database_path=tmp_path / "data" / "profile_sync_api_offline.db",
    )
    settings.ensure_directories()
    init_database(settings.database_path)

    app = FastAPI()
    app.state.container = build_container(settings)
    app.include_router(profile_sync_router)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/profile-sync/szu/run",
            json={
                "auth_mode": "offline_fixture",
                "hints": {
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
                            },
                            {
                                "courseNumber": "CS210",
                                "courseName": "Computer Networks",
                                "teacherName": "Prof. Chen",
                                "semesterName": "2025-2026-2",
                            },
                        ]
                    },
                },
            },
        )

    assert response.status_code == 200
    body = response.json()
    profile = body["result"]["profile"]
    assert body["result"]["persisted"] is True
    assert profile["student_id"] == "2020124040"
    assert profile["college"] == "Computer Science"
    assert profile["major"] == "Software Engineering"
    assert profile["degree_level"] == "undergraduate"
    assert profile["credit_status"]["program_summary"]["required_total_credits"] == 160
    assert profile["credit_status"]["program_summary"]["completed_total_credits"] == 112
    assert profile["credit_status"]["program_summary"]["outstanding_total_credits"] == 48
    assert profile["credit_status"]["source_snapshot"]["source_system"] == "szu_student_profile_hint"
    assert [course["course_id"] for course in profile["enrolled_courses"]] == ["CS210", "CS305"]
    assert body["result"]["missing_fields"] == []


def test_profile_sync_api_supports_academic_completion_fragments_without_polluting_enrolled_courses(
    tmp_path: Path,
) -> None:
    settings = Settings(
        project_root=PROJECT_ROOT,
        data_dir=tmp_path / "data",
        database_path=tmp_path / "data" / "profile_sync_api_academic.db",
    )
    settings.ensure_directories()
    init_database(settings.database_path)

    app = FastAPI()
    app.state.container = build_container(settings)
    app.include_router(profile_sync_router)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/profile-sync/szu/run",
            json={
                "auth_mode": "offline_fixture",
                "hints": {
                    "degree_level": "undergraduate",
                    "szu_academic_completion": {
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
                        "root_nodes": [
                            {
                                "KZH": "root_innovation",
                                "FKZH": "-1",
                                "KZM": "创新创业模块",
                                "YQXF": "3",
                                "WCXF": "1",
                                "YQMS": 2,
                                "WCMS": 1,
                            }
                        ],
                        "child_nodes": [
                            {
                                "KZH": "child_innovation",
                                "FKZH": "root_innovation",
                                "KZM": "创新创业（必修）",
                                "YQXF": "2",
                                "WCXF": "1",
                                "YQMS": 2,
                                "WCMS": 1,
                            }
                        ],
                        "child_nodes_by_parent": {"root_innovation": ["child_innovation"]},
                        "root_summaries": [{"root_module": "创新创业模块", "child_course_total": 1}],
                        "course_groups": [
                            {
                                "parent_module": "创新创业模块",
                                "parent_kzh": "root_innovation",
                                "child_module": "创新创业（必修）",
                                "child_kzh": "child_innovation",
                                "course_total": 1,
                                "courses": [{"KCM": "创新领航讲座", "KCH": "I001", "SFTG_DISPLAY": "未通过"}],
                            }
                        ],
                        "course_rows": [
                            {
                                "parent_module": "创新创业模块",
                                "parent_kzh": "root_innovation",
                                "child_module": "创新创业（必修）",
                                "child_kzh": "child_innovation",
                                "KCM": "创新领航讲座",
                                "KCH": "I001",
                                "XF": 1.0,
                                "SFTG_DISPLAY": "未通过",
                                "KCXZDM_DISPLAY": "必修",
                                "KCLBDM_DISPLAY": "创新创业（必修）",
                            }
                        ],
                        "summary": {
                            "root_module_count": 1,
                            "child_module_count": 1,
                            "course_row_count": 1,
                        },
                    },
                },
            },
        )

    assert response.status_code == 200
    profile = response.json()["result"]["profile"]
    assert profile["student_id"] == "2020124040"
    assert profile["degree_level"] == "undergraduate"
    assert profile["enrolled_courses"] == []
    assert profile["credit_status"]["program_summary"]["program_name"] == "2022级软件工程主修培养方案"
    assert any(
        module["module_name"] == "创新创业（必修）" for module in profile["credit_status"]["module_progress"]
    )
    assert any(item["title"] == "创新领航讲座" for item in profile["credit_status"]["pending_items"])
