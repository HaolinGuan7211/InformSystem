from __future__ import annotations

from backend.app.services.user_profile.models import CourseInfo
from backend.app.services.user_profile.repositories import SQLiteUserProfileRepository


class CourseSyncAdapter:
    def __init__(self, repository: SQLiteUserProfileRepository) -> None:
        self._repository = repository

    async def sync_courses(self, user_id: str) -> list[CourseInfo]:
        return await self._repository.list_courses(user_id)
