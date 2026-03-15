from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.app.services.profile_sampling.models import (
    ProfileSyncRequest,
    RawProfileFragment,
    SchoolSessionHandle,
)
from backend.app.services.profile_sampling.samplers.base import ProfileSampler


class SzuPersonalInfoSampler(ProfileSampler):
    source_system = "szu_personal_info"
    endpoint_url = "https://authserver.szu.edu.cn/personalInfo/personalInfo/mobile/queryPersonalInfo"

    def supports(
        self,
        session_handle: SchoolSessionHandle,
        request: ProfileSyncRequest,
    ) -> bool:
        return request.auth_mode != "offline_fixture" and session_handle.session is not None

    async def sample(
        self,
        session_handle: SchoolSessionHandle,
        request: ProfileSyncRequest,
    ) -> list[RawProfileFragment]:
        payload = self._fetch_payload(session_handle)
        data = payload.get("data", payload)
        student_id = self._first_string(
            data.get("uid"),
            data.get("id"),
            data.get("accountSetting", {}).get("id") if isinstance(data.get("accountSetting"), dict) else None,
        )
        name = self._first_string(data.get("cn"), data.get("name"))
        fragment_payload: dict[str, Any] = {}
        if student_id:
            fragment_payload["student_id"] = student_id
        if name:
            fragment_payload["name"] = name
        if isinstance(data.get("mobile"), str) and data.get("mobile"):
            fragment_payload["metadata"] = {"masked_mobile": data["mobile"]}
        if not fragment_payload:
            return []

        return [
            RawProfileFragment(
                fragment_type="identity",
                source_system=self.source_system,
                payload=fragment_payload,
                collected_at=datetime.now(timezone.utc).isoformat(),
            )
        ]

    def _fetch_payload(self, session_handle: SchoolSessionHandle) -> dict[str, Any]:
        response = session_handle.session.get(
            self.endpoint_url,
            timeout=20,
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") not in (None, "0", 0, "1", 1):
            raise ValueError(f"Unexpected personal info response code: {payload.get('code')}")
        return payload

    def _first_string(self, *values: Any) -> str | None:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None
