from __future__ import annotations

from backend.app.services.campus_auth.models import CampusAuthRequest
from backend.app.services.campus_auth.service import CampusAuthService
from backend.app.services.profile_sampling.auth.base import AuthProvider
from backend.app.services.profile_sampling.models import ProfileSyncRequest, SchoolSessionHandle


class SzuHTTPCasProvider(AuthProvider):
    def __init__(
        self,
        *,
        campus_auth_service: CampusAuthService,
        target_system: str,
        entry_url: str,
    ) -> None:
        self._campus_auth_service = campus_auth_service
        self._target_system = target_system
        self._entry_url = entry_url

    async def authenticate(self, request: ProfileSyncRequest) -> SchoolSessionHandle:
        session_handle = await self._campus_auth_service.authenticate(
            CampusAuthRequest(
                school_code=request.school_code,
                auth_mode="cli_cas",
                target_system=self._target_system,
                entry_url=self._entry_url,
                username=request.username,
                password=request.password,
                username_env=request.username_env,
                password_env=request.password_env,
                hints=request.hints,
            )
        )
        return SchoolSessionHandle(
            school_code=session_handle.school_code,
            auth_mode=request.auth_mode,
            session=session_handle.session,
            entry_url=session_handle.entry_url,
            authenticated_url=session_handle.authenticated_url,
            metadata={
                **session_handle.metadata,
                "target_system": session_handle.target_system,
            },
        )
