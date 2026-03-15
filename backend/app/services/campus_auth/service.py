from __future__ import annotations

from backend.app.services.campus_auth.models import CampusAuthRequest, CampusSessionHandle
from backend.app.services.campus_auth.providers.base import CampusAuthProvider


class CampusAuthService:
    def __init__(self) -> None:
        self._providers: dict[tuple[str, str], CampusAuthProvider] = {}

    def register_provider(
        self,
        *,
        school_code: str,
        auth_mode: str,
        provider: CampusAuthProvider,
    ) -> None:
        self._providers[(school_code, auth_mode)] = provider

    async def authenticate(self, request: CampusAuthRequest) -> CampusSessionHandle:
        provider = self._providers.get((request.school_code, request.auth_mode))
        if provider is None:
            raise LookupError(
                f"Unsupported campus auth provider: {request.school_code}/{request.auth_mode}"
            )
        return await provider.authenticate(request)
