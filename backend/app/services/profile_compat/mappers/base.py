from __future__ import annotations

from abc import ABC, abstractmethod

from backend.app.services.profile_compat.models import NormalizedProfileDraft
from backend.app.services.profile_sampling.models import ProfileSamplingResult, ProfileSyncRequest
from backend.app.services.user_profile.models import UserProfile


class ProfileMapper(ABC):
    @abstractmethod
    def map(
        self,
        *,
        request: ProfileSyncRequest,
        sampling_result: ProfileSamplingResult,
        existing_profile: UserProfile | None = None,
    ) -> NormalizedProfileDraft:
        raise NotImplementedError
