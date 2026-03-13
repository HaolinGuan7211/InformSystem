from __future__ import annotations

from typing import Any

from backend.app.shared.models import DecisionResult, DeliveryTask, SourceEvent, UserProfile
from backend.app.services.delivery.channel_router import DeliveryChannelRouter
from backend.app.services.delivery.renderer import MessageRenderer
from backend.app.services.delivery.utils import build_dedupe_key, build_task_id


class DeliveryPlanner:
    def __init__(
        self,
        channel_router: DeliveryChannelRouter,
        renderer: MessageRenderer,
    ) -> None:
        self._channel_router = channel_router
        self._renderer = renderer

    async def build_tasks(
        self,
        decision_result: DecisionResult,
        event: SourceEvent,
        user_profile: UserProfile,
        context: dict[str, Any] | None = None,
    ) -> list[DeliveryTask]:
        channels = await self._channel_router.resolve(decision_result, user_profile)
        tasks: list[DeliveryTask] = []

        for channel in channels:
            rendered = await self._renderer.render(decision_result, event, channel)
            overrides = self._resolve_task_override(context, channel)
            metadata = {
                "priority_level": decision_result.priority_level,
                "reason_summary": decision_result.reason_summary,
                "delivery_timing": decision_result.delivery_timing,
            }
            metadata.update(decision_result.metadata)
            metadata.update(overrides.get("metadata", {}))

            tasks.append(
                DeliveryTask(
                    task_id=overrides.get("task_id")
                    or build_task_id(
                        decision_result.decision_id,
                        channel,
                        decision_result.delivery_timing,
                    ),
                    decision_id=decision_result.decision_id,
                    event_id=decision_result.event_id,
                    user_id=decision_result.user_id,
                    action=decision_result.decision_action,
                    channel=channel,
                    title=overrides.get("title") or rendered["title"],
                    body=overrides.get("body") or rendered["body"],
                    scheduled_at=overrides.get("scheduled_at")
                    or self._resolve_scheduled_at(decision_result),
                    dedupe_key=overrides.get("dedupe_key")
                    or build_dedupe_key(
                        decision_result.decision_id,
                        channel,
                        decision_result.delivery_timing,
                    ),
                    metadata=metadata,
                )
            )

        return tasks

    def _resolve_scheduled_at(self, decision_result: DecisionResult) -> str | None:
        if decision_result.delivery_timing != "scheduled":
            return None
        scheduled_for = decision_result.metadata.get("scheduled_for")
        return scheduled_for if isinstance(scheduled_for, str) else None

    def _resolve_task_override(
        self,
        context: dict[str, Any] | None,
        channel: str,
    ) -> dict[str, Any]:
        if not context:
            return {}
        task_overrides = context.get("task_overrides", {})
        override = task_overrides.get(channel) or task_overrides.get("*") or {}
        return override if isinstance(override, dict) else {}
