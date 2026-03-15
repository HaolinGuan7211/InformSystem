from __future__ import annotations

from backend.app.services.profile_sampling.auth.base import AuthProvider
from backend.app.services.profile_sampling.models import ProfileSyncRequest, SchoolSessionHandle


class OfflineFixtureAuthProvider(AuthProvider):
    async def authenticate(self, request: ProfileSyncRequest) -> SchoolSessionHandle:
        return SchoolSessionHandle(
            school_code=request.school_code,
            auth_mode="offline_fixture",
            session=None,
            entry_url="offline://fixture",
            authenticated_url="offline://fixture",
            metadata={"fixture_keys": sorted(request.hints.keys())},
        )
