from __future__ import annotations

from abc import ABC, abstractmethod

from backend.app.services.profile_sampling.models import ProfileSyncRequest, RawProfileFragment, SchoolSessionHandle


class ProfileSampler(ABC):
    source_system: str

    def supports(
        self,
        session_handle: SchoolSessionHandle,
        request: ProfileSyncRequest,
    ) -> bool:
        return True

    @abstractmethod
    async def sample(
        self,
        session_handle: SchoolSessionHandle,
        request: ProfileSyncRequest,
    ) -> list[RawProfileFragment]:
        raise NotImplementedError
