from __future__ import annotations

import pytest

from backend.app.services.profile_sampling.models import ProfileSyncRequest, SchoolSessionHandle
from backend.app.services.profile_sampling.samplers.szu.personal_info_sampler import (
    SzuPersonalInfoSampler,
)


class _FakeResponse:
    status_code = 200

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeSession:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def get(self, url: str, timeout: int, headers: dict[str, str]):
        return _FakeResponse(self._payload)


@pytest.mark.asyncio
async def test_szu_personal_info_sampler_extracts_structured_identity() -> None:
    sampler = SzuPersonalInfoSampler()
    session_handle = SchoolSessionHandle(
        school_code="szu",
        auth_mode="szu_http_cas",
        session=_FakeSession(
            {
                "code": "0",
                "data": {
                    "cn": "Test Student",
                    "uid": "2020124040",
                    "mobile": "180****1730",
                },
            }
        ),
        entry_url="https://authserver.szu.edu.cn/personalInfo/",
        authenticated_url="https://authserver.szu.edu.cn/personalInfo/",
    )

    fragments = await sampler.sample(
        session_handle,
        ProfileSyncRequest(school_code="szu", auth_mode="szu_http_cas"),
    )

    assert len(fragments) == 1
    assert fragments[0].payload["name"] == "Test Student"
    assert fragments[0].payload["student_id"] == "2020124040"
    assert fragments[0].payload["metadata"]["masked_mobile"] == "180****1730"
