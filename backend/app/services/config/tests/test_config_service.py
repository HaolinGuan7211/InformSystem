from __future__ import annotations

from backend.app.container import build_container
from backend.app.services.config import ConfigFilePaths, ConfigService, FileConfigStore, SQLiteConfigStore
from backend.app.services.config.models import AIRuntimeConfig
from backend.app.services.decision_engine.policy_loader import PolicyLoader
from backend.app.services.rule_engine.config_loader import RuleConfigLoader


async def test_sqlite_config_service_bootstraps_and_serves_contracts(
    sqlite_config_service,
):
    sources = await sqlite_config_service.list_enabled_sources()
    assert {source.source_id for source in sources} == {
        "wecom_cs_notice_group",
        "school_website_notice",
        "manual_input_default",
    }

    rule_bundle = await sqlite_config_service.get_rule_bundle("rule_engine")
    assert rule_bundle.version == "v1"
    assert rule_bundle.thresholds["relevant_score"] == 0.7
    assert all(rule.enabled for rule in rule_bundle.rules)

    categories = await sqlite_config_service.list_categories()
    assert {category.category_id for category in categories} >= {"graduation", "material_submission"}

    policies = await sqlite_config_service.get_push_policies()
    assert {policy.version for policy in policies} == {"policy_v1"}
    assert any(policy.action == "push_now" for policy in policies)

    ai_runtime = await sqlite_config_service.get_ai_runtime_config()
    assert ai_runtime.prompt_version == "prompt_v1"
    assert ai_runtime.model_name == "gpt-5-mini"

    delivery_channels = await sqlite_config_service.list_delivery_channel_configs()
    assert {item.channel for item in delivery_channels} == {"app_push", "email"}

    change_logs = await sqlite_config_service.list_change_logs()
    assert len(change_logs) == 6


async def test_publish_and_rollback_policy_snapshot(sqlite_config_service):
    baseline = await sqlite_config_service.get_push_policies()
    published_version = await sqlite_config_service.publish_config(
        "push_policy_configs",
        [
            {
                **policy.model_dump(mode="json"),
                "channels": ["app_push", "email"],
            }
            for policy in baseline
        ],
        operator="tester",
        version="policy_v2",
    )

    assert published_version == "policy_v2"
    updated = await sqlite_config_service.get_push_policies()
    assert {policy.version for policy in updated} == {"policy_v2"}
    assert any(policy.channels == ["app_push", "email"] for policy in updated)

    await sqlite_config_service.rollback("push_policy_configs", "policy_v1", operator="tester")
    rolled_back = await sqlite_config_service.get_push_policies()
    assert {policy.version for policy in rolled_back} == {"policy_v1"}
    assert all(policy.channels in (["app_push"], []) for policy in rolled_back)

    change_logs = await sqlite_config_service.list_change_logs("push_policy_configs")
    assert change_logs[-1].action == "rollback"
    assert change_logs[-1].version == "policy_v1"


async def test_file_backend_and_downstream_loaders_share_same_contract(
    file_config_service,
    config_test_settings,
):
    loader = RuleConfigLoader(file_config_service)
    bundle = await loader.load_bundle("rule_engine")
    assert bundle.version == "v1"
    assert bundle.rules[0].priority >= bundle.rules[-1].priority

    policy_loader = PolicyLoader(file_config_service)
    policies = await policy_loader.load_policies()
    assert any(policy.action == "digest" for policy in policies)

    container = build_container(config_test_settings)
    source_config = await container.source_registry.get_source_by_id("wecom_cs_notice_group")
    assert source_config is not None
    assert source_config["connector_type"] == "wecom_webhook"
    assert container.config_service.get_ai_runtime_config_sync().prompt_version == "prompt_v1"
    assert container.delivery_service._default_channel_configs["app_push"]["provider_message_id"] == "app_push_default"
    assert container.config_service is not None


async def test_publish_ai_runtime_and_delivery_channel_configs(sqlite_config_service):
    ai_version = await sqlite_config_service.publish_config(
        "ai_runtime_configs",
        {
            "config_id": "default",
            "enabled": True,
            "provider": "mock",
            "model_name": "gpt-5-nano",
            "prompt_version": "prompt_v2",
            "template_path": "D:/InformSystem/backend/app/services/ai_processing/prompts/notice_analysis_v1.txt",
            "timeout_seconds": 10.0,
            "max_retries": 1,
            "metadata": {"release_ring": "canary"},
            "version": "ai_runtime_v2",
        },
        operator="tester",
        version="ai_runtime_v2",
    )
    channel_version = await sqlite_config_service.publish_config(
        "delivery_channel_configs",
        [
            {
                "channel": "app_push",
                "enabled": True,
                "provider": "mock_app_push",
                "config": {"provider_message_id": "override_push"},
                "version": "channel_v2",
            }
        ],
        operator="tester",
        version="channel_v2",
    )

    assert ai_version == "ai_runtime_v2"
    assert channel_version == "channel_v2"
    assert (await sqlite_config_service.get_ai_runtime_config()).prompt_version == "prompt_v2"
    assert (await sqlite_config_service.get_delivery_channel_config("app_push")).config["provider_message_id"] == "override_push"

    await sqlite_config_service.rollback("ai_runtime_configs", "ai_runtime_v1", operator="tester")
    rolled_back = await sqlite_config_service.get_ai_runtime_config()
    assert rolled_back.prompt_version == "prompt_v1"
    assert rolled_back.model_name == "gpt-5-mini"


