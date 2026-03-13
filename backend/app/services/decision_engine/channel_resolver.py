from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from backend.app.shared.models import UserProfile
from backend.app.services.decision_engine.policies import PushPolicyConfig


class ChannelResolver:
    async def resolve(
        self,
        decision_action: str,
        user_profile: UserProfile,
        policies: list[PushPolicyConfig],
        matched_policy: PushPolicyConfig | None = None,
        priority_level: str = "low",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if decision_action in {"archive", "ignore"}:
            return {
                "delivery_timing": "scheduled",
                "delivery_channels": [],
                "metadata": {},
            }

        channels = self._resolve_channels(decision_action, user_profile, matched_policy, policies)
        current_time = self._resolve_current_time(context)

        if decision_action == "digest":
            return {
                "delivery_timing": "digest_window",
                "delivery_channels": channels,
                "metadata": {},
            }

        if decision_action == "push_high" and self._is_in_quiet_hours(
            current_time,
            user_profile.notification_preference.quiet_hours,
        ) and priority_level != "critical":
            scheduled_for = self._next_quiet_end(
                current_time,
                user_profile.notification_preference.quiet_hours,
            )
            return {
                "delivery_timing": "scheduled",
                "delivery_channels": channels,
                "metadata": {"scheduled_for": scheduled_for.isoformat()},
            }

        return {
            "delivery_timing": "immediate",
            "delivery_channels": channels,
            "metadata": {},
        }

    def _resolve_channels(
        self,
        decision_action: str,
        user_profile: UserProfile,
        matched_policy: PushPolicyConfig | None,
        policies: list[PushPolicyConfig],
    ) -> list[str]:
        preferred_channels = user_profile.notification_preference.channels
        policy_channels = (matched_policy.channels if matched_policy else []) or self._policy_channels_for_action(
            decision_action,
            policies,
        )

        if preferred_channels and policy_channels:
            intersection = [channel for channel in preferred_channels if channel in policy_channels]
            if intersection:
                return intersection
            return policy_channels

        if policy_channels:
            return policy_channels

        if preferred_channels:
            return preferred_channels

        return ["app_push"]

    def _policy_channels_for_action(self, action: str, policies: list[PushPolicyConfig]) -> list[str]:
        for policy in policies:
            if policy.action == action and policy.channels:
                return policy.channels
        return []

    def _resolve_current_time(self, context: dict[str, Any] | None) -> datetime:
        value = (context or {}).get("current_time")
        if value:
            return datetime.fromisoformat(value)
        return datetime.now().astimezone()

    def _is_in_quiet_hours(self, moment: datetime, quiet_hours: list[str]) -> bool:
        return any(self._window_contains(moment, window) for window in quiet_hours)

    def _next_quiet_end(self, moment: datetime, quiet_hours: list[str]) -> datetime:
        candidates = []
        for window in quiet_hours:
            if not self._window_contains(moment, window):
                continue
            _, end = self._window_bounds(moment, window)
            candidates.append(end)

        if not candidates:
            return moment

        return min(candidates)

    def _window_contains(self, moment: datetime, window: str) -> bool:
        start, end = self._window_bounds(moment, window)
        return start <= moment < end

    def _window_bounds(self, moment: datetime, window: str) -> tuple[datetime, datetime]:
        start_text, end_text = window.split("-", maxsplit=1)
        start_hour, start_minute = self._parse_clock(start_text)
        end_hour, end_minute = self._parse_clock(end_text)

        start = moment.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
        end = moment.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)

        if end <= start:
            if moment < end:
                start -= timedelta(days=1)
            else:
                end += timedelta(days=1)

        return start, end

    def _parse_clock(self, value: str) -> tuple[int, int]:
        hour_text, minute_text = value.split(":", maxsplit=1)
        return int(hour_text), int(minute_text)
