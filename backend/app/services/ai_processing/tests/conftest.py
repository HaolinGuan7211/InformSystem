from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from backend.app.core.config import Settings
from backend.app.core.database import init_database
from backend.app.services.ai_processing.cache import MemoryAICache
from backend.app.services.ai_processing.field_extractor import FieldExtractor
from backend.app.services.ai_processing.model_gateway import MockModelGateway
from backend.app.services.ai_processing.models import AIModelConfig, ProfileContext, RuleAnalysisResult
from backend.app.services.ai_processing.prompt_builder import PromptBuilder
from backend.app.services.ai_processing.repositories.ai_analysis_repository import (
    SQLiteAIAnalysisRepository,
)
from backend.app.services.ai_processing.result_validator import ResultValidator
from backend.app.services.ai_processing.service import AIProcessingService
from backend.app.services.ai_processing.summary_generator import SummaryGenerator
from backend.app.services.ingestion.models import SourceEvent

PROJECT_ROOT = Path(__file__).resolve().parents[5]
FLOW_ROOT = (
    PROJECT_ROOT
    / "mocks"
    / "shared"
    / "golden_flows"
    / "flow_001_graduation_material_submission"
)


@pytest.fixture
def ai_test_settings(tmp_path: Path) -> Settings:
    settings = Settings(
        project_root=PROJECT_ROOT,
        data_dir=tmp_path / "data",
        database_path=tmp_path / "data" / "test.db",
        source_config_path=PROJECT_ROOT / "mocks" / "ingestion" / "source_configs.json",
        ai_prompt_template_path=PROJECT_ROOT
        / "backend"
        / "app"
        / "services"
        / "ai_processing"
        / "prompts"
        / "notice_analysis_v1.txt",
    )
    settings.ensure_directories()
    init_database(settings.database_path)
    return settings


@pytest.fixture
def load_ai_mock():
    def _load(group: str, name: str) -> dict[str, Any]:
        path = PROJECT_ROOT / "mocks" / "ai_processing" / group / name
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
        "rule_result": RuleAnalysisResult.model_validate(load_golden("03_rule_analysis_result.json")),
        "profile_context": ProfileContext.model_validate(
            _load_json(
                PROJECT_ROOT
                / "mocks"
                / "ai_processing"
                / "upstream_inputs"
                / "graduation_material_submission__input__profile_context.json"
            )
        ),
    }


@pytest.fixture
def fixed_now() -> datetime:
    return datetime.fromisoformat("2026-03-13T10:22:00+08:00")


@pytest.fixture
def build_ai_service(ai_test_settings: Settings, fixed_now: datetime):
    def _build(
        fixture_response: dict[str, Any] | None = None,
        gateway: MockModelGateway | None = None,
        repository: SQLiteAIAnalysisRepository | None = None,
        model_config_overrides: dict[str, Any] | None = None,
    ) -> tuple[AIProcessingService, SQLiteAIAnalysisRepository, MockModelGateway]:
        repo = repository or SQLiteAIAnalysisRepository(ai_test_settings.database_path)
        mock_gateway = gateway or MockModelGateway(
            fixture_responses={("evt_001", "stu_001"): fixture_response} if fixture_response else None
        )
        ai_service = AIProcessingService(
            prompt_builder=PromptBuilder(
                template_path=ai_test_settings.ai_prompt_template_path,
                prompt_version=ai_test_settings.ai_prompt_version,
            ),
            model_gateway=mock_gateway,
            field_extractor=FieldExtractor(),
            summary_generator=SummaryGenerator(),
            result_validator=ResultValidator(),
            repository=repo,
            cache=MemoryAICache(),
            model_config=AIModelConfig.model_validate(
                {
                    "enabled": True,
                    "provider": ai_test_settings.ai_provider,
                    "model_name": ai_test_settings.ai_model_name,
                    "prompt_version": ai_test_settings.ai_prompt_version,
                    **(model_config_overrides or {}),
                }
            ),
            timezone=ai_test_settings.timezone,
            id_factory=lambda: "ai_001",
            call_id_factory=lambda: "call_001",
            now_provider=lambda: fixed_now,
        )
        return ai_service, repo, mock_gateway

    return _build


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)
