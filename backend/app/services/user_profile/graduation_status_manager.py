from __future__ import annotations

from backend.app.services.user_profile.repositories import SQLiteUserProfileRepository


class GraduationStatusManager:
    def __init__(self, repository: SQLiteUserProfileRepository) -> None:
        self._repository = repository

    async def get_graduation_stage(self, user_id: str) -> str | None:
        profile = await self._repository.get_base_profile(user_id)
        return profile.graduation_stage if profile else None

    async def get_current_tasks(self, user_id: str) -> list[str]:
        profile = await self._repository.get_base_profile(user_id)
        return profile.current_tasks if profile else []
