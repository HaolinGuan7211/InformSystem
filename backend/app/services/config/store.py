from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from backend.app.core.database import get_connection
from backend.app.services.config.models import (
    AIRuntimeConfig,
    ConfigChangeLog,
    DeliveryChannelConfig,
    NotificationCategoryConfig,
    PushPolicyConfig,
    RuleBundle,
    RuleConfig,
    SourceConfig,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def _resolve_source_paths(config: dict, base_dir: Path) -> dict:
    resolved = dict(config)
    for key, value in list(resolved.items()):
        if key.endswith("_path") and isinstance(value, str):
            path = Path(value)
            resolved[key] = str(path if path.is_absolute() else (base_dir / path).resolve())
    return resolved


@dataclass(slots=True)
class ConfigFilePaths:
    source_config_path: Path
    rule_config_path: Path
    notification_category_path: Path
    ai_runtime_config_path: Path = field(default_factory=lambda: Path("ai_runtime_config.json"))
    delivery_channel_config_path: Path = field(default_factory=lambda: Path("delivery_channel_configs.json"))
    push_policy_path: Path = field(default_factory=lambda: Path("push_policies.json"))
    audit_log_path: Path = field(default_factory=lambda: Path("change_logs.json"))


class FileConfigStore:
    def __init__(self, paths: ConfigFilePaths) -> None:
        self._paths = paths

    def list_source_configs(self) -> list[SourceConfig]:
        payload = _read_json(self._paths.source_config_path, [])
        configs = [
            SourceConfig.model_validate(
                _resolve_source_paths(item, self._paths.source_config_path.parent)
            )
            for item in payload
        ]
        return sorted(configs, key=lambda item: (-item.priority, item.source_id))

    def get_source_config(self, source_id: str) -> SourceConfig | None:
        for config in self.list_source_configs():
            if config.source_id == source_id:
                return config
        return None

    def replace_source_configs(self, configs: list[SourceConfig], version: str) -> None:
        payload = [
            config.model_copy(update={"version": config.version or version}).model_dump(
                mode="json",
                exclude_none=True,
            )
            for config in configs
        ]
        _write_json(self._paths.source_config_path, payload)

    def get_rule_bundle(self, scene: str | None = None) -> RuleBundle:
        payload = _read_json(
            self._paths.rule_config_path,
            {"version": "v0", "ai_gate": {}, "thresholds": {}, "rules": []},
        )
        bundle = RuleBundle.model_validate(payload)
        if scene is None:
            return bundle
        filtered_rules = [rule for rule in bundle.rules if rule.scene == scene and rule.enabled]
        return bundle.model_copy(update={"rules": filtered_rules})

    def replace_rule_bundle(self, bundle: RuleBundle) -> None:
        _write_json(
            self._paths.rule_config_path,
            bundle.model_dump(mode="json", exclude_none=True),
        )

    def list_categories(self) -> list[NotificationCategoryConfig]:
        payload = _read_json(self._paths.notification_category_path, [])
        configs = [NotificationCategoryConfig.model_validate(item) for item in payload]
        return sorted(configs, key=lambda item: item.category_id)

    def replace_categories(
        self,
        categories: list[NotificationCategoryConfig],
        version: str,
    ) -> None:
        payload = [
            item.model_copy(update={"version": item.version or version}).model_dump(
                mode="json",
                exclude_none=True,
            )
            for item in categories
        ]
        _write_json(self._paths.notification_category_path, payload)

    def get_ai_runtime_config(self) -> AIRuntimeConfig:
        payload = _read_json(
            self._paths.ai_runtime_config_path,
            {
                "config_id": "default",
                "enabled": True,
                "provider": "mock",
                "model_name": "gpt-5-mini",
                "prompt_version": "prompt_v1",
                "template_path": "backend/app/services/ai_processing/prompts/notice_analysis_v1.txt",
                "version": "ai_runtime_v1",
            },
        )
        config = AIRuntimeConfig.model_validate(payload)
        template_path = Path(config.template_path)
        if not template_path.is_absolute():
            config = config.model_copy(
                update={
                    "template_path": str(
                        (self._paths.ai_runtime_config_path.parent / template_path).resolve()
                    )
                }
            )
        return config

    def replace_ai_runtime_config(self, config: AIRuntimeConfig) -> None:
        payload = config.model_dump(mode="json", exclude_none=True)
        template_path = Path(payload["template_path"])
        if template_path.is_absolute():
            try:
                payload["template_path"] = str(
                    template_path.relative_to(self._paths.ai_runtime_config_path.parent)
                )
            except ValueError:
                payload["template_path"] = str(template_path)
        _write_json(self._paths.ai_runtime_config_path, payload)

    def list_delivery_channel_configs(self) -> list[DeliveryChannelConfig]:
        payload = _read_json(self._paths.delivery_channel_config_path, [])
        configs = [DeliveryChannelConfig.model_validate(item) for item in payload]
        return sorted(configs, key=lambda item: item.channel)

    def get_delivery_channel_config(self, channel: str) -> DeliveryChannelConfig | None:
        for config in self.list_delivery_channel_configs():
            if config.channel == channel:
                return config
        return None

    def replace_delivery_channel_configs(
        self,
        configs: list[DeliveryChannelConfig],
        version: str,
    ) -> None:
        payload = [
            config.model_copy(update={"version": config.version or version}).model_dump(
                mode="json",
                exclude_none=True,
            )
            for config in configs
        ]
        _write_json(self._paths.delivery_channel_config_path, payload)

    def list_push_policies(self) -> list[PushPolicyConfig]:
        payload = _read_json(self._paths.push_policy_path, [])
        policies = [PushPolicyConfig.model_validate(item) for item in payload]
        return sorted(policies, key=lambda item: (item.action, item.policy_id))

    def replace_push_policies(self, policies: list[PushPolicyConfig], version: str) -> None:
        payload = [
            policy.model_copy(update={"version": version}).model_dump(
                mode="json",
                exclude_none=True,
            )
            for policy in policies
        ]
        _write_json(self._paths.push_policy_path, payload)

    def list_change_logs(self, config_type: str | None = None) -> list[ConfigChangeLog]:
        payload = _read_json(self._paths.audit_log_path, [])
        logs = [ConfigChangeLog.model_validate(item) for item in payload]
        if config_type is not None:
            logs = [log for log in logs if log.config_type == config_type]
        logs.sort(key=lambda item: (item.created_at, item.change_id))
        return logs

    def get_change_log(self, config_type: str, version: str) -> ConfigChangeLog | None:
        matching = [
            log
            for log in self.list_change_logs(config_type)
            if log.version == version
        ]
        return matching[-1] if matching else None

    def get_latest_change_log(self, config_type: str) -> ConfigChangeLog | None:
        logs = self.list_change_logs(config_type)
        return logs[-1] if logs else None

    def append_change_log(self, change_log: ConfigChangeLog) -> None:
        payload = [
            log.model_dump(mode="json", exclude_none=True)
            for log in self.list_change_logs()
        ]
        payload.append(change_log.model_dump(mode="json", exclude_none=True))
        _write_json(self._paths.audit_log_path, payload)


class SQLiteConfigStore:
    def __init__(
        self,
        database_path: Path,
        runtime_store: FileConfigStore | None = None,
    ) -> None:
        self._database_path = database_path
        self._runtime_store = runtime_store or FileConfigStore(
            ConfigFilePaths(
                source_config_path=database_path.parent / "source_configs.json",
                rule_config_path=database_path.parent / "rule_configs.json",
                notification_category_path=database_path.parent / "notification_categories.json",
                ai_runtime_config_path=database_path.parent / "ai_runtime_config.json",
                delivery_channel_config_path=database_path.parent / "delivery_channel_configs.json",
                push_policy_path=database_path.parent / "push_policies.json",
                audit_log_path=database_path.parent / "config_change_logs.json",
            )
        )

    def list_source_configs(self) -> list[SourceConfig]:
        with get_connection(self._database_path) as connection:
            rows = connection.execute(
                """
                SELECT config_json
                FROM source_configs
                ORDER BY priority DESC, source_id ASC
                """
            ).fetchall()
        return [SourceConfig.model_validate(json.loads(row["config_json"])) for row in rows]

    def get_source_config(self, source_id: str) -> SourceConfig | None:
        with get_connection(self._database_path) as connection:
            row = connection.execute(
                "SELECT config_json FROM source_configs WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        if row is None:
            return None
        return SourceConfig.model_validate(json.loads(row["config_json"]))

    def replace_source_configs(self, configs: list[SourceConfig], version: str) -> None:
        timestamp = _utc_now()
        stamped = [
            config.model_copy(update={"version": config.version or version})
            for config in configs
        ]

        with get_connection(self._database_path) as connection:
            connection.execute("DELETE FROM source_configs")
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
                    version,
                    config_json,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        config.source_id,
                        config.source_name,
                        config.source_type,
                        config.connector_type,
                        int(config.enabled),
                        json.dumps(config.auth_config, ensure_ascii=False),
                        json.dumps(config.parse_config, ensure_ascii=False),
                        config.polling_schedule,
                        config.authority_level,
                        config.priority,
                        config.version,
                        json.dumps(
                            config.model_dump(mode="json", exclude_none=True),
                            ensure_ascii=False,
                        ),
                        timestamp,
                        timestamp,
                    )
                    for config in stamped
                ],
            )
            connection.commit()

    def get_rule_bundle(self, scene: str | None = None) -> RuleBundle:
        version = self._active_version("rule_configs")
        snapshot = self.get_change_log("rule_configs", version) if version else None
        query = """
            SELECT config_json
            FROM rule_configs
            WHERE enabled = 1
        """
        params: list[str] = []
        if version:
            query += " AND version = ?"
            params.append(version)
        if scene is not None:
            query += " AND scene = ?"
            params.append(scene)
        query += " ORDER BY priority DESC, rule_id ASC"

        with get_connection(self._database_path) as connection:
            rows = connection.execute(query, params).fetchall()

        rules = [RuleConfig.model_validate(json.loads(row["config_json"])) for row in rows]
        payload = snapshot.payload if snapshot is not None else {}
        return RuleBundle(
            version=version or payload.get("version") or "v0",
            ai_gate=payload.get("ai_gate", {}),
            thresholds=payload.get("thresholds", {}),
            rules=rules,
        )

    def replace_rule_bundle(self, bundle: RuleBundle) -> None:
        timestamp = _utc_now()
        stamped_rules = [
            rule.model_copy(update={"version": bundle.version})
            for rule in bundle.rules
        ]

        with get_connection(self._database_path) as connection:
            connection.execute("DELETE FROM rule_configs WHERE version = ?", (bundle.version,))
            connection.executemany(
                """
                INSERT INTO rule_configs (
                    rule_id,
                    version,
                    rule_name,
                    scene,
                    enabled,
                    priority,
                    conditions_json,
                    outputs_json,
                    config_json,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        rule.rule_id,
                        bundle.version,
                        rule.rule_name,
                        rule.scene,
                        int(rule.enabled),
                        rule.priority,
                        json.dumps(rule.conditions, ensure_ascii=False),
                        json.dumps(rule.outputs, ensure_ascii=False),
                        json.dumps(rule.model_dump(mode="json"), ensure_ascii=False),
                        timestamp,
                        timestamp,
                    )
                    for rule in stamped_rules
                ],
            )
            connection.commit()

    def list_categories(self) -> list[NotificationCategoryConfig]:
        with get_connection(self._database_path) as connection:
            rows = connection.execute(
                """
                SELECT config_json
                FROM notification_category_configs
                ORDER BY category_id ASC
                """
            ).fetchall()
        return [
            NotificationCategoryConfig.model_validate(json.loads(row["config_json"]))
            for row in rows
        ]

    def replace_categories(
        self,
        categories: list[NotificationCategoryConfig],
        version: str,
    ) -> None:
        timestamp = _utc_now()
        stamped = [
            item.model_copy(update={"version": item.version or version})
            for item in categories
        ]

        with get_connection(self._database_path) as connection:
            connection.execute("DELETE FROM notification_category_configs")
            connection.executemany(
                """
                INSERT INTO notification_category_configs (
                    category_id,
                    category_name,
                    parent_category,
                    keywords_json,
                    enabled,
                    config_json,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.category_id,
                        item.category_name,
                        item.parent_category,
                        json.dumps(item.keywords, ensure_ascii=False),
                        int(item.enabled),
                        json.dumps(
                            item.model_dump(mode="json", exclude_none=True),
                            ensure_ascii=False,
                        ),
                        timestamp,
                        timestamp,
                    )
                    for item in stamped
                ],
            )
            connection.commit()

    def get_ai_runtime_config(self) -> AIRuntimeConfig:
        version = self._active_version("ai_runtime_configs")
        query = """
            SELECT config_json
            FROM ai_runtime_configs
            WHERE config_id = ?
        """
        params: list[str] = ["default"]
        if version:
            query += " AND version = ?"
            params.append(version)
        query += " ORDER BY updated_at DESC, version DESC LIMIT 1"

        with get_connection(self._database_path) as connection:
            row = connection.execute(query, params).fetchone()
        if row is not None:
            return AIRuntimeConfig.model_validate(json.loads(row["config_json"]))

        snapshot = self.get_change_log("ai_runtime_configs", version) if version else None
        if snapshot is not None:
            return AIRuntimeConfig.model_validate(snapshot.payload)
        raise ValueError("missing ai runtime config in sqlite store")

    def replace_ai_runtime_config(self, config: AIRuntimeConfig) -> None:
        timestamp = _utc_now()

        with get_connection(self._database_path) as connection:
            connection.execute(
                "DELETE FROM ai_runtime_configs WHERE config_id = ? AND version = ?",
                (config.config_id, config.version),
            )
            connection.execute(
                """
                INSERT INTO ai_runtime_configs (
                    config_id,
                    version,
                    enabled,
                    provider,
                    model_name,
                    prompt_version,
                    template_path,
                    endpoint,
                    api_key,
                    timeout_seconds,
                    max_retries,
                    metadata_json,
                    config_json,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    config.config_id,
                    config.version,
                    int(config.enabled),
                    config.provider,
                    config.model_name,
                    config.prompt_version,
                    config.template_path,
                    config.endpoint,
                    config.api_key,
                    config.timeout_seconds,
                    config.max_retries,
                    json.dumps(config.metadata, ensure_ascii=False),
                    json.dumps(config.model_dump(mode="json", exclude_none=True), ensure_ascii=False),
                    timestamp,
                    timestamp,
                ),
            )
            connection.commit()

    def list_delivery_channel_configs(self) -> list[DeliveryChannelConfig]:
        if self._runtime_store is None:
            return []
        return self._runtime_store.list_delivery_channel_configs()

    def get_delivery_channel_config(self, channel: str) -> DeliveryChannelConfig | None:
        if self._runtime_store is None:
            return None
        return self._runtime_store.get_delivery_channel_config(channel)

    def replace_delivery_channel_configs(
        self,
        configs: list[DeliveryChannelConfig],
        version: str,
    ) -> None:
        if self._runtime_store is None:
            raise ValueError("runtime store is not configured for delivery channel configs")
        self._runtime_store.replace_delivery_channel_configs(configs, version)

    def list_push_policies(self) -> list[PushPolicyConfig]:
        version = self._active_version("push_policy_configs")
        query = """
            SELECT config_json
            FROM push_policy_configs
            WHERE enabled = 1
        """
        params: list[str] = []
        if version:
            query += " AND version = ?"
            params.append(version)
        query += " ORDER BY action ASC, policy_id ASC"

        with get_connection(self._database_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [PushPolicyConfig.model_validate(json.loads(row["config_json"])) for row in rows]

    def replace_push_policies(self, policies: list[PushPolicyConfig], version: str) -> None:
        timestamp = _utc_now()
        stamped = [policy.model_copy(update={"version": version}) for policy in policies]

        with get_connection(self._database_path) as connection:
            connection.execute("DELETE FROM push_policy_configs WHERE version = ?", (version,))
            connection.executemany(
                """
                INSERT INTO push_policy_configs (
                    policy_id,
                    version,
                    policy_name,
                    enabled,
                    action,
                    conditions_json,
                    channels_json,
                    config_json,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        policy.policy_id,
                        version,
                        policy.policy_name,
                        int(policy.enabled),
                        policy.action,
                        json.dumps(policy.conditions, ensure_ascii=False),
                        json.dumps(policy.channels, ensure_ascii=False),
                        json.dumps(policy.model_dump(mode="json"), ensure_ascii=False),
                        timestamp,
                        timestamp,
                    )
                    for policy in stamped
                ],
            )
            connection.commit()

    def list_change_logs(self, config_type: str | None = None) -> list[ConfigChangeLog]:
        query = """
            SELECT change_id, config_type, version, operator, action, payload_json, created_at
            FROM config_change_logs
        """
        params: list[str] = []
        if config_type is not None:
            query += " WHERE config_type = ?"
            params.append(config_type)
        query += " ORDER BY created_at ASC, change_id ASC"

        with get_connection(self._database_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_change_log(row) for row in rows]

    def get_change_log(self, config_type: str, version: str) -> ConfigChangeLog | None:
        with get_connection(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT change_id, config_type, version, operator, action, payload_json, created_at
                FROM config_change_logs
                WHERE config_type = ? AND version = ?
                ORDER BY created_at DESC, change_id DESC
                LIMIT 1
                """,
                (config_type, version),
            ).fetchone()
        return self._row_to_change_log(row) if row is not None else None

    def get_latest_change_log(self, config_type: str) -> ConfigChangeLog | None:
        with get_connection(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT change_id, config_type, version, operator, action, payload_json, created_at
                FROM config_change_logs
                WHERE config_type = ?
                ORDER BY created_at DESC, change_id DESC
                LIMIT 1
                """,
                (config_type,),
            ).fetchone()
        return self._row_to_change_log(row) if row is not None else None

    def append_change_log(self, change_log: ConfigChangeLog) -> None:
        with get_connection(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO config_change_logs (
                    change_id,
                    config_type,
                    version,
                    operator,
                    action,
                    payload_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    change_log.change_id,
                    change_log.config_type,
                    change_log.version,
                    change_log.operator,
                    change_log.action,
                    json.dumps(change_log.payload, ensure_ascii=False),
                    change_log.created_at,
                ),
            )
            connection.commit()

    def _row_to_change_log(self, row) -> ConfigChangeLog:
        return ConfigChangeLog(
            change_id=row["change_id"],
            config_type=row["config_type"],
            version=row["version"],
            operator=row["operator"],
            action=row["action"],
            payload=json.loads(row["payload_json"]),
            created_at=row["created_at"],
        )

    def _active_version(self, config_type: str) -> str | None:
        latest = self.get_latest_change_log(config_type)
        if latest is not None:
            return latest.version

        table_name = {
            "rule_configs": "rule_configs",
            "ai_runtime_configs": "ai_runtime_configs",
            "push_policy_configs": "push_policy_configs",
        }.get(config_type)
        if table_name is None:
            return None

        with get_connection(self._database_path) as connection:
            row = connection.execute(
                f"SELECT version FROM {table_name} ORDER BY updated_at DESC, version DESC LIMIT 1"
            ).fetchone()
        return row["version"] if row else None
