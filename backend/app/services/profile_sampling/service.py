from __future__ import annotations

from collections import defaultdict

from backend.app.services.profile_sampling.auth.base import AuthProvider
from backend.app.services.profile_sampling.models import (
    ProfileSamplingResult,
    ProfileSyncRequest,
    RawProfileFragment,
)
from backend.app.services.profile_sampling.samplers.base import ProfileSampler


class ProfileSamplingService:
    def __init__(self) -> None:
        self._auth_providers: dict[tuple[str, str], AuthProvider] = {}
        self._samplers: dict[str, list[ProfileSampler]] = defaultdict(list)

    def register_auth_provider(
        self,
        school_code: str,
        auth_mode: str,
        provider: AuthProvider,
    ) -> None:
        self._auth_providers[(school_code, auth_mode)] = provider

    def register_sampler(self, school_code: str, sampler: ProfileSampler) -> None:
        self._samplers[school_code].append(sampler)

    async def sample(self, request: ProfileSyncRequest) -> ProfileSamplingResult:
        provider = self._auth_providers.get((request.school_code, request.auth_mode))
        if provider is None:
            raise LookupError(
                f"Unsupported profile sampling auth provider: {request.school_code}/{request.auth_mode}"
            )

        session_handle = await provider.authenticate(request)
        fragments: list[RawProfileFragment] = []
        warnings: list[str] = []
        failed_sources: list[str] = []

        for sampler in self._samplers.get(request.school_code, []):
            if not sampler.supports(session_handle, request):
                continue
            try:
                sampled = await sampler.sample(session_handle, request)
            except Exception as exc:
                failed_sources.append(sampler.source_system)
                warnings.append(f"{sampler.source_system}: {exc}")
                continue
            fragments.extend(sampled)

        return ProfileSamplingResult(
            school_code=request.school_code,
            auth_mode=request.auth_mode,
            fragments=fragments,
            warnings=warnings,
            failed_sources=failed_sources,
            metadata={
                "authenticated_url": session_handle.authenticated_url,
                "entry_url": session_handle.entry_url,
                "sampler_count": len(self._samplers.get(request.school_code, [])),
            },
        )
