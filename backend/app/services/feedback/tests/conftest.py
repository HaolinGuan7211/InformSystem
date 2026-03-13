from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app.container import build_container
from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.services.ai_processing.repositories.ai_analysis_repository import (
    SQLiteAIAnalysisRepository,
)
from backend.app.services.decision_engine.repositories.decision_repository import (
    SQLiteDecisionRepository,
)
from backend.app.services.feedback.sample_assembler import SampleAssembler
from backend.app.services.rule_engine.repositories.rule_analysis_repository import (
    RuleAnalysisRepository,
)
from backend.app.shared.models import AIAnalysisResult, DecisionResult, RuleAnalysisResult, SourceEvent

PROJECT_ROOT = Path(__file__).resolve().parents[5]
FLOW_ROOT = (
    PROJECT_ROOT
    / "mocks"
    / "shared"
    / "golden_flows"
    / "flow_001_graduation_material_submission"
)


@pytest.fixture
def feedback_settings(tmp_path: Path) -> Settings:
    return Settings(
        project_root=PROJECT_ROOT,
        data_dir=tmp_path / "data",
        database_path=tmp_path / "data" / "test.db",
        source_config_path=PROJECT_ROOT / "mocks" / "ingestion" / "source_configs.json",
        rule_config_path=PROJECT_ROOT / "mocks" / "rule_engine" / "upstream_inputs" / "rule_configs.json",
        push_policy_path=PROJECT_ROOT / "mocks" / "config" / "downstream_outputs" / "push_policies.json",
    )


@pytest.fixture
def container(feedback_settings: Settings):
    return build_container(feedback_settings)


@pytest.fixture
def client(feedback_settings: Settings) -> TestClient:
    return TestClient(create_app(feedback_settings))


@pytest.fixture
def feedback_service(container):
    return container.feedback_service


@pytest.fixture
def sample_assembler(container) -> SampleAssembler:
    return SampleAssembler(
        raw_event_repository=container.raw_event_repository,
        rule_analysis_repository=container.rule_analysis_repository,
        ai_analysis_repository=container.ai_analysis_repository,
        decision_repository=container.decision_repository,
        delivery_log_repository=container.delivery_log_repository,
        feedback_repository=container.feedback_repository,
        timezone_offset=container.settings.timezone,
    )


@pytest.fixture
def load_feedback_mock():
    def _load(relative_path: str) -> dict[str, Any]:
        path = PROJECT_ROOT / "mocks" / "feedback" / relative_path
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
def seed_pipeline_records(load_golden):
    async def _seed(target_container) -> None:
        event = SourceEvent.model_validate(load_golden("01_source_event.json"))
        rule_result = RuleAnalysisResult.model_validate(load_golden("03_rule_analysis_result.json"))
        ai_result = AIAnalysisResult.model_validate(load_golden("04_ai_analysis_result.json"))
        decision_result = DecisionResult.model_validate(load_golden("05_decision_result.json"))

        await target_container.raw_event_repository.save_events([event])
        await target_container.rule_analysis_repository.save(rule_result)
        await target_container.ai_analysis_repository.save(ai_result)
        await target_container.decision_repository.save(decision_result)

    return _seed
