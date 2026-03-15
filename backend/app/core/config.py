from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_AI_PROVIDER = "mock"
DEFAULT_AI_MODEL_NAME = "gpt-5-mini"
DEFAULT_AI_PROMPT_VERSION = "prompt_v1"


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
    ai_runtime_config_path: Path | None = None
    delivery_channel_config_path: Path | None = None
    config_audit_log_path: Path | None = None
    ai_provider: str = DEFAULT_AI_PROVIDER
    ai_model_name: str = DEFAULT_AI_MODEL_NAME
    ai_prompt_version: str = DEFAULT_AI_PROMPT_VERSION
    ai_gateway_endpoint: str | None = None
    ai_api_key: str | None = None
    ai_prompt_template_path: Path | None = None
    ai_enabled: bool | None = None
    ai_max_retries: int | None = None
    push_policy_path: Path | None = None

    def __post_init__(self) -> None:
        self.project_root = Path(self.project_root)
        env_ai_provider = os.getenv("AI_PROVIDER")
        env_ai_model_name = os.getenv("AI_MODEL_NAME")
        env_ai_gateway_endpoint = os.getenv("AI_GATEWAY_ENDPOINT")
        env_ai_api_key = os.getenv("AI_API_KEY")
        env_kimi_model = os.getenv("KIMI_MODEL")
        env_kimi_base_url = os.getenv("KIMI_BASE_URL")
        env_kimi_api_key = os.getenv("KIMI_API_KEY")
        env_ai_enabled = self._parse_env_bool(os.getenv("AI_ENABLED"))
        env_ai_max_retries = self._parse_env_int(os.getenv("AI_MAX_RETRIES"))

        if env_ai_provider:
            self.ai_provider = env_ai_provider
        if env_ai_model_name:
            self.ai_model_name = env_ai_model_name
        if self.ai_gateway_endpoint is None and env_ai_gateway_endpoint:
            self.ai_gateway_endpoint = env_ai_gateway_endpoint
        if self.ai_api_key is None and env_ai_api_key:
            self.ai_api_key = env_ai_api_key
        if self.ai_enabled is None and env_ai_enabled is not None:
            self.ai_enabled = env_ai_enabled
        if self.ai_max_retries is None and env_ai_max_retries is not None:
            self.ai_max_retries = env_ai_max_retries

        if self.ai_provider == "kimi":
            if env_ai_model_name is None and env_kimi_model:
                self.ai_model_name = env_kimi_model
            if self.ai_gateway_endpoint is None and env_kimi_base_url:
                self.ai_gateway_endpoint = env_kimi_base_url
            if self.ai_api_key is None:
                self.ai_api_key = env_kimi_api_key

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
        if self.ai_runtime_config_path is None:
            self.ai_runtime_config_path = (
                self.project_root
                / "mocks"
                / "config"
                / "downstream_outputs"
                / "ai_runtime_config.json"
            )
        if self.delivery_channel_config_path is None:
            self.delivery_channel_config_path = (
                self.project_root
                / "mocks"
                / "config"
                / "downstream_outputs"
                / "delivery_channel_configs.json"
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
        self.ai_runtime_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.delivery_channel_config_path.parent.mkdir(parents=True, exist_ok=True)

    def resolve_ai_runtime_overrides(
        self,
        default_prompt_template_path: Path,
    ) -> dict[str, Any]:
        overrides: dict[str, Any] = {}
        if self.ai_enabled is not None:
            overrides["enabled"] = self.ai_enabled
        if self.ai_provider != DEFAULT_AI_PROVIDER:
            overrides["provider"] = self.ai_provider
        if self.ai_model_name != DEFAULT_AI_MODEL_NAME:
            overrides["model_name"] = self.ai_model_name
        if self.ai_prompt_version != DEFAULT_AI_PROMPT_VERSION:
            overrides["prompt_version"] = self.ai_prompt_version
        if self.ai_gateway_endpoint is not None:
            overrides["endpoint"] = self.ai_gateway_endpoint
        if self.ai_api_key is not None:
            overrides["api_key"] = self.ai_api_key
        if self.ai_max_retries is not None:
            overrides["max_retries"] = self.ai_max_retries
        if (
            self.ai_prompt_template_path is not None
            and self.ai_prompt_template_path != default_prompt_template_path
        ):
            overrides["template_path"] = str(self.ai_prompt_template_path)
        return overrides

    @staticmethod
    def _parse_env_bool(value: str | None) -> bool | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return None

    @staticmethod
    def _parse_env_int(value: str | None) -> int | None:
        if value is None:
            return None
        try:
            return int(value.strip())
        except ValueError:
            return None
