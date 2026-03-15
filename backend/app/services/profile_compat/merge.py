from __future__ import annotations

from typing import Any

from backend.app.services.user_profile.models import NotificationPreference, UserProfile


class ProfileMergePolicy:
    def merge(
        self,
        *,
        school_code: str,
        proposed_values: dict[str, Any],
        existing_profile: UserProfile | None = None,
        preferred_user_id: str | None = None,
    ) -> UserProfile:
        student_id = proposed_values.get("student_id") or (
            existing_profile.student_id if existing_profile else None
        )
        if not student_id:
            raise ValueError("Unable to build profile without student_id")

        user_id = (
            preferred_user_id
            or proposed_values.get("user_id")
            or (existing_profile.user_id if existing_profile else None)
            or f"{school_code}_{student_id}"
        )

        return UserProfile(
            user_id=user_id,
            student_id=student_id,
            name=self._pick_scalar("name", proposed_values, existing_profile),
            college=self._pick_scalar("college", proposed_values, existing_profile),
            major=self._pick_scalar("major", proposed_values, existing_profile),
            grade=self._pick_scalar("grade", proposed_values, existing_profile),
            degree_level=self._pick_scalar("degree_level", proposed_values, existing_profile),
            identity_tags=self._pick_sequence("identity_tags", proposed_values, existing_profile),
            graduation_stage=self._pick_scalar("graduation_stage", proposed_values, existing_profile),
            enrolled_courses=self._pick_sequence("enrolled_courses", proposed_values, existing_profile),
            credit_status=self._pick_mapping("credit_status", proposed_values, existing_profile),
            current_tasks=self._pick_sequence("current_tasks", proposed_values, existing_profile),
            notification_preference=self._pick_preference(proposed_values, existing_profile),
            metadata=self._merge_metadata(school_code, proposed_values, existing_profile),
        )

    def _pick_scalar(
        self,
        key: str,
        proposed_values: dict[str, Any],
        existing_profile: UserProfile | None,
    ) -> Any:
        if key in proposed_values and proposed_values[key] is not None:
            return proposed_values[key]
        return getattr(existing_profile, key, None) if existing_profile else None

    def _pick_sequence(
        self,
        key: str,
        proposed_values: dict[str, Any],
        existing_profile: UserProfile | None,
    ) -> list[Any]:
        if key in proposed_values and proposed_values[key] is not None:
            return list(proposed_values[key])
        if existing_profile is None:
            return []
        return list(getattr(existing_profile, key))

    def _pick_mapping(
        self,
        key: str,
        proposed_values: dict[str, Any],
        existing_profile: UserProfile | None,
    ) -> dict[str, Any]:
        if key in proposed_values and proposed_values[key] is not None:
            return dict(proposed_values[key])
        if existing_profile is None:
            return {}
        return dict(getattr(existing_profile, key))

    def _pick_preference(
        self,
        proposed_values: dict[str, Any],
        existing_profile: UserProfile | None,
    ) -> NotificationPreference:
        if "notification_preference" in proposed_values and proposed_values["notification_preference"] is not None:
            return proposed_values["notification_preference"]
        if existing_profile is not None:
            return existing_profile.notification_preference
        return NotificationPreference()

    def _merge_metadata(
        self,
        school_code: str,
        proposed_values: dict[str, Any],
        existing_profile: UserProfile | None,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        if existing_profile is not None:
            metadata.update(existing_profile.metadata)
        metadata.update(proposed_values.get("metadata", {}))
        metadata["source_school"] = school_code
        return metadata
