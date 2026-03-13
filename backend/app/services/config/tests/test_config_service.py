from __future__ import annotations

from backend.app.container import build_container
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

    change_logs = await sqlite_config_service.list_change_logs()
    assert len(change_logs) == 4


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
    assert container.config_service is not None
