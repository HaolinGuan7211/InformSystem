from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.shared.models import DecisionAction

ConfigType = Literal[
    "source_configs",
    "rule_configs",
    "notification_category_configs",
    "push_policy_configs",
]
ConfigAction = Literal["publish", "rollback", "bootstrap"]


class SourceConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    source_id: str
    source_name: str
    source_type: str
    connector_type: str
    enabled: bool = True
    auth_config: dict[str, Any] = Field(default_factory=dict)
    parse_config: dict[str, Any] = Field(default_factory=dict)
    polling_schedule: str | None = None
    authority_level: str | None = None
    priority: int = 0
    version: str | None = None


class RuleConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    rule_id: str
    rule_name: str
    scene: str
    enabled: bool = True
    priority: int = 0
    conditions: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    version: str


class RuleBundle(BaseModel):
    version: str
    ai_gate: dict[str, Any] = Field(default_factory=dict)
    thresholds: dict[str, Any] = Field(default_factory=dict)
    rules: list[RuleConfig] = Field(default_factory=list)


class NotificationCategoryConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    category_id: str
    category_name: str
    parent_category: str | None = None
    keywords: list[str] = Field(default_factory=list)
    enabled: bool = True
    version: str | None = None


class PushPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    policy_id: str
    policy_name: str
    enabled: bool = True
    action: DecisionAction
    conditions: dict[str, Any] = Field(default_factory=dict)
    channels: list[str] = Field(default_factory=list)
    version: str


class ConfigChangeLog(BaseModel):
    change_id: str
    config_type: ConfigType
    version: str
    operator: str
    action: ConfigAction
    payload: Any
    created_at: str
