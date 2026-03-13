from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from backend.app.shared.models import DeliveryLog, DeliveryTask
from backend.app.services.delivery.gateways.base import DeliveryChannelError
from backend.app.services.delivery.models import GatewaySendResult


class RetryManager:
    def __init__(self, max_retries: int = 2, backoff_seconds: float = 0.0) -> None:
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds

    async def execute(
        self,
        task: DeliveryTask,
        sender: Callable[[DeliveryTask], Awaitable[GatewaySendResult]],
        build_logs: Callable[[str, int, GatewaySendResult | None, Exception | None], list[DeliveryLog]],
        persist_logs: Callable[[list[DeliveryLog]], Awaitable[None]] | None = None,
    ) -> list[DeliveryLog]:
        retry_count = 0

        while True:
            try:
                response = await sender(task)
                logs = build_logs("sent", retry_count, response, None)
                if persist_logs is not None:
                    await persist_logs(logs)
                return logs
            except DeliveryChannelError as exc:
                logs = build_logs("failed", retry_count, None, exc)
                if persist_logs is not None:
                    await persist_logs(logs)
                if not exc.retryable or retry_count >= self._max_retries:
                    return logs
            except Exception as exc:  # pragma: no cover
                logs = build_logs("failed", retry_count, None, exc)
                if persist_logs is not None:
                    await persist_logs(logs)
                return logs

            retry_count += 1
            if self._backoff_seconds > 0:
                await asyncio.sleep(self._backoff_seconds)
