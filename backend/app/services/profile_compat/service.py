from __future__ import annotations

from backend.app.services.profile_compat.mappers.base import ProfileMapper
from backend.app.services.profile_compat.models import NormalizedProfileDraft
from backend.app.services.profile_sampling.models import ProfileSamplingResult, ProfileSyncRequest
from backend.app.services.user_profile.models import UserProfile


class ProfileCompatibilityService:
    def __init__(self) -> None:
        self._mappers: dict[str, ProfileMapper] = {}

    def register_mapper(self, school_code: str, mapper: ProfileMapper) -> None:
        self._mappers[school_code] = mapper

    def normalize(
        self,
        *,
        request: ProfileSyncRequest,
        sampling_result: ProfileSamplingResult,
        existing_profile: UserProfile | None = None,
    ) -> NormalizedProfileDraft:
        mapper = self._mappers.get(request.school_code)
        if mapper is None:
            raise LookupError(f"Unsupported profile compatibility mapper: {request.school_code}")
        return mapper.map(
            request=request,
            sampling_result=sampling_result,
            existing_profile=existing_profile,
        )
