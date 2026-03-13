from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.app.shared.models import DecisionResult, DeliveryLog, DeliveryTask, SourceEvent, UserProfile
from backend.app.services.delivery.digest_composer import DigestComposer
from backend.app.services.delivery.gateway_manager import GatewayManager
from backend.app.services.delivery.models import GatewaySendResult
from backend.app.services.delivery.planner import DeliveryPlanner
from backend.app.services.delivery.repositories.delivery_log_repository import DeliveryLogRepository
from backend.app.services.delivery.retry_manager import RetryManager
from backend.app.services.delivery.utils import build_log_id, resolve_now


class DeliveryService:
    def __init__(
        self,
        planner: DeliveryPlanner,
        gateway_manager: GatewayManager,
        retry_manager: RetryManager,
        digest_composer: DigestComposer,
        log_repository: DeliveryLogRepository,
        timezone_offset: str = "+08:00",
    ) -> None:
        self._planner = planner
        self._gateway_manager = gateway_manager
        self._retry_manager = retry_manager
        self._digest_composer = digest_composer
        self._log_repository = log_repository
        self._timezone_offset = timezone_offset

    async def dispatch(
        self,
        decision_result: DecisionResult,
        event: SourceEvent,
        user_profile: UserProfile,
        context: dict[str, Any] | None = None,
    ) -> list[DeliveryLog]:
        tasks = await self._planner.build_tasks(
            decision_result=decision_result,
            event=event,
            user_profile=user_profile,
            context=context,
        )
        if not tasks:
            return []

        logs: list[DeliveryLog] = []
        current_time = resolve_now((context or {}).get("current_time"), self._timezone_offset)

        for task in tasks:
            terminal = await self._log_repository.get_latest_terminal_log(task.task_id)
            if terminal is not None:
                logs.append(terminal)
                continue

            if task.action == "digest":
                job = await self._digest_composer.enqueue(task, context=context)
                pending = await self._ensure_pending_log(
                    task=task,
                    current_time=current_time,
                    context=context,
                    metadata={
                        "digest_job_id": job.job_id,
                        "window_key": job.window_key,
                        "scheduled_at": job.scheduled_at,
                    },
                )
                logs.append(pending)
                continue

            if self._is_scheduled_for_later(task, current_time):
                pending = await self._ensure_pending_log(
                    task=task,
                    current_time=current_time,
                    context=context,
                    metadata={"scheduled_at": task.scheduled_at},
                )
                logs.append(pending)
                continue

            logs.extend(await self._dispatch_task(task, current_time, context=context))

        return logs

    async def dispatch_batch(
        self,
        items: list[tuple[DecisionResult, SourceEvent, UserProfile]],
        context: dict[str, Any] | None = None,
    ) -> list[DeliveryLog]:
        logs: list[DeliveryLog] = []
        for decision_result, event, user_profile in items:
            logs.extend(
                await self.dispatch(
                    decision_result=decision_result,
                    event=event,
                    user_profile=user_profile,
                    context=context,
                )
            )
        return logs

    async def flush_digest(
        self,
        user_id: str,
        window_key: str,
        context: dict[str, Any] | None = None,
    ) -> list[DeliveryLog]:
        return await self._digest_composer.flush(user_id=user_id, window_key=window_key, context=context)

    async def _dispatch_task(
        self,
        task: DeliveryTask,
        current_time: datetime,
        context: dict[str, Any] | None = None,
    ) -> list[DeliveryLog]:
        gateway = self._gateway_manager.get_gateway(task.channel)
        channel_config = self._resolve_channel_config(task.channel, context)

        async def _persist(logs: list[DeliveryLog]) -> None:
            await self._log_repository.save_many(logs, created_at=current_time.isoformat())

        def _build_logs(
            status: str,
            retry_count: int,
            response: GatewaySendResult | None,
            error: Exception | None,
        ) -> list[DeliveryLog]:
            return [
                DeliveryLog(
                    log_id=self._resolve_log_id(task.channel, status, context),
                    task_id=task.task_id,
                    decision_id=task.decision_id,
                    event_id=task.event_id,
                    user_id=task.user_id,
                    channel=task.channel,
                    status=status,
                    retry_count=retry_count,
                    provider_message_id=response.provider_message_id if response else None,
                    error_message=str(error) if error else None,
                    delivered_at=current_time.isoformat() if status == "sent" else None,
                    metadata={},
                )
            ]

        return await self._retry_manager.execute(
            task=task,
            sender=lambda payload: gateway.send(payload, channel_config),
            build_logs=_build_logs,
            persist_logs=_persist,
        )

    async def _ensure_pending_log(
        self,
        task: DeliveryTask,
        current_time: datetime,
        context: dict[str, Any] | None,
        metadata: dict[str, Any],
    ) -> DeliveryLog:
        existing = await self._log_repository.get_latest_by_task(task.task_id)
        if existing is not None and existing.status == "pending":
            return existing

        log = DeliveryLog(
            log_id=self._resolve_log_id(task.channel, "pending", context),
            task_id=task.task_id,
            decision_id=task.decision_id,
            event_id=task.event_id,
            user_id=task.user_id,
            channel=task.channel,
            status="pending",
            retry_count=0,
            provider_message_id=None,
            error_message=None,
            delivered_at=None,
            metadata=metadata,
        )
        await self._log_repository.save(log, created_at=current_time.isoformat())
        return log

    def _is_scheduled_for_later(self, task: DeliveryTask, current_time: datetime) -> bool:
        if not task.scheduled_at:
            return False
        return datetime.fromisoformat(task.scheduled_at) > current_time

    def _resolve_channel_config(
        self,
        channel: str,
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not context:
            return {}
        channel_configs = context.get("channel_configs", {})
        config = channel_configs.get(channel) or channel_configs.get("*") or {}
        return config if isinstance(config, dict) else {}

    def _resolve_log_id(
        self,
        channel: str,
        status: str,
        context: dict[str, Any] | None,
    ) -> str:
        if context:
            log_overrides = context.get("log_overrides", {})
            override_config = log_overrides.get(channel) or log_overrides.get("*") or {}
            if isinstance(override_config, dict):
                override = override_config.get(status)
                if isinstance(override, str):
                    return override
        return build_log_id()
