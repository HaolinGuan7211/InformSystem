from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.container import build_container
from backend.app.core.config import Settings
from backend.app.main import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[5]


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    return Settings(
        project_root=PROJECT_ROOT,
        data_dir=tmp_path / "data",
        database_path=tmp_path / "data" / "test.db",
        source_config_path=PROJECT_ROOT / "mocks" / "ingestion" / "source_configs.json",
    )


@pytest.fixture
def container(test_settings: Settings):
    return build_container(test_settings)


@pytest.fixture
def client(test_settings: Settings) -> TestClient:
    return TestClient(create_app(test_settings))


@pytest.fixture
def load_mock():
    import json

    def _load(name: str):
        path = PROJECT_ROOT / "mocks" / "ingestion" / "raw_inputs" / name
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    return _load
