from __future__ import annotations

from backend.app.services.delivery.channel_router import DeliveryChannelRouter
from backend.app.services.delivery.planner import DeliveryPlanner
from backend.app.services.delivery.renderer import MessageRenderer


async def test_planner_builds_idempotent_task_from_decision_result(flow_inputs) -> None:
    planner = DeliveryPlanner(DeliveryChannelRouter(), MessageRenderer())

    tasks = await planner.build_tasks(
        flow_inputs["decision_result"],
        flow_inputs["event"],
        flow_inputs["user_profile"],
    )

    assert len(tasks) == 1
    assert tasks[0].task_id.startswith("task_")
    assert tasks[0].action == "push_now"
    assert tasks[0].channel == "app_push"
    assert tasks[0].dedupe_key == "dec_001:app_push:immediate"
    assert tasks[0].scheduled_at is None
    assert tasks[0].metadata["priority_level"] == "critical"


async def test_planner_uses_scheduled_time_from_decision_metadata(flow_inputs) -> None:
    planner = DeliveryPlanner(DeliveryChannelRouter(), MessageRenderer())
    decision = flow_inputs["decision_result"].model_copy(
        update={
            "decision_id": "dec_sched",
            "event_id": "evt_sched",
            "decision_action": "push_high",
            "delivery_timing": "scheduled",
            "metadata": {"scheduled_for": "2026-03-14T07:00:00+08:00"},
        }
    )

    tasks = await planner.build_tasks(
        decision,
        flow_inputs["event"].model_copy(update={"event_id": "evt_sched"}),
        flow_inputs["user_profile"],
    )

    assert len(tasks) == 1
    assert tasks[0].scheduled_at == "2026-03-14T07:00:00+08:00"
    assert tasks[0].dedupe_key == "dec_sched:app_push:scheduled"
