from __future__ import annotations

from backend.app.shared.models import DeliveryLog, DeliveryTask
from backend.app.services.delivery.gateways.base import DeliveryChannelError
from backend.app.services.delivery.models import GatewaySendResult
from backend.app.services.delivery.retry_manager import RetryManager


async def test_retry_manager_retries_until_success() -> None:
    retry_manager = RetryManager(max_retries=2)
    task = DeliveryTask(
        task_id="task_retry",
        decision_id="dec_retry",
        event_id="evt_retry",
        user_id="stu_001",
        action="push_now",
        channel="app_push",
        title="提醒",
        body="内容",
    )
    attempts = {"count": 0}
    persisted: list[DeliveryLog] = []

    async def sender(_: DeliveryTask) -> GatewaySendResult:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise DeliveryChannelError("temporary failure")
        return GatewaySendResult(provider_message_id="msg_retry")

    def build_logs(status: str, retry_count: int, response, error) -> list[DeliveryLog]:
        return [
            DeliveryLog(
                log_id=f"dlv_{status}_{retry_count}",
                task_id=task.task_id,
                decision_id=task.decision_id,
                event_id=task.event_id,
                user_id=task.user_id,
                channel=task.channel,
                status=status,
                retry_count=retry_count,
                provider_message_id=response.provider_message_id if response else None,
                error_message=str(error) if error else None,
                delivered_at="2026-03-13T10:30:00+08:00" if status == "sent" else None,
                metadata={},
            )
        ]

    async def persist(logs: list[DeliveryLog]) -> None:
        persisted.extend(logs)

    result = await retry_manager.execute(task, sender, build_logs, persist)

    assert attempts["count"] == 2
    assert [log.status for log in persisted] == ["failed", "sent"]
    assert persisted[0].retry_count == 0
    assert persisted[1].retry_count == 1
    assert result[0].status == "sent"


async def test_retry_manager_stops_after_non_retryable_failure() -> None:
    retry_manager = RetryManager(max_retries=2)
    task = DeliveryTask(
        task_id="task_fail",
        decision_id="dec_fail",
        event_id="evt_fail",
        user_id="stu_001",
        action="push_now",
        channel="app_push",
        title="提醒",
        body="内容",
    )
    persisted: list[DeliveryLog] = []

    async def sender(_: DeliveryTask) -> GatewaySendResult:
        raise DeliveryChannelError("permanent failure", retryable=False)

    def build_logs(status: str, retry_count: int, response, error) -> list[DeliveryLog]:
        return [
            DeliveryLog(
                log_id="dlv_failed",
                task_id=task.task_id,
                decision_id=task.decision_id,
                event_id=task.event_id,
                user_id=task.user_id,
                channel=task.channel,
                status=status,
                retry_count=retry_count,
                provider_message_id=None,
                error_message=str(error) if error else None,
                delivered_at=None,
                metadata={},
            )
        ]

    async def persist(logs: list[DeliveryLog]) -> None:
        persisted.extend(logs)

    result = await retry_manager.execute(task, sender, build_logs, persist)

    assert len(persisted) == 1
    assert result[0].status == "failed"
    assert result[0].retry_count == 0
