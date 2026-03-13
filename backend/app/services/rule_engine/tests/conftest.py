from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.core.config import Settings
from backend.app.core.database import init_database
from backend.app.services.ingestion.models import SourceEvent
from backend.app.services.rule_engine.action_risk_evaluator import ActionRiskEvaluator
from backend.app.services.rule_engine.ai_trigger_gate import AITriggerGate
from backend.app.services.rule_engine.audience_matcher import AudienceMatcher
from backend.app.services.rule_engine.config_loader import RuleConfigLoader
from backend.app.services.rule_engine.preprocessor import EventPreprocessor
from backend.app.services.rule_engine.repositories.rule_analysis_repository import RuleAnalysisRepository
from backend.app.services.rule_engine.service import RuleEngineService
from backend.app.services.rule_engine.signal_extractor import SignalExtractor
from backend.app.services.user_profile.models import UserProfile

PROJECT_ROOT = Path(__file__).resolve().parents[5]


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    settings = Settings(
        project_root=PROJECT_ROOT,
        data_dir=tmp_path / "data",
        database_path=tmp_path / "data" / "test.db",
        source_config_path=PROJECT_ROOT / "mocks" / "ingestion" / "source_configs.json",
        rule_config_path=PROJECT_ROOT / "mocks" / "rule_engine" / "upstream_inputs" / "rule_configs.json",
    )
    settings.ensure_directories()
    init_database(settings.database_path)
    return settings


@pytest.fixture
def rule_engine_service(test_settings: Settings) -> RuleEngineService:
    return RuleEngineService(
        config_loader=RuleConfigLoader(test_settings.rule_config_path),
        preprocessor=EventPreprocessor(),
        signal_extractor=SignalExtractor(),
        audience_matcher=AudienceMatcher(),
        action_risk_evaluator=ActionRiskEvaluator(),
        ai_trigger_gate=AITriggerGate(),
        repository=RuleAnalysisRepository(test_settings.database_path),
    )


@pytest.fixture
def load_rule_mock():
    def _load(relative_path: str):
        path = PROJECT_ROOT / "mocks" / "rule_engine" / relative_path
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    return _load


@pytest.fixture
def source_event(load_rule_mock) -> SourceEvent:
    payload = load_rule_mock("upstream_inputs/graduation_material_submission__input__source_event.json")
    return SourceEvent.model_validate(payload)


@pytest.fixture
def user_profile(load_rule_mock) -> UserProfile:
    payload = load_rule_mock("upstream_inputs/graduation_material_submission__input__user_profile.json")
    return UserProfile.model_validate(payload)
