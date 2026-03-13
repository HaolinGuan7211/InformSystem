from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from backend.app.shared.models import DeliveryTask
from backend.app.services.delivery.models import GatewaySendResult


class DeliveryChannelError(Exception):
    def __init__(self, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class DeliveryChannelGateway(ABC):
    channel: str

    @abstractmethod
    async def send(
        self,
        task: DeliveryTask,
        channel_config: dict[str, Any] | None = None,
    ) -> GatewaySendResult:
        raise NotImplementedError
