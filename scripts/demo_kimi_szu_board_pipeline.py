from __future__ import annotations

import asyncio
import os
from pathlib import Path

from backend.app.container import build_container
from backend.app.core.config import Settings
from backend.app.services.user_profile.models import NotificationPreference, UserProfile


def build_demo_profile() -> UserProfile:
    return UserProfile(
        user_id="szu_kimi_demo_student",
        student_id="KIMI20260001",
        name="Kimi Demo Student",
        college="马克思主义学院",
        major="思想政治教育",
        grade="2022",
        degree_level="undergraduate",
        identity_tags=["student"],
        graduation_stage=None,
        current_tasks=["校内报名"],
        notification_preference=NotificationPreference(
            channels=["app_push"],
            quiet_hours=["23:00-07:00"],
            digest_enabled=True,
            muted_categories=[],
        ),
        metadata={"demo": True, "ai_provider": "kimi"},
    )


async def main() -> None:
    if not os.getenv("SZU_BOARD_USERNAME") or not os.getenv("SZU_BOARD_PASSWORD"):
        raise SystemExit("SZU_BOARD_USERNAME and SZU_BOARD_PASSWORD are required")
    if not os.getenv("KIMI_API_KEY"):
        raise SystemExit("KIMI_API_KEY is required")

    project_root = Path(__file__).resolve().parents[1]
    settings = Settings(
        project_root=project_root,
        data_dir=project_root / "backend" / "data" / "demo_kimi_szu_board",
        database_path=project_root / "backend" / "data" / "demo_kimi_szu_board" / "pipeline.db",
        ai_provider="kimi",
        ai_model_name=os.getenv("KIMI_MODEL") or "moonshot-v1-8k",
        ai_gateway_endpoint=os.getenv("KIMI_BASE_URL") or "https://api.moonshot.cn/v1",
        ai_api_key=os.getenv("KIMI_API_KEY"),
    )
    container = build_container(settings)

    source_config = await container.source_registry.get_source_by_id("szu_campus_board")
    if source_config is None:
        raise SystemExit("szu_campus_board source config not found")

    source_config = {
        **source_config,
        "enabled": True,
        "parse_config": {
            **source_config.get("parse_config", {}),
            "max_items": 1,
        },
    }

    connector = container.connector_manager.get_connector(source_config["connector_type"])
    raw_items = await connector.fetch(source_config)
    events = await container.ingestion_service.ingest_many(raw_items, source_config)
    if not events:
        raise SystemExit("No events were accepted from SZU board")

    profile = build_demo_profile()
    await container.user_profile_service.upsert_profile(profile)

    workflow = await container.workflow_orchestrator.run_event(
        events[0],
        user_ids=[profile.user_id],
        context={"current_time": "2026-03-14T14:00:00+08:00"},
    )
    if not workflow.results:
        raise SystemExit("Workflow produced no user results")

    result = workflow.results[0]
    print(f"AI provider: {settings.ai_provider}")
    print(f"AI model: {settings.ai_model_name}")
    print(f"Event title: {workflow.event.title}")
    print(f"Rule relevance: {result.rule_result.relevance_status} ({result.rule_result.relevance_score})")
    print(f"AI summary: {result.ai_result.summary if result.ai_result else None}")
    print(f"AI category: {result.ai_result.normalized_category if result.ai_result else None}")
    print(f"AI confidence: {result.ai_result.confidence if result.ai_result else None}")
    print(f"Decision action: {result.decision_result.decision_action}")
    print(f"Delivery statuses: {[log.status for log in result.delivery_logs]}")


if __name__ == "__main__":
    asyncio.run(main())
