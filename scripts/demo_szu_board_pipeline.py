from __future__ import annotations

import asyncio
import os
from pathlib import Path

from backend.app.container import build_container
from backend.app.core.config import Settings
from backend.app.services.user_profile.models import NotificationPreference, UserProfile


def build_demo_profile() -> UserProfile:
    return UserProfile(
        user_id="szu_live_demo_student",
        student_id="LIVE20260001",
        name="SZU Demo Student",
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
        metadata={"demo": True},
    )


async def main() -> None:
    if not os.getenv("SZU_BOARD_USERNAME") or not os.getenv("SZU_BOARD_PASSWORD"):
        raise SystemExit("SZU_BOARD_USERNAME and SZU_BOARD_PASSWORD are required")

    project_root = Path(__file__).resolve().parents[1]
    settings = Settings(
        project_root=project_root,
        data_dir=project_root / "backend" / "data" / "demo_szu_board",
        database_path=project_root / "backend" / "data" / "demo_szu_board" / "pipeline.db",
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
        context={"current_time": "2026-03-13T14:00:00+08:00"},
    )

    feedback_id = None
    sample_count = 0
    if workflow.results and workflow.results[0].delivery_logs and container.feedback_service is not None:
        first_result = workflow.results[0]
        feedback = await container.feedback_service.record_user_feedback(
            {
                "feedback_id": "fb_szu_board_demo",
                "user_id": first_result.user_profile.user_id,
                "event_id": workflow.event.event_id,
                "decision_id": first_result.decision_result.decision_id,
                "delivery_log_id": first_result.delivery_logs[0].log_id,
                "feedback_type": "useful",
                "rating": 5,
                "comment": "live SZU board demo feedback",
                "metadata": {"request_id": "szu_board_demo_feedback"},
                "created_at": "2026-03-13T14:10:00+08:00",
            }
        )
        feedback_id = feedback.feedback_id
        sample_count = len(await container.feedback_service.export_optimization_samples(limit=20))

    print(f"Fetched raw items: {len(raw_items)}")
    print(f"Accepted events: {len(events)}")
    print(f"Event title: {events[0].title}")
    print(f"Decision action: {workflow.results[0].decision_result.decision_action if workflow.results else 'none'}")
    print(
        "Delivery statuses: "
        f"{[log.status for log in workflow.results[0].delivery_logs] if workflow.results else []}"
    )
    print(f"Feedback id: {feedback_id}")
    print(f"Optimization samples: {sample_count}")


if __name__ == "__main__":
    asyncio.run(main())
