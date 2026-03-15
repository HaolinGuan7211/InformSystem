from __future__ import annotations

from pathlib import Path

import pytest
import requests

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

PROJECT_ROOT = Path(__file__).resolve().parents[4]
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
        return SchoolSessionHandle(
            school_code="szu",
            auth_mode=request.auth_mode,
            session=requests.Session(),
            entry_url="https://www1.szu.edu.cn/board/",
            authenticated_url="https://www1.szu.edu.cn/board/",
            metadata={"authenticated_html": SAMPLE_BOARD_HTML},
        )


@pytest.mark.asyncio
async def test_profile_sync_orchestrator_persists_sampled_profile(tmp_path: Path) -> None:
    settings = Settings(
        project_root=PROJECT_ROOT,
        data_dir=tmp_path / "data",
        database_path=tmp_path / "data" / "profile_sync.db",
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

    result = await orchestrator.run(
        ProfileSyncRequest(
            school_code="szu",
            auth_mode="szu_http_cas",
            hints={
                "college": "Computer Science",
                "major": "Software Engineering",
                "degree_level": "undergraduate",
            },
        )
    )

    assert result.persisted is True
    assert result.profile.user_id == "szu_2020124040"
    assert result.profile.student_id == "2020124040"
    assert result.profile.name == "Test Student"
    assert result.profile.grade == "2020"
    assert result.profile.college == "Computer Science"
    assert result.profile.major == "Software Engineering"

    snapshot = await user_profile_service.build_snapshot("szu_2020124040")
    assert snapshot is not None
    assert snapshot.student_id == "2020124040"