async def test_sqlite_ai_runtime_config_is_read_from_database_not_runtime_file(
    config_test_settings,
    tmp_path,
):
    isolated_ai_runtime_path = tmp_path / "config" / "isolated_ai_runtime_config.json"
    seed_store = FileConfigStore(
        ConfigFilePaths(
            source_config_path=config_test_settings.source_config_path,
            rule_config_path=config_test_settings.rule_config_path,
            notification_category_path=config_test_settings.notification_category_path,
            ai_runtime_config_path=isolated_ai_runtime_path,
            delivery_channel_config_path=config_test_settings.delivery_channel_config_path,
            push_policy_path=config_test_settings.push_policy_path,
            audit_log_path=config_test_settings.config_audit_log_path,
        )
    )
    seed_store.replace_ai_runtime_config(
        AIRuntimeConfig(
            config_id="default",
            enabled=True,
            provider="mock",
            model_name="gpt-5-mini",
            prompt_version="prompt_v1",
            template_path=str(config_test_settings.ai_prompt_template_path),
            timeout_seconds=15.0,
            max_retries=0,
            metadata={"fallback_mode": "mock"},
            version="ai_runtime_v1",
        )
    )
    sqlite_store = SQLiteConfigStore(
        config_test_settings.database_path,
        runtime_store=seed_store,
    )
    service = ConfigService(sqlite_store)
    service.ensure_seed_data(seed_store)

    seed_store.replace_ai_runtime_config(
        AIRuntimeConfig(
            config_id="default",
            enabled=False,
            provider="mock",
            model_name="file-only-model",
            prompt_version="prompt_file_only",
            template_path=str(config_test_settings.ai_prompt_template_path),
            timeout_seconds=1.0,
            max_retries=0,
            metadata={"source": "runtime_file"},
            version="file_override_v1",
        )
    )

    fresh_service = ConfigService(
        SQLiteConfigStore(
            config_test_settings.database_path,
            runtime_store=seed_store,
        )
    )
    runtime_config = await fresh_service.get_ai_runtime_config()

    assert runtime_config.prompt_version == "prompt_v1"
    assert runtime_config.model_name == "gpt-5-mini"
    assert runtime_config.enabled is True


async def test_container_merges_ai_runtime_config_with_settings_overrides(
    config_test_settings,
):
    config_test_settings.ai_provider = "kimi"
    config_test_settings.ai_model_name = "moonshot-v1-8k"
    config_test_settings.ai_gateway_endpoint = "https://api.moonshot.cn/v1"
    config_test_settings.ai_api_key = "test-key"
    config_test_settings.ai_enabled = False
    config_test_settings.ai_max_retries = 3

    container = build_container(config_test_settings)

    assert container.ai_processing_service._model_config.enabled is False
    assert container.ai_processing_service._model_config.provider == "kimi"
    assert container.ai_processing_service._model_config.model_name == "moonshot-v1-8k"
    assert container.ai_processing_service._model_config.prompt_version == "prompt_v1"
    assert container.ai_processing_service._model_config.endpoint == "https://api.moonshot.cn/v1"
    assert container.ai_processing_service._model_config.max_retries == 3


async def test_container_keeps_configured_kimi_model_when_provider_only_override(
    config_test_settings,
):
    seed_store = FileConfigStore(
        ConfigFilePaths(
            source_config_path=config_test_settings.source_config_path,
            rule_config_path=config_test_settings.rule_config_path,
            notification_category_path=config_test_settings.notification_category_path,
            ai_runtime_config_path=config_test_settings.ai_runtime_config_path,
            delivery_channel_config_path=config_test_settings.delivery_channel_config_path,
            push_policy_path=config_test_settings.push_policy_path,
            audit_log_path=config_test_settings.config_audit_log_path,
        )
    )
    sqlite_service = ConfigService(
        SQLiteConfigStore(
            config_test_settings.database_path,
            runtime_store=seed_store,
        )
    )
    sqlite_service.ensure_seed_data(seed_store)
    await sqlite_service.publish_config(
        "ai_runtime_configs",
        {
            "config_id": "default",
            "enabled": True,
            "provider": "kimi",
            "model_name": "custom-kimi-model",
            "prompt_version": "prompt_v1",
            "template_path": str(config_test_settings.ai_prompt_template_path),
            "endpoint": "https://kimi.example.com/v1",
            "api_key": "config-key",
            "timeout_seconds": 12.0,
            "max_retries": 1,
            "metadata": {"release_ring": "config"},
            "version": "ai_runtime_kimi_v1",
        },
        operator="tester",
        version="ai_runtime_kimi_v1",
    )

    config_test_settings.ai_provider = "kimi"
    container = build_container(config_test_settings)

    assert container.ai_processing_service._model_config.provider == "kimi"
    assert container.ai_processing_service._model_config.model_name == "custom-kimi-model"
    assert container.ai_processing_service._model_config.endpoint == "https://kimi.example.com/v1"
