from __future__ import annotations

from backend.app.services.user_profile.models import UserProfile
from backend.app.services.user_profile.repositories import SQLiteUserProfileRepository
from backend.app.services.user_profile.snapshot_builder import SnapshotBuilder


class UserProfileService:
    def __init__(
        self,
        repository: SQLiteUserProfileRepository,
        snapshot_builder: SnapshotBuilder,
    ) -> None:
        self._repository = repository
        self._snapshot_builder = snapshot_builder

    async def get_profile(self, user_id: str) -> UserProfile | None:
        return await self.build_snapshot(user_id)

    async def upsert_profile(self, profile: UserProfile) -> None:
        await self._repository.save(profile)

    async def build_snapshot(self, user_id: str) -> UserProfile | None:
        return await self._snapshot_builder.build(user_id)

    async def list_active_users(self, limit: int = 1000) -> list[UserProfile]:
        profiles = await self._repository.list_profile_refs(limit=limit)
        snapshots: list[UserProfile] = []
        for profile in profiles:
            snapshot = await self.build_snapshot(profile.user_id)
            if snapshot is not None:
                snapshots.append(snapshot)
        return snapshots
