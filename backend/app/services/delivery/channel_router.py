from __future__ import annotations

from backend.app.shared.models import DecisionResult, UserProfile


class DeliveryChannelRouter:
    async def resolve(
        self,
        decision_result: DecisionResult,
        user_profile: UserProfile,
    ) -> list[str]:
        if decision_result.decision_action not in {"push_now", "push_high", "digest"}:
            return []

        candidates = (
            decision_result.delivery_channels
            or user_profile.notification_preference.channels
            or ["app_push"]
        )
        seen: set[str] = set()
        ordered: list[str] = []
        for channel in candidates:
            if channel in seen:
                continue
            seen.add(channel)
            ordered.append(channel)
        return ordered
