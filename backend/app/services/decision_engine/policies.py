from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from backend.app.core.database import get_connection
from backend.app.shared.models import DecisionAction


class PushPolicyConfig(BaseModel):
    policy_id: str
    policy_name: str
    enabled: bool = True
    action: DecisionAction
    conditions: dict[str, Any] = Field(default_factory=dict)
    channels: list[str] = Field(default_factory=list)
    version: str


def load_push_policies_from_file(file_path: Path) -> list[PushPolicyConfig]:
    with file_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    return [PushPolicyConfig.model_validate(item) for item in payload]


class DecisionPolicyProvider(ABC):
    @abstractmethod
    async def get_active_policies(self) -> list[PushPolicyConfig]:
        raise NotImplementedError


class FileDecisionPolicyProvider(DecisionPolicyProvider):
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path

    async def get_active_policies(self) -> list[PushPolicyConfig]:
        return [policy for policy in load_push_policies_from_file(self.file_path) if policy.enabled]


class SQLiteDecisionPolicyProvider(DecisionPolicyProvider):
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    async def get_active_policies(self) -> list[PushPolicyConfig]:
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT config_json
                FROM push_policy_configs
                WHERE enabled = 1
                ORDER BY action ASC, policy_id ASC
                """
            ).fetchall()
        return [PushPolicyConfig.model_validate(json.loads(row["config_json"])) for row in rows]
