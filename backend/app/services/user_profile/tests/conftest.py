from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.routes.user_profile import router as user_profile_router
from backend.app.core.config import Settings
from backend.app.core.database import init_database
from backend.app.services.user_profile.course_sync_adapter import CourseSyncAdapter
from backend.app.services.user_profile.credit_status_manager import CreditStatusManager
from backend.app.services.user_profile.graduation_status_manager import GraduationStatusManager
from backend.app.services.user_profile.preference_manager import PreferenceManager
from backend.app.services.user_profile.profile_context_selector import ProfileContextSelector
from backend.app.services.user_profile.repositories import SQLiteUserProfileRepository
from backend.app.services.user_profile.service import UserProfileService
from backend.app.services.user_profile.snapshot_builder import SnapshotBuilder

PROJECT_ROOT = Path(__file__).resolve().parents[5]
SHARED_FLOW_ROOT = (
    PROJECT_ROOT
    / "mocks"
    / "shared"
    / "golden_flows"
    / "flow_001_graduation_material_submission"
)


@pytest.fixture
def user_profile_test_settings(tmp_path: Path) -> Settings:
    settings = Settings(
        project_root=PROJECT_ROOT,
        data_dir=tmp_path / "data",
        database_path=tmp_path / "data" / "test.db",
    )
    settings.ensure_directories()
    init_database(settings.database_path)
    return settings


@pytest.fixture
def user_profile_repository(user_profile_test_settings: Settings) -> SQLiteUserProfileRepository:
    return SQLiteUserProfileRepository(
        user_profile_test_settings.database_path,
        user_profile_test_settings.timezone,
    )


@pytest.fixture
def snapshot_builder(user_profile_repository: SQLiteUserProfileRepository) -> SnapshotBuilder:
    return SnapshotBuilder(
        repository=user_profile_repository,
        course_sync_adapter=CourseSyncAdapter(user_profile_repository),
        credit_status_manager=CreditStatusManager(user_profile_repository),
        graduation_status_manager=GraduationStatusManager(user_profile_repository),
        preference_manager=PreferenceManager(user_profile_repository),
    )


@pytest.fixture
def user_profile_service(
    user_profile_repository: SQLiteUserProfileRepository,
    snapshot_builder: SnapshotBuilder,
    user_profile_test_settings: Settings,
) -> UserProfileService:
    return UserProfileService(
        repository=user_profile_repository,
        snapshot_builder=snapshot_builder,
        profile_context_selector=ProfileContextSelector(user_profile_test_settings.timezone),
    )


@pytest.fixture
def load_user_profile_mock():
    def _load(group: str, name: str) -> dict:
        path = PROJECT_ROOT / "mocks" / "user_profile" / group / name
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    return _load


@pytest.fixture
def load_golden():
    def _load(name: str) -> dict:
        path = SHARED_FLOW_ROOT / name
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    return _load


@pytest.fixture
def api_client(user_profile_service: UserProfileService):
    app = FastAPI()
    app.state.container = SimpleNamespace(user_profile_service=user_profile_service)
    app.include_router(user_profile_router)
    with TestClient(app) as client:
        yield client
