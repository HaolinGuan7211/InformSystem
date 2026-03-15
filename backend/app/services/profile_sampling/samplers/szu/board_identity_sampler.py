from __future__ import annotations

import re
from datetime import datetime, timezone

from backend.app.services.profile_sampling.models import (
    ProfileSyncRequest,
    RawProfileFragment,
    SchoolSessionHandle,
)
from backend.app.services.profile_sampling.samplers.base import ProfileSampler

PERSONAL_INFO_LINK_RE = re.compile(
    r'<a[^>]+href="https?://authserver\.szu\.edu\.cn/personalInfo"[^>]+title="(?P<title>[^"]+)"',
    re.IGNORECASE,
)
USER_BANNER_RE = re.compile(
    r'(?P<name>[^<>\uFF08\uFF09\(\)\|\uFF5C]+?)\s*[\(\uFF08]\s*(?P<student_id>\d{6,20})\s*[\)\uFF09]',
    re.IGNORECASE,
)


class SzuBoardIdentitySampler(ProfileSampler):
    source_system = "szu_board_identity"

    def supports(
        self,
        session_handle: SchoolSessionHandle,
        request: ProfileSyncRequest,
    ) -> bool:
        if request.auth_mode == "offline_fixture":
            return False
        target_system = session_handle.metadata.get("target_system")
        return target_system in (None, "board")

    async def sample(
        self,
        session_handle: SchoolSessionHandle,
        request: ProfileSyncRequest,
    ) -> list[RawProfileFragment]:
        html = self._resolve_html(session_handle)
        match = self._extract_identity(html)
        if match is None:
            raise ValueError("Unable to extract student identity from SZU board session")

        return [
            RawProfileFragment(
                fragment_type="identity",
                source_system=self.source_system,
                payload={
                    "name": match.group("name").strip(),
                    "student_id": match.group("student_id").strip(),
                },
                collected_at=datetime.now(timezone.utc).isoformat(),
                metadata={
                    "entry_url": session_handle.entry_url,
                    "authenticated_url": session_handle.authenticated_url,
                },
            )
        ]

    def _resolve_html(self, session_handle: SchoolSessionHandle) -> str:
        authenticated_html = session_handle.metadata.get("authenticated_html")
        if isinstance(authenticated_html, str) and authenticated_html.strip():
            return authenticated_html

        response = session_handle.session.get(
            session_handle.authenticated_url or session_handle.entry_url,
            timeout=20,
        )
        response.raise_for_status()
        for encoding in ["utf-8", "gb18030", "gbk", response.apparent_encoding or ""]:
            if not encoding:
                continue
            try:
                return response.content.decode(encoding)
            except (LookupError, UnicodeDecodeError):
                continue
        return response.content.decode("utf-8", errors="replace")

    def _extract_identity(self, html: str) -> re.Match[str] | None:
        personal_info_match = PERSONAL_INFO_LINK_RE.search(html)
        if personal_info_match is not None:
            title_match = USER_BANNER_RE.search(personal_info_match.group("title"))
            if title_match is not None:
                return title_match
        return USER_BANNER_RE.search(html)
