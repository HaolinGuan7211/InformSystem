from __future__ import annotations

import requests

from backend.app.services.campus_auth.models import CampusAuthRequest, CampusSessionHandle
from backend.app.services.campus_auth.providers.base import CampusAuthProvider


class BrowserCookieCampusAuthProvider(CampusAuthProvider):
    async def authenticate(self, request: CampusAuthRequest) -> CampusSessionHandle:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": request.hints.get(
                    "user_agent",
                    (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/134.0.0.0 Safari/537.36"
                    ),
                )
            }
        )
        for cookie in request.imported_cookies:
            if not cookie.get("name"):
                continue
            session.cookies.set(
                cookie["name"],
                str(cookie.get("value", "")),
                domain=cookie.get("domain"),
                path=cookie.get("path", "/"),
            )

        return CampusSessionHandle(
            school_code=request.school_code,
            auth_mode="browser_cookie_import",
            target_system=request.target_system,
            session=session,
            entry_url=request.entry_url,
            authenticated_url=request.entry_url,
            metadata={"imported_cookie_count": len(request.imported_cookies)},
        )
