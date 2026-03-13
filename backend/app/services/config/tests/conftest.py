from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.core.config import Settings
from backend.app.core.database import init_database
from backend.app.services.config import ConfigFilePaths, ConfigService, FileConfigStore, SQLiteConfigStore

PROJECT_ROOT = Path(__file__).resolve().parents[5]


@pytest.fixture
def config_test_settings(tmp_path: Path) -> Settings:
    settings = Settings(
        project_root=PROJECT_ROOT,
        data_dir=tmp_path / "data",
        database_path=tmp_path / "data" / "test.db",
        source_config_path=PROJECT_ROOT / "mocks" / "ingestion" / "source_configs.json",
        rule_config_path=PROJECT_ROOT / "mocks" / "rule_engine" / "upstream_inputs" / "rule_configs.json",
        notification_category_path=PROJECT_ROOT
        / "mocks"
        / "config"
        / "downstream_outputs"
        / "notification_categories.json",
        push_policy_path=PROJECT_ROOT / "mocks" / "config" / "downstream_outputs" / "push_policies.json",
        config_audit_log_path=tmp_path / "config" / "change_logs.json",
    )
    settings.ensure_directories()
    init_database(settings.database_path)
    return settings


@pytest.fixture
def sqlite_config_service(config_test_settings: Settings) -> ConfigService:
    seed_store = FileConfigStore(
        ConfigFilePaths(
            source_config_path=config_test_settings.source_config_path,
            rule_config_path=config_test_settings.rule_config_path,
            notification_category_path=config_test_settings.notification_category_path,
            push_policy_path=config_test_settings.push_policy_path,
            audit_log_path=config_test_settings.config_audit_log_path,
        )
    )
    service = ConfigService(SQLiteConfigStore(config_test_settings.database_path))
    service.ensure_seed_data(seed_store)
    return service


@pytest.fixture
def file_config_service(tmp_path: Path, config_test_settings: Settings) -> ConfigService:
    source_path = tmp_path / "config" / "source_configs.json"
    rule_path = tmp_path / "config" / "rule_configs.json"
    category_path = tmp_path / "config" / "notification_categories.json"
    policy_path = tmp_path / "config" / "push_policies.json"
    audit_log_path = tmp_path / "config" / "change_logs.json"

    seed_store = FileConfigStore(
        ConfigFilePaths(
            source_config_path=config_test_settings.source_config_path,
            rule_config_path=config_test_settings.rule_config_path,
            notification_category_path=config_test_settings.notification_category_path,
            push_policy_path=config_test_settings.push_policy_path,
            audit_log_path=config_test_settings.config_audit_log_path,
        )
    )
    file_store = FileConfigStore(
        ConfigFilePaths(
            source_config_path=source_path,
            rule_config_path=rule_path,
            notification_category_path=category_path,
            push_policy_path=policy_path,
            audit_log_path=audit_log_path,
        )
    )
    service = ConfigService(file_store)
    service.ensure_seed_data(seed_store)
    return service
