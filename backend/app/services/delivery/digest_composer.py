from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from backend.app.shared.models import DeliveryLog, DeliveryTask
from backend.app.services.delivery.gateway_manager import GatewayManager
from backend.app.services.delivery.models import DigestJob, GatewaySendResult
from backend.app.services.delivery.renderer import MessageRenderer
from backend.app.services.delivery.repositories.delivery_log_repository import DeliveryLogRepository
from backend.app.services.delivery.repositories.digest_job_repository import DigestJobRepository
from backend.app.services.delivery.retry_manager import RetryManager
from backend.app.services.delivery.utils import (
    build_digest_job_id,
    build_log_id,
    resolve_digest_window,
    resolve_now,
)


class DigestComposer:
    def __init__(
        self,
        repository: DigestJobRepository,
        gateway_manager: GatewayManager,
        retry_manager: RetryManager,
        log_repository: DeliveryLogRepository,
        renderer: MessageRenderer,
        timezone_offset: str = "+08:00",
    ) -> None:
        self._repository = repository
        self._gateway_manager = gateway_manager
        self._retry_manager = retry_manager
        self._log_repository = log_repository
        self._renderer = renderer
        self._timezone_offset = timezone_offset

    async def enqueue(
        self,
        task: DeliveryTask,
        context: dict[str, Any] | None = None,
    ) -> DigestJob:
        current_time = resolve_now((context or {}).get("current_time"), self._timezone_offset)
        window_key, scheduled_at = self._resolve_window(current_time, context)
        existing = await self._repository.get_by_user_and_window(task.user_id, window_key)
        task_ref = task.model_dump(mode="json")

        if existing is None:
            job = DigestJob(
                job_id=build_digest_job_id(task.user_id, window_key),
                user_id=task.user_id,
                window_key=window_key,
                status="pending",
                task_refs=[task_ref],
                scheduled_at=scheduled_at,
                created_at=current_time.isoformat(),
            )
        else:
            task_refs = list(existing.task_refs)
            existing_ids = {item.get("task_id") for item in task_refs}
            if task.task_id not in existing_ids:
                task_refs.append(task_ref)
            job = existing.model_copy(
                update={
                    "status": "pending",
                    "task_refs": task_refs,
                    "scheduled_at": scheduled_at,
                }
            )

        await self._repository.save(job)
        return job

    async def flush(
        self,
        user_id: str,
        window_key: str,
        context: dict[str, Any] | None = None,
    ) -> list[DeliveryLog]:
        job = await self._repository.get_by_user_and_window(user_id, window_key)
        if job is None or not job.task_refs:
            return []

        tasks = [DeliveryTask.model_validate(item) for item in job.task_refs]
        if job.status == "sent":
            logs: list[DeliveryLog] = []
            for task in tasks:
                latest = await self._log_repository.get_latest_terminal_log(task.task_id)
                if latest is not None:
                    logs.append(latest)
            return logs

        current_time = resolve_now((context or {}).get("current_time"), self._timezone_offset)
        grouped: dict[str, list[DeliveryTask]] = defaultdict(list)
        for task in tasks:
            grouped[task.channel].append(task)

        final_logs: list[DeliveryLog] = []
        for channel, channel_tasks in grouped.items():
            rendered = await self._renderer.render_digest(channel_tasks, window_key, channel)
            aggregate_task = DeliveryTask(
                task_id=f"digest_{job.job_id}_{channel}",
                decision_id=channel_tasks[0].decision_id,
                event_id=channel_tasks[0].event_id,
                user_id=user_id,
                action="digest",
                channel=channel,
                title=rendered["title"],
                body=rendered["body"],
                scheduled_at=job.scheduled_at,
                dedupe_key=f"{job.job_id}:{channel}",
                metadata=self._resolve_channel_config(channel, context),
            )
            gateway = self._gateway_manager.get_gateway(channel)

            async def _persist(logs: list[DeliveryLog]) -> None:
                await self._log_repository.save_many(logs, created_at=current_time.isoformat())

            def _build_logs(
                status: str,
                retry_count: int,
                response: GatewaySendResult | None,
                error: Exception | None,
            ) -> list[DeliveryLog]:
                logs: list[DeliveryLog] = []
                for task in channel_tasks:
                    logs.append(
                        DeliveryLog(
                            log_id=build_log_id(),
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
                            metadata={
                                **task.metadata,
                                "digest_job_id": job.job_id,
                                "window_key": window_key,
                                "digest_task_count": len(channel_tasks),
                                "delivery_mode": "digest_flush",
                            },
                        )
                    )
                return logs

            channel_logs = await self._retry_manager.execute(
                task=aggregate_task,
                sender=lambda payload, _gateway=gateway: _gateway.send(
                    payload,
                    self._resolve_channel_config(channel, context),
                ),
                build_logs=_build_logs,
                persist_logs=_persist,
            )
            final_logs.extend(channel_logs)

        job_status = "sent" if all(log.status == "sent" for log in final_logs) else "failed"
        await self._repository.save(
            job.model_copy(
                update={
                    "status": job_status,
                    "sent_at": current_time.isoformat() if job_status == "sent" else None,
                }
            )
        )
        return final_logs

    def _resolve_window(
        self,
        current_time: datetime,
        context: dict[str, Any] | None,
    ) -> tuple[str, str]:
        override_key = (context or {}).get("digest_window_key")
        override_scheduled_at = (context or {}).get("digest_scheduled_at")
        if override_key and override_scheduled_at:
            return str(override_key), str(override_scheduled_at)
        return resolve_digest_window(current_time)

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
