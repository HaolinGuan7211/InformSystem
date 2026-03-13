from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.core.database import get_connection


def _resolve_config_paths(config: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    resolved = dict(config)
    for key, value in list(resolved.items()):
        if key.endswith("_path") and isinstance(value, str):
            path = Path(value)
            resolved[key] = str(path if path.is_absolute() else (base_dir / path).resolve())
    return resolved


def load_source_configs_from_file(file_path: Path) -> list[dict[str, Any]]:
    with file_path.open("r", encoding="utf-8") as file:
        configs = json.load(file)
    return [_resolve_config_paths(config, file_path.parent) for config in configs]


class SourceConfigRepository(ABC):
    @abstractmethod
    async def list_enabled_sources(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def get_source_by_id(self, source_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    async def upsert_many(self, source_configs: list[dict[str, Any]]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def count(self) -> int:
        raise NotImplementedError


class FileSourceConfigRepository(SourceConfigRepository):
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path

    async def list_enabled_sources(self) -> list[dict[str, Any]]:
        return [config for config in load_source_configs_from_file(self.file_path) if config.get("enabled", True)]

    async def get_source_by_id(self, source_id: str) -> dict[str, Any] | None:
        for config in load_source_configs_from_file(self.file_path):
            if config["source_id"] == source_id:
                return config
        return None

    async def upsert_many(self, source_configs: list[dict[str, Any]]) -> None:
        with self.file_path.open("w", encoding="utf-8") as file:
            json.dump(source_configs, file, ensure_ascii=False, indent=2)

    async def count(self) -> int:
        return len(load_source_configs_from_file(self.file_path))


class SQLiteSourceConfigRepository(SourceConfigRepository):
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    async def list_enabled_sources(self) -> list[dict[str, Any]]:
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                "SELECT config_json FROM source_configs WHERE enabled = 1 ORDER BY priority DESC, source_id ASC"
            ).fetchall()
        return [json.loads(row["config_json"]) for row in rows]

    async def get_source_by_id(self, source_id: str) -> dict[str, Any] | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT config_json FROM source_configs WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        return json.loads(row["config_json"]) if row else None

    async def upsert_many(self, source_configs: list[dict[str, Any]]) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        with get_connection(self.database_path) as connection:
            connection.executemany(
                """
                INSERT INTO source_configs (
                    source_id,
                    source_name,
                    source_type,
                    connector_type,
                    enabled,
                    auth_config,
                    parse_config,
                    polling_schedule,
                    authority_level,
                    priority,
                    config_json,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    source_name = excluded.source_name,
                    source_type = excluded.source_type,
                    connector_type = excluded.connector_type,
                    enabled = excluded.enabled,
                    auth_config = excluded.auth_config,
                    parse_config = excluded.parse_config,
                    polling_schedule = excluded.polling_schedule,
                    authority_level = excluded.authority_level,
                    priority = excluded.priority,
                    config_json = excluded.config_json,
                    updated_at = excluded.updated_at
                """,
                [
                    (
                        config["source_id"],
                        config["source_name"],
                        config["source_type"],
                        config["connector_type"],
                        int(config.get("enabled", True)),
                        json.dumps(config.get("auth_config", {}), ensure_ascii=False),
                        json.dumps(config.get("parse_config", {}), ensure_ascii=False),
                        config.get("polling_schedule"),
                        config.get("authority_level"),
                        config.get("priority", 0),
                        json.dumps(config, ensure_ascii=False),
                        timestamp,
                    )
                    for config in source_configs
                ],
            )
            connection.commit()

    async def count(self) -> int:
        with get_connection(self.database_path) as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM source_configs").fetchone()
        return int(row["total"])


def bootstrap_source_configs_if_empty(database_path: Path, source_config_path: Path) -> None:
    configs = load_source_configs_from_file(source_config_path)
    with get_connection(database_path) as connection:
        row = connection.execute("SELECT COUNT(*) AS total FROM source_configs").fetchone()
        if int(row["total"]) > 0:
            return

        timestamp = datetime.now(timezone.utc).isoformat()
        connection.executemany(
            """
            INSERT INTO source_configs (
                source_id,
                source_name,
                source_type,
                connector_type,
                enabled,
                auth_config,
                parse_config,
                polling_schedule,
                authority_level,
                priority,
                config_json,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    config["source_id"],
                    config["source_name"],
                    config["source_type"],
                    config["connector_type"],
                    int(config.get("enabled", True)),
                    json.dumps(config.get("auth_config", {}), ensure_ascii=False),
                    json.dumps(config.get("parse_config", {}), ensure_ascii=False),
                    config.get("polling_schedule"),
                    config.get("authority_level"),
                    config.get("priority", 0),
                    json.dumps(config, ensure_ascii=False),
                    timestamp,
                )
                for config in configs
            ],
        )
        connection.commit()

