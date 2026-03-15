from __future__ import annotations

from backend.app.services.campus_auth.cooldown_guard import LoginCooldownGuard
from backend.app.services.campus_auth.models import CampusAuthRequest, CampusSessionHandle
from backend.app.services.campus_auth.providers.base import CampusAuthProvider
from backend.app.services.campus_auth.szu.cas_client import SzuCasClient
from backend.app.services.campus_auth.szu.ehall_client import SzuEhallClient


class SzuWebCampusAuthProvider(CampusAuthProvider):
    def __init__(
        self,
        *,
        cas_client: SzuCasClient | None = None,
        ehall_client: SzuEhallClient | None = None,
        cooldown_guard: LoginCooldownGuard | None = None,
    ) -> None:
        self._cas_client = cas_client or SzuCasClient()
        self._ehall_client = ehall_client or SzuEhallClient()
        self._cooldown_guard = cooldown_guard

    async def authenticate(self, request: CampusAuthRequest) -> CampusSessionHandle:
        username, password = self._cas_client.resolve_credentials(request)
        if self._cooldown_guard is not None:
            self._cooldown_guard.assert_allowed(
                school_code=request.school_code,
                username=username,
            )

        success = False
        try:
            session = self._cas_client.create_session(request)
            login_page_response, login_html = self._cas_client.bootstrap(session, request.entry_url)
            form = self._cas_client.parse_login_form(login_html, login_page_response.url)
            authenticated_response, authenticated_html = self._cas_client.submit_login(
                session,
                form=form,
                username=username,
                password=password,
            )
            validation = self._validate_target(
                request=request,
                authenticated_response=authenticated_response,
                authenticated_html=authenticated_html,
                session=session,
            )
            success = True
            return CampusSessionHandle(
                school_code=request.school_code,
                auth_mode=request.auth_mode,
                target_system=request.target_system,
                session=session,
                entry_url=request.entry_url,
                authenticated_url=authenticated_response.url,
                metadata={
                    "redirect_chain": self._cas_client.redirect_chain(
                        login_page_response,
                        authenticated_response,
                    ),
                    "authenticated_html": authenticated_html,
                    "validation": validation,
                },
            )
        finally:
            if self._cooldown_guard is not None:
                self._cooldown_guard.record_attempt(
                    school_code=request.school_code,
                    username=username,
                    target_system=request.target_system,
                    success=success,
                )

    def _validate_target(
        self,
        *,
        request: CampusAuthRequest,
        authenticated_response,
        authenticated_html: str,
        session,
    ) -> dict[str, object]:
        final_url = authenticated_response.url.rstrip("/")
        login_error = self._cas_client.extract_login_error(authenticated_html)
        if login_error:
            raise PermissionError(login_error)

        if request.target_system == "board":
            if "/board" not in final_url:
                raise PermissionError("SZU board login did not reach the authenticated site")
            return {"board_authenticated": True}

        if request.target_system == "ehall":
            handle = CampusSessionHandle(
                school_code=request.school_code,
                auth_mode=request.auth_mode,
                target_system=request.target_system,
                session=session,
                entry_url=request.entry_url,
                authenticated_url=authenticated_response.url,
            )
            return self._ehall_client.validate_portal_session(handle)

        raise LookupError(f"Unsupported SZU target_system: {request.target_system}")
