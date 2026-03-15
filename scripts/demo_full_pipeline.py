from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from backend.app.container import build_container
from backend.app.core.config import Settings
from backend.app.services.user_profile.models import UserProfile


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


async def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    run_id = uuid4().hex
    demo_root = project_root / "backend" / "data" / "demo"
    demo_root.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        project_root=project_root,
        data_dir=demo_root,
        database_path=demo_root / f"full_pipeline_demo_{run_id}.db",
    )
    container = build_container(settings)

    flow_root = (
        settings.project_root
        / "mocks"
        / "shared"
        / "golden_flows"
        / "flow_001_graduation_material_submission"
    )
    relevant_profile = UserProfile.model_validate(load_json(flow_root / "02_user_profile.json"))
    await container.user_profile_service.upsert_profile(relevant_profile)

    wecom_payload = load_json(settings.project_root / "mocks" / "ingestion" / "raw_inputs" / "wecom_message.json")
    wecom_payload["msgid"] = f"demo_wecom_{run_id}"
    event = (await container.webhook_receiver.receive("wecom_cs_notice_group", wecom_payload))[0]
    workflow = await container.workflow_orchestrator.run_event(
        event,
        context={"current_time": "2026-03-13T14:00:00+08:00"},
    )

    feedback_id = None
    sample_count = 0
    if workflow.results and workflow.results[0].delivery_logs and container.feedback_service is not None:
        first_result = workflow.results[0]
        sent_log = first_result.delivery_logs[0]
        feedback = await container.feedback_service.record_user_feedback(
            {
                "feedback_id": f"fb_demo_useful_{run_id}",
                "user_id": first_result.user_profile.user_id,
                "event_id": workflow.event.event_id,
                "decision_id": first_result.decision_result.decision_id,
                "delivery_log_id": sent_log.log_id,
                "feedback_type": "useful",
                "rating": 5,
                "comment": "demo useful feedback",
                "metadata": {"request_id": f"demo_useful_feedback_{run_id}"},
                "created_at": "2026-03-13T14:10:00+08:00",
            }
        )
        feedback_id = feedback.feedback_id
        sample_count = len(await container.feedback_service.export_optimization_samples(limit=20))

    print(f"Run id: {run_id}")
    print(f"Demo database: {settings.database_path}")
    print(f"Event id: {workflow.event.event_id}")
    print(f"Candidate users: {workflow.total_candidate_users}")
    print(f"Processed users: {workflow.processed_user_count}")
    if workflow.results:
        first_result = workflow.results[0]
        print(f"Decision action: {first_result.decision_result.decision_action}")
        print(f"Delivery statuses: {[log.status for log in first_result.delivery_logs]}")
    print(f"Feedback id: {feedback_id}")
    print(f"Optimization samples: {sample_count}")


if __name__ == "__main__":
    asyncio.run(main())
