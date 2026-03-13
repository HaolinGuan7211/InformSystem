from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from backend.app.core.config import Settings
from backend.app.core.database import init_database
from backend.app.services.decision_engine.action_resolver import ActionResolver
from backend.app.services.decision_engine.channel_resolver import ChannelResolver
from backend.app.services.decision_engine.evidence_aggregator import EvidenceAggregator
from backend.app.services.decision_engine.policy_loader import PolicyLoader
from backend.app.services.decision_engine.policies import FileDecisionPolicyProvider
from backend.app.services.decision_engine.priority_calculator import PriorityCalculator
from backend.app.services.decision_engine.repositories.decision_repository import SQLiteDecisionRepository
from backend.app.services.decision_engine.service import DecisionEngineService
from backend.app.shared.models import AIAnalysisResult, RuleAnalysisResult, SourceEvent, UserProfile

PROJECT_ROOT = Path(__file__).resolve().parents[5]
FLOW_ROOT = (
    PROJECT_ROOT
    / "mocks"
    / "shared"
    / "golden_flows"
    / "flow_001_graduation_material_submission"
)


@pytest.fixture
def decision_test_settings(tmp_path: Path) -> Settings:
    settings = Settings(
        project_root=PROJECT_ROOT,
        data_dir=tmp_path / "data",
        database_path=tmp_path / "data" / "test.db",
        source_config_path=PROJECT_ROOT / "mocks" / "ingestion" / "source_configs.json",
        push_policy_path=PROJECT_ROOT / "mocks" / "config" / "downstream_outputs" / "push_policies.json",
    )
    settings.ensure_directories()
    init_database(settings.database_path)
    return settings


@pytest.fixture
def decision_repository(decision_test_settings: Settings) -> SQLiteDecisionRepository:
    return SQLiteDecisionRepository(decision_test_settings.database_path)


@pytest.fixture
def decision_service(
    decision_test_settings: Settings,
    decision_repository: SQLiteDecisionRepository,
) -> DecisionEngineService:
    return DecisionEngineService(
        policy_loader=PolicyLoader(FileDecisionPolicyProvider(decision_test_settings.push_policy_path)),
        evidence_aggregator=EvidenceAggregator(),
        priority_calculator=PriorityCalculator(),
        action_resolver=ActionResolver(),
        channel_resolver=ChannelResolver(),
        decision_repository=decision_repository,
        timezone_offset=decision_test_settings.timezone,
    )


@pytest.fixture
def load_decision_mock():
    def _load(group: str, name: str) -> dict[str, Any]:
        path = PROJECT_ROOT / "mocks" / "decision_engine" / group / name
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
        "rule_result": RuleAnalysisResult.model_validate(load_golden("03_rule_analysis_result.json")),
        "ai_result": AIAnalysisResult.model_validate(load_golden("04_ai_analysis_result.json")),
    }
