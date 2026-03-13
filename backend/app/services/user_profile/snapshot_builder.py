from __future__ import annotations

from backend.app.services.user_profile.course_sync_adapter import CourseSyncAdapter
from backend.app.services.user_profile.credit_status_manager import CreditStatusManager
from backend.app.services.user_profile.graduation_status_manager import GraduationStatusManager
from backend.app.services.user_profile.models import UserProfile
from backend.app.services.user_profile.preference_manager import PreferenceManager
from backend.app.services.user_profile.repositories import SQLiteUserProfileRepository


class SnapshotBuilder:
    def __init__(
        self,
        repository: SQLiteUserProfileRepository,
        course_sync_adapter: CourseSyncAdapter,
        credit_status_manager: CreditStatusManager,
        graduation_status_manager: GraduationStatusManager,
        preference_manager: PreferenceManager,
    ) -> None:
        self._repository = repository
        self._course_sync_adapter = course_sync_adapter
        self._credit_status_manager = credit_status_manager
        self._graduation_status_manager = graduation_status_manager
        self._preference_manager = preference_manager

    async def build(self, user_id: str) -> UserProfile | None:
        base_profile = await self._repository.get_base_profile(user_id)
        if base_profile is None:
            return None

        return base_profile.model_copy(
            update={
                "enrolled_courses": await self._course_sync_adapter.sync_courses(user_id),
                "credit_status": await self._credit_status_manager.get_credit_status(user_id),
                "graduation_stage": await self._graduation_status_manager.get_graduation_stage(user_id),
                "current_tasks": await self._graduation_status_manager.get_current_tasks(user_id),
                "notification_preference": await self._preference_manager.get_preference(user_id),
            }
        )
