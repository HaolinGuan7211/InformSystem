from __future__ import annotations

from backend.app.shared.models import DeliveryLog


async def test_delivery_service_matches_golden_flow(
    delivery_service,
    delivery_log_repository,
    flow_inputs,
    load_golden,
) -> None:
    logs = await delivery_service.dispatch(
        flow_inputs["decision_result"],
        flow_inputs["event"],
        flow_inputs["user_profile"],
        context={
            "current_time": "2026-03-13T10:24:00+08:00",
            "task_overrides": {
                "app_push": {
                    "task_id": "task_001",
                    "metadata": {"provider_message_id": "msg_abc_001"},
                }
            },
            "log_overrides": {"app_push": {"sent": "dlv_001"}},
        },
    )
    expected = DeliveryLog.model_validate(load_golden("06_delivery_log.json"))
    stored = await delivery_log_repository.get_latest_by_task("task_001")

    assert len(logs) == 1
    assert logs[0].model_dump() == expected.model_dump()
    assert stored is not None
    assert stored.model_dump() == expected.model_dump()


async def test_delivery_service_retries_and_preserves_failed_attempts(
    delivery_service,
    delivery_log_repository,
    flow_inputs,
) -> None:
    decision = flow_inputs["decision_result"].model_copy(
        update={"decision_id": "dec_retry", "event_id": "evt_retry"}
    )
    event = flow_inputs["event"].model_copy(update={"event_id": "evt_retry"})

    logs = await delivery_service.dispatch(
        decision,
        event,
        flow_inputs["user_profile"],
        context={
            "current_time": "2026-03-13T10:30:00+08:00",
            "task_overrides": {
                "app_push": {"metadata": {"mock_failures_before_success": 1}}
            },
        },
    )

    assert len(logs) == 1
    assert logs[0].status == "sent"
    assert logs[0].retry_count == 1

    attempts = await delivery_log_repository.list_by_task(logs[0].task_id)
    assert [log.status for log in attempts] == ["failed", "sent"]
    assert attempts[0].retry_count == 0
    assert attempts[1].retry_count == 1


async def test_delivery_service_enqueues_digest_and_flushes(
    delivery_service,
    delivery_log_repository,
    digest_job_repository,
    flow_inputs,
) -> None:
    decision_a = flow_inputs["decision_result"].model_copy(
        update={
            "decision_id": "dec_digest_a",
            "event_id": "evt_digest_a",
            "decision_action": "digest",
            "delivery_timing": "digest_window",
            "priority_level": "medium",
            "priority_score": 65.0,
        }
    )
    decision_b = flow_inputs["decision_result"].model_copy(
        update={
            "decision_id": "dec_digest_b",
            "event_id": "evt_digest_b",
            "decision_action": "digest",
            "delivery_timing": "digest_window",
            "priority_level": "medium",
            "priority_score": 60.0,
        }
    )
    event_a = flow_inputs["event"].model_copy(update={"event_id": "evt_digest_a"})
    event_b = flow_inputs["event"].model_copy(
        update={
            "event_id": "evt_digest_b",
            "content_text": "请毕业生补充上传离校确认材料",
        }
    )

    queued_a = await delivery_service.dispatch(
        decision_a,
        event_a,
        flow_inputs["user_profile"],
        context={"current_time": "2026-03-13T14:00:00+08:00"},
    )
    queued_b = await delivery_service.dispatch(
        decision_b,
        event_b,
        flow_inputs["user_profile"],
        context={"current_time": "2026-03-13T14:05:00+08:00"},
    )
    job = await digest_job_repository.get_by_user_and_window("stu_001", "2026-03-13")

    assert queued_a[0].status == "pending"
    assert queued_b[0].status == "pending"
    assert job is not None
    assert len(job.task_refs) == 2

    flushed = await delivery_service.flush_digest(
        "stu_001",
        "2026-03-13",
        context={"current_time": "2026-03-13T20:00:00+08:00"},
    )

    assert len(flushed) == 2
    assert all(log.status == "sent" for log in flushed)
    assert len({log.provider_message_id for log in flushed}) == 1

    latest_a = await delivery_log_repository.get_latest_by_task(queued_a[0].task_id)
    latest_b = await delivery_log_repository.get_latest_by_task(queued_b[0].task_id)
    assert latest_a is not None and latest_a.status == "sent"
    assert latest_b is not None and latest_b.status == "sent"


async def test_delivery_service_sends_after_scheduled_time(
    delivery_service,
    delivery_log_repository,
    flow_inputs,
) -> None:
    decision = flow_inputs["decision_result"].model_copy(
        update={
            "decision_id": "dec_sched",
            "event_id": "evt_sched",
            "decision_action": "push_high",
            "delivery_timing": "scheduled",
            "priority_level": "high",
            "priority_score": 82.0,
            "metadata": {"scheduled_for": "2026-03-14T07:00:00+08:00"},
        }
    )
    event = flow_inputs["event"].model_copy(update={"event_id": "evt_sched"})

    pending = await delivery_service.dispatch(
        decision,
        event,
        flow_inputs["user_profile"],
        context={"current_time": "2026-03-13T23:30:00+08:00"},
    )
    sent = await delivery_service.dispatch(
        decision,
        event,
        flow_inputs["user_profile"],
        context={"current_time": "2026-03-14T07:05:00+08:00"},
    )

    assert pending[0].status == "pending"
    assert sent[0].status == "sent"

    history = await delivery_log_repository.list_by_task(sent[0].task_id)
    assert [log.status for log in history] == ["pending", "sent"]


async def test_delivery_service_logs_failure_when_channels_are_missing(
    delivery_service,
    delivery_log_repository,
    flow_inputs,
) -> None:
    decision = flow_inputs["decision_result"].model_copy(
        update={
            "decision_id": "dec_missing_channel",
            "event_id": "evt_missing_channel",
            "delivery_channels": [],
        }
    )
    event = flow_inputs["event"].model_copy(update={"event_id": "evt_missing_channel"})

    logs = await delivery_service.dispatch(
        decision,
        event,
        flow_inputs["user_profile"],
        context={"current_time": "2026-03-13T16:00:00+08:00"},
    )

    assert len(logs) == 1
    assert logs[0].status == "failed"
    assert logs[0].channel == "unresolved_channel"
    assert logs[0].metadata["failure_reason"] == "missing_delivery_channels"

    stored = await delivery_log_repository.get_latest_by_task(logs[0].task_id)
    assert stored is not None
    assert stored.model_dump() == logs[0].model_dump()


async def test_delivery_service_logs_failure_for_unsupported_channel_without_crashing(
    delivery_service,
    delivery_log_repository,
    flow_inputs,
) -> None:
    decision = flow_inputs["decision_result"].model_copy(
        update={
            "decision_id": "dec_bad_channel",
            "event_id": "evt_bad_channel",
            "delivery_channels": ["sms"],
        }
    )
    event = flow_inputs["event"].model_copy(update={"event_id": "evt_bad_channel"})

    logs = await delivery_service.dispatch(
        decision,
        event,
        flow_inputs["user_profile"],
        context={"current_time": "2026-03-13T16:05:00+08:00"},
    )

    assert len(logs) == 1
    assert logs[0].status == "failed"
    assert logs[0].channel == "sms"
    assert logs[0].error_message == "Unsupported delivery channel: sms"
    assert logs[0].metadata["failure_reason"] == "UnsupportedDeliveryChannelError"

    stored = await delivery_log_repository.get_latest_by_task(logs[0].task_id)
    assert stored is not None
    assert stored.model_dump() == logs[0].model_dump()
