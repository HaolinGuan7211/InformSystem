from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from backend.app.services.config.cache import MemoryConfigCache
from backend.app.services.config.models import (
    ConfigAction,
    ConfigChangeLog,
    ConfigType,
    NotificationCategoryConfig,
    PushPolicyConfig,
    RuleBundle,
    RuleConfig,
    SourceConfig,
)


class ConfigService:
    def __init__(self, store, cache: MemoryConfigCache | None = None) -> None:
        self._store = store
        self._cache = cache or MemoryConfigCache()

    async def get_source_config(self, source_id: str) -> SourceConfig | None:
        return self.get_source_config_sync(source_id)

    async def get_source_by_id(self, source_id: str) -> SourceConfig | None:
        return self.get_source_config_sync(source_id)

    def get_source_config_sync(self, source_id: str) -> SourceConfig | None:
        cache_key = f"source:{source_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        config = self._store.get_source_config(source_id)
        if config is not None:
            self._cache.set(cache_key, config)
        return config

    async def list_source_configs(self) -> list[SourceConfig]:
        return self.list_source_configs_sync()

    def list_source_configs_sync(self) -> list[SourceConfig]:
        cache_key = "source_configs:all"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        configs = self._store.list_source_configs()
        self._cache.set(cache_key, configs)
        return configs

    async def list_enabled_sources(self) -> list[SourceConfig]:
        return self.list_enabled_sources_sync()

    def list_enabled_sources_sync(self) -> list[SourceConfig]:
        cache_key = "source_configs:enabled"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        configs = [config for config in self.list_source_configs_sync() if config.enabled]
        self._cache.set(cache_key, configs)
        return configs

    async def get_rule_bundle(self, scene: str | None = None) -> RuleBundle:
        return self.get_rule_bundle_sync(scene)

    def get_rule_bundle_sync(self, scene: str | None = None) -> RuleBundle:
        cache_key = f"rule_bundle:{scene or 'all'}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        bundle = self._store.get_rule_bundle(scene)
        self._cache.set(cache_key, bundle)
        return bundle

    async def get_rule_configs(self, scene: str | None = None) -> list[RuleConfig]:
        return self.get_rule_bundle_sync(scene).rules

    async def list_categories(self) -> list[NotificationCategoryConfig]:
        return self.list_categories_sync()

    def list_categories_sync(self) -> list[NotificationCategoryConfig]:
        cache_key = "notification_category_configs"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        categories = self._store.list_categories()
        self._cache.set(cache_key, categories)
        return categories

    async def get_push_policies(self) -> list[PushPolicyConfig]:
        return self.get_push_policies_sync()

    async def get_active_policies(self) -> list[PushPolicyConfig]:
        return self.get_push_policies_sync()

    def get_push_policies_sync(self) -> list[PushPolicyConfig]:
        cache_key = "push_policy_configs"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        policies = self._store.list_push_policies()
        self._cache.set(cache_key, policies)
        return policies

    async def list_change_logs(
        self,
        config_type: ConfigType | None = None,
    ) -> list[ConfigChangeLog]:
        return self._store.list_change_logs(config_type)

    async def publish_config(
        self,
        config_type: ConfigType,
        payload: Any,
        operator: str,
        version: str | None = None,
    ) -> str:
        return self.publish_config_sync(config_type, payload, operator, version)

    def publish_config_sync(
        self,
        config_type: ConfigType,
        payload: Any,
        operator: str,
        version: str | None = None,
        action: ConfigAction = "publish",
    ) -> str:
        normalized, resolved_version = self._normalize_payload(config_type, payload, version)
        self._write_payload(config_type, normalized, resolved_version)
        self._store.append_change_log(
            ConfigChangeLog(
                change_id=self._build_change_id(config_type, resolved_version, action),
                config_type=config_type,
                version=resolved_version,
                operator=operator,
                action=action,
                payload=self._serialize_payload(normalized),
                created_at=self._now(),
            )
        )
        self._invalidate_cache()
        return resolved_version

    async def rollback(
        self,
        config_type: ConfigType,
        version: str,
        operator: str,
    ) -> None:
        self.rollback_sync(config_type, version, operator)

    def rollback_sync(
        self,
        config_type: ConfigType,
        version: str,
        operator: str,
    ) -> None:
        target = self._store.get_change_log(config_type, version)
        if target is None:
            raise ValueError(f"missing config snapshot for {config_type}:{version}")

        normalized, _ = self._normalize_payload(config_type, target.payload, version)
        self.publish_config_sync(
            config_type=config_type,
            payload=normalized,
            operator=operator,
            version=version,
            action="rollback",
        )

    def ensure_seed_data(self, seed_store, operator: str = "system_bootstrap") -> None:
        for config_type, payload in [
            ("source_configs", seed_store.list_source_configs()),
            ("rule_configs", seed_store.get_rule_bundle()),
            ("notification_category_configs", seed_store.list_categories()),
            ("push_policy_configs", seed_store.list_push_policies()),
        ]:
            if self._store.get_latest_change_log(config_type) is not None:
                continue
            self.publish_config_sync(
                config_type=config_type,
                payload=payload,
                operator=operator,
                version=self._infer_version(config_type, payload),
                action="bootstrap",
            )

    def _write_payload(self, config_type: ConfigType, payload: Any, version: str) -> None:
        if config_type == "source_configs":
            self._store.replace_source_configs(payload, version)
            return
        if config_type == "rule_configs":
            self._store.replace_rule_bundle(payload)
            return
        if config_type == "notification_category_configs":
            self._store.replace_categories(payload, version)
            return
        if config_type == "push_policy_configs":
            self._store.replace_push_policies(payload, version)
            return
        raise ValueError(f"unsupported config type: {config_type}")

    def _normalize_payload(
        self,
        config_type: ConfigType,
        payload: Any,
        version: str | None,
    ) -> tuple[Any, str]:
        resolved_version = version or self._infer_version(config_type, payload)

        if config_type == "source_configs":
            items = payload.get("items") if isinstance(payload, dict) and "items" in payload else payload
            configs = [SourceConfig.model_validate(item) for item in items]
            stamped = [
                config.model_copy(update={"version": resolved_version})
                for config in configs
            ]
            return stamped, resolved_version

        if config_type == "rule_configs":
            bundle = RuleBundle.model_validate(payload)
            stamped_rules = [
                rule.model_copy(update={"version": resolved_version})
                for rule in bundle.rules
            ]
            stamped_bundle = bundle.model_copy(
                update={"version": resolved_version, "rules": stamped_rules}
            )
            return stamped_bundle, resolved_version

        if config_type == "notification_category_configs":
            items = payload.get("items") if isinstance(payload, dict) and "items" in payload else payload
            categories = [NotificationCategoryConfig.model_validate(item) for item in items]
            stamped = [
                item.model_copy(update={"version": resolved_version})
                for item in categories
            ]
            return stamped, resolved_version

        if config_type == "push_policy_configs":
            items = payload.get("items") if isinstance(payload, dict) and "items" in payload else payload
            policies = [PushPolicyConfig.model_validate(item) for item in items]
            stamped = [
                item.model_copy(update={"version": resolved_version})
                for item in policies
            ]
            return stamped, resolved_version

        raise ValueError(f"unsupported config type: {config_type}")

    def _serialize_payload(self, payload: Any) -> Any:
        if isinstance(payload, RuleBundle):
            return payload.model_dump(mode="json", exclude_none=True)
        if isinstance(payload, list):
            return [item.model_dump(mode="json", exclude_none=True) for item in payload]
        return payload

    def _infer_version(self, config_type: ConfigType, payload: Any) -> str:
        if isinstance(payload, RuleBundle):
            return payload.version

        if isinstance(payload, dict) and isinstance(payload.get("version"), str):
            return payload["version"]

        if isinstance(payload, list) and payload:
            first = payload[0]
            if hasattr(first, "version") and getattr(first, "version", None):
                return getattr(first, "version")
            if isinstance(first, dict) and isinstance(first.get("version"), str):
                versions = {item.get("version") for item in payload if isinstance(item, dict)}
                versions.discard(None)
                if len(versions) == 1:
                    return versions.pop()

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        prefix = config_type.removesuffix("_configs")
        return f"{prefix}_v{timestamp}"

    def _invalidate_cache(self) -> None:
        self._cache.invalidate()

    def _build_change_id(self, config_type: str, version: str, action: str) -> str:
        digest = hashlib.sha1(f"{config_type}:{version}:{action}:{self._now()}".encode("utf-8")).hexdigest()
        return f"cfgchg_{digest[:12]}"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
