from __future__ import annotations

from backend.app.services.user_profile.models import NotificationPreference
from backend.app.services.user_profile.repositories import SQLiteUserProfileRepository


class PreferenceManager:
    def __init__(self, repository: SQLiteUserProfileRepository) -> None:
        self._repository = repository

    async def get_preference(self, user_id: str) -> NotificationPreference:
        return await self._repository.get_preference(user_id)
