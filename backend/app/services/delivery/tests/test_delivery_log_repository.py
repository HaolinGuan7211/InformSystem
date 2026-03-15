from __future__ import annotations

from backend.app.shared.models import DeliveryLog


def _build_log(
    *,
    log_id: str,
    task_id: str,
    status: str,
    event_id: str = "evt_repo",
    user_id: str = "stu_001",
    retry_count: int = 0,
    provider_message_id: str | None = None,
    error_message: str | None = None,
    delivered_at: str | None = None,
) -> DeliveryLog:
    return DeliveryLog(
        log_id=log_id,
        task_id=task_id,
        decision_id=f"dec_{task_id}",
        event_id=event_id,
        user_id=user_id,
        channel="app_push",
        status=status,
        retry_count=retry_count,
        provider_message_id=provider_message_id,
        error_message=error_message,
        delivered_at=delivered_at,
        metadata={},
    )


async def test_delivery_log_repository_supports_get_by_log_id(delivery_log_repository) -> None:
    expected = _build_log(
        log_id="dlv_lookup",
        task_id="task_lookup",
        status="sent",
        provider_message_id="msg_lookup",
        delivered_at="2026-03-13T10:24:00+08:00",
    )

    await delivery_log_repository.save(
        expected,
        created_at="2026-03-13T10:24:00+08:00",
    )

    stored = await delivery_log_repository.get_by_log_id("dlv_lookup")

    assert stored is not None
    assert stored.model_dump() == expected.model_dump()


async def test_delivery_log_repository_exposes_latest_views_without_second_store(
    delivery_log_repository,
) -> None:
    pending = _build_log(
        log_id="dlv_pending",
        task_id="task_repo",
        status="pending",
    )
    failed = _build_log(
        log_id="dlv_failed",
        task_id="task_repo",
        status="failed",
        retry_count=1,
        error_message="temporary failure",
    )
    sent = _build_log(
        log_id="dlv_sent",
        task_id="task_repo",
        status="sent",
        retry_count=1,
        provider_message_id="msg_repo",
        delivered_at="2026-03-13T10:05:00+08:00",
    )
    later_fact = _build_log(
        log_id="dlv_other_task",
        task_id="task_other",
        status="failed",
        error_message="manual backfill failure",
    )

    await delivery_log_repository.save_many(
        [pending, failed],
        created_at="2026-03-13T10:00:00+08:00",
    )
    await delivery_log_repository.save(
        sent,
        created_at="2026-03-13T10:05:00+08:00",
    )
    await delivery_log_repository.save(
        later_fact,
        created_at="2026-03-13T10:10:00+08:00",
    )

    history = await delivery_log_repository.list_by_task("task_repo")
    latest_by_task = await delivery_log_repository.get_latest_by_task("task_repo")
    latest_by_event_and_user = await delivery_log_repository.get_latest_by_event_and_user(
        "evt_repo",
        "stu_001",
    )

    assert [log.log_id for log in history] == ["dlv_pending", "dlv_failed", "dlv_sent"]
    assert latest_by_task is not None
    assert latest_by_task.log_id == "dlv_sent"
    assert latest_by_event_and_user is not None
    assert latest_by_event_and_user.log_id == "dlv_other_task"
