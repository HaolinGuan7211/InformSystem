from __future__ import annotations

from backend.app.shared.models import DeliveryTask
from backend.app.services.delivery.gateways.base import DeliveryChannelError, DeliveryChannelGateway
from backend.app.services.delivery.models import GatewaySendResult
from backend.app.services.delivery.utils import build_provider_message_id


class MockAppPushGateway(DeliveryChannelGateway):
    channel = "app_push"

    def __init__(self) -> None:
        self._attempts: dict[str, int] = {}

    async def send(
        self,
        task: DeliveryTask,
        channel_config: dict[str, object] | None = None,
    ) -> GatewaySendResult:
        config = channel_config or {}
        attempt = self._attempts.get(task.task_id, 0) + 1
        self._attempts[task.task_id] = attempt

        if config.get("always_fail") or task.metadata.get("mock_always_fail"):
            raise DeliveryChannelError("Mock app_push permanent failure", retryable=False)

        failures_before_success = int(
            config.get(
                "failures_before_success",
                task.metadata.get("mock_failures_before_success", 0),
            )
        )
        if attempt <= failures_before_success:
            raise DeliveryChannelError(f"Mock app_push temporary failure on attempt {attempt}")

        provider_message_id = build_provider_message_id(
            self.channel,
            task.task_id,
            override=config.get("provider_message_id") or task.metadata.get("provider_message_id"),
        )
        return GatewaySendResult(
            provider_message_id=provider_message_id,
            metadata={"channel": self.channel, "attempt": attempt},
        )
