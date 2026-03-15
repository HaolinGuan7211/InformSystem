from __future__ import annotations

from abc import ABC, abstractmethod

from backend.app.services.profile_sampling.models import ProfileSyncRequest, SchoolSessionHandle


class AuthProvider(ABC):
    @abstractmethod
    async def authenticate(self, request: ProfileSyncRequest) -> SchoolSessionHandle:
        raise NotImplementedError
