from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.container import build_container
from backend.app.core.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[5]


@pytest.fixture
def message_probe_settings(tmp_path: Path) -> Settings:
    return Settings(
        project_root=PROJECT_ROOT,
        data_dir=tmp_path / "data",
        database_path=tmp_path / "data" / "test.db",
        source_config_path=PROJECT_ROOT / "mocks" / "ingestion" / "source_configs.json",
    )


@pytest.fixture
def container(message_probe_settings: Settings):
    return build_container(message_probe_settings)
