from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class Settings:
    project_root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[3])
    app_name: str = "InformSystem"
    timezone: str = "+08:00"
    config_backend: str = "sqlite"
    data_dir: Path | None = None
    database_path: Path | None = None
    source_config_path: Path | None = None
    rule_config_path: Path | None = None
    notification_category_path: Path | None = None
    config_audit_log_path: Path | None = None
    ai_provider: str = "mock"
    ai_model_name: str = "gpt-5-mini"
    ai_prompt_version: str = "prompt_v1"
    ai_gateway_endpoint: str | None = None
    ai_api_key: str | None = None
    ai_prompt_template_path: Path | None = None
    push_policy_path: Path | None = None

    def __post_init__(self) -> None:
        self.project_root = Path(self.project_root)
        if self.data_dir is None:
            self.data_dir = self.project_root / "backend" / "data"
        if self.database_path is None:
            self.database_path = self.data_dir / "inform_system.db"
        if self.source_config_path is None:
            self.source_config_path = self.project_root / "mocks" / "ingestion" / "source_configs.json"
        if self.rule_config_path is None:
            self.rule_config_path = (
                self.project_root
                / "mocks"
                / "rule_engine"
                / "upstream_inputs"
                / "rule_configs.json"
            )
        if self.notification_category_path is None:
            self.notification_category_path = (
                self.project_root
                / "mocks"
                / "config"
                / "downstream_outputs"
                / "notification_categories.json"
            )
        if self.ai_prompt_template_path is None:
            self.ai_prompt_template_path = (
                self.project_root
                / "backend"
                / "app"
                / "services"
                / "ai_processing"
                / "prompts"
                / "notice_analysis_v1.txt"
            )
        if self.push_policy_path is None:
            self.push_policy_path = (
                self.project_root
                / "mocks"
                / "config"
                / "downstream_outputs"
                / "push_policies.json"
            )
        if self.config_audit_log_path is None:
            self.config_audit_log_path = (
                self.project_root
                / "mocks"
                / "config"
                / "change_logs.json"
            )

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config_audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.notification_category_path.parent.mkdir(parents=True, exist_ok=True)
