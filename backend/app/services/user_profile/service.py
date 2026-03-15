from __future__ import annotations

from backend.app.services.user_profile.light_profile_tag_builder import (
    LightProfileTagBuilder,
    LightProfileTags,
)
from backend.app.services.user_profile.models import ProfileContext, UserProfile
from backend.app.services.user_profile.profile_context_selector import ProfileContextSelector
from backend.app.services.user_profile.repositories import SQLiteUserProfileRepository
from backend.app.services.user_profile.snapshot_builder import SnapshotBuilder


class UserProfileService:
    def __init__(
        self,
        repository: SQLiteUserProfileRepository,
        snapshot_builder: SnapshotBuilder,
        profile_context_selector: ProfileContextSelector | None = None,
        light_profile_tag_builder: LightProfileTagBuilder | None = None,
    ) -> None:
        self._repository = repository
        self._snapshot_builder = snapshot_builder
        self._profile_context_selector = profile_context_selector or ProfileContextSelector()
        self._light_profile_tag_builder = light_profile_tag_builder or LightProfileTagBuilder()

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

    async def build_profile_context(
        self,
        profile: UserProfile,
        required_facets: list[str],
        context: dict | None = None,
    ) -> ProfileContext:
        return await self._profile_context_selector.select(
            profile=profile,
            required_facets=required_facets,
            context=context,
        )

    async def build_light_profile_tags(
        self,
        profile: UserProfile,
        context: dict | None = None,
    ) -> LightProfileTags:
        return await self._light_profile_tag_builder.build(
            profile=profile,
            context=context,
        )
