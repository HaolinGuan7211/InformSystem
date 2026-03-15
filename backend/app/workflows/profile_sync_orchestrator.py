from __future__ import annotations

from backend.app.services.profile_compat.models import ProfileSyncResult
from backend.app.services.profile_compat.service import ProfileCompatibilityService
from backend.app.services.profile_sampling.models import ProfileSyncRequest
from backend.app.services.profile_sampling.service import ProfileSamplingService
from backend.app.services.user_profile.repositories import SQLiteUserProfileRepository
from backend.app.services.user_profile.service import UserProfileService


class ProfileSyncOrchestrator:
    def __init__(
        self,
        *,
        sampling_service: ProfileSamplingService,
        compatibility_service: ProfileCompatibilityService,
        user_profile_repository: SQLiteUserProfileRepository,
        user_profile_service: UserProfileService,
    ) -> None:
        self._sampling_service = sampling_service
        self._compatibility_service = compatibility_service
        self._user_profile_repository = user_profile_repository
        self._user_profile_service = user_profile_service

    async def run(self, request: ProfileSyncRequest) -> ProfileSyncResult:
        sampling_result = await self._sampling_service.sample(request)
        existing_profile = await self._resolve_existing_profile(request, sampling_result)
        draft = self._compatibility_service.normalize(
            request=request,
            sampling_result=sampling_result,
            existing_profile=existing_profile,
        )

        persisted = bool(request.persist and not request.dry_run)
        profile = draft.profile
        if persisted:
            await self._user_profile_service.upsert_profile(profile)
            snapshot = await self._user_profile_service.build_snapshot(profile.user_id)
            if snapshot is not None:
                profile = snapshot

        return ProfileSyncResult(
            school_code=request.school_code,
            auth_mode=request.auth_mode,
            persisted=persisted,
            profile=profile,
            missing_fields=draft.missing_fields,
            warnings=draft.warnings,
            failed_sources=draft.failed_sources,
            field_sources=draft.field_sources,
            sampled_fragments=[
                f"{fragment.fragment_type}:{fragment.source_system}"
                for fragment in sampling_result.fragments
            ],
            metadata=draft.metadata,
        )

    async def _resolve_existing_profile(self, request: ProfileSyncRequest, sampling_result) -> object | None:
        student_id = self._extract_student_id(sampling_result)
        if student_id:
            return await self._user_profile_repository.get_by_student_id(student_id)
        if request.user_id:
            return await self._user_profile_repository.get_by_user_id(request.user_id)
        return None

    def _extract_student_id(self, sampling_result) -> str | None:
        for fragment in sampling_result.fragments:
            student_id = fragment.payload.get("student_id")
            if isinstance(student_id, str) and student_id.strip():
                return student_id.strip()
        return None
