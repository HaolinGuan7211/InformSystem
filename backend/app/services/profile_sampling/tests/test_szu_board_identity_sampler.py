from __future__ import annotations

import requests
import pytest

from backend.app.services.profile_sampling.models import ProfileSyncRequest, SchoolSessionHandle
from backend.app.services.profile_sampling.samplers.szu.board_identity_sampler import (
    SzuBoardIdentitySampler,
)

SAMPLE_BOARD_HTML = """
<html>
  <body>
    <a href="https://authserver.szu.edu.cn/personalInfo"
       title="Test Student\uff082020124040\uff09\uff5c修改密码、绑定手机和邮箱等">profile</a>
  </body>
</html>
"""


@pytest.mark.asyncio
async def test_szu_board_identity_sampler_extracts_identity_from_personal_info_banner() -> None:
    sampler = SzuBoardIdentitySampler()
    session_handle = SchoolSessionHandle(
        school_code="szu",
        auth_mode="szu_http_cas",
        session=requests.Session(),
        entry_url="https://www1.szu.edu.cn/board/",
        authenticated_url="https://www1.szu.edu.cn/board/",
        metadata={"authenticated_html": SAMPLE_BOARD_HTML},
    )

    fragments = await sampler.sample(session_handle, ProfileSyncRequest())

    assert len(fragments) == 1
    assert fragments[0].fragment_type == "identity"
    assert fragments[0].payload == {
        "name": "Test Student",
        "student_id": "2020124040",
    }
