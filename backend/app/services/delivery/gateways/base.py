from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from backend.app.shared.models import DeliveryTask
from backend.app.services.delivery.models import GatewaySendResult


class DeliveryChannelError(Exception):
    def __init__(self, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class UnsupportedDeliveryChannelError(DeliveryChannelError):
    def __init__(self, channel: str) -> None:
        super().__init__(f"Unsupported delivery channel: {channel}", retryable=False)
        self.channel = channel


class DeliveryChannelGateway(ABC):
    channel: str

    @abstractmethod
    async def send(
        self,
        task: DeliveryTask,
        channel_config: dict[str, Any] | None = None,
    ) -> GatewaySendResult:
        raise NotImplementedError
