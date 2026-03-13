from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from backend.app.core.config import Settings
from backend.app.core.database import init_database
from backend.app.services.delivery.channel_router import DeliveryChannelRouter
from backend.app.services.delivery.digest_composer import DigestComposer
from backend.app.services.delivery.gateway_manager import GatewayManager
from backend.app.services.delivery.planner import DeliveryPlanner
from backend.app.services.delivery.renderer import MessageRenderer
from backend.app.services.delivery.repositories.delivery_log_repository import DeliveryLogRepository
from backend.app.services.delivery.repositories.digest_job_repository import DigestJobRepository
from backend.app.services.delivery.retry_manager import RetryManager
from backend.app.services.delivery.service import DeliveryService
from backend.app.shared.models import DecisionResult, SourceEvent, UserProfile

PROJECT_ROOT = Path(__file__).resolve().parents[5]
FLOW_ROOT = (
    PROJECT_ROOT
    / "mocks"
    / "shared"
    / "golden_flows"
    / "flow_001_graduation_material_submission"
)


@pytest.fixture
def delivery_test_settings(tmp_path: Path) -> Settings:
    settings = Settings(
        project_root=PROJECT_ROOT,
        data_dir=tmp_path / "data",
        database_path=tmp_path / "data" / "test.db",
    )
    settings.ensure_directories()
    init_database(settings.database_path)
    return settings


@pytest.fixture
def delivery_log_repository(delivery_test_settings: Settings) -> DeliveryLogRepository:
    return DeliveryLogRepository(delivery_test_settings.database_path)


@pytest.fixture
def digest_job_repository(delivery_test_settings: Settings) -> DigestJobRepository:
    return DigestJobRepository(delivery_test_settings.database_path)


@pytest.fixture
def delivery_service(
    delivery_test_settings: Settings,
    delivery_log_repository: DeliveryLogRepository,
    digest_job_repository: DigestJobRepository,
) -> DeliveryService:
    renderer = MessageRenderer()
    gateway_manager = GatewayManager()
    retry_manager = RetryManager()
    digest_composer = DigestComposer(
        repository=digest_job_repository,
        gateway_manager=gateway_manager,
        retry_manager=retry_manager,
        log_repository=delivery_log_repository,
        renderer=renderer,
        timezone_offset=delivery_test_settings.timezone,
    )
    return DeliveryService(
        planner=DeliveryPlanner(
            channel_router=DeliveryChannelRouter(),
            renderer=renderer,
        ),
        gateway_manager=gateway_manager,
        retry_manager=retry_manager,
        digest_composer=digest_composer,
        log_repository=delivery_log_repository,
        timezone_offset=delivery_test_settings.timezone,
    )


@pytest.fixture
def load_delivery_mock():
    def _load(group: str, name: str) -> dict[str, Any]:
        path = PROJECT_ROOT / "mocks" / "delivery" / group / name
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    return _load


@pytest.fixture
def load_golden():
    def _load(name: str) -> dict[str, Any]:
        path = FLOW_ROOT / name
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    return _load


@pytest.fixture
def flow_inputs(load_golden):
    return {
        "event": SourceEvent.model_validate(load_golden("01_source_event.json")),
        "user_profile": UserProfile.model_validate(load_golden("02_user_profile.json")),
        "decision_result": DecisionResult.model_validate(load_golden("05_decision_result.json")),
    }
