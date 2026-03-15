from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.app.container import build_container
from backend.app.core.config import Settings
from backend.app.services.campus_auth.models import CampusAuthRequest

PROJECT_ROOT = Path(__file__).resolve().parents[5]


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_SZU_EHALL_REAL_TEST") != "1",
    reason="real SZU ehall test is disabled by default",
)
async def test_real_szu_ehall_login_establishes_portal_session(tmp_path: Path) -> None:
    settings = Settings(
        project_root=PROJECT_ROOT,
        data_dir=tmp_path / "data",
        database_path=tmp_path / "data" / "ehall_real_test.db",
    )
    container = build_container(settings)

    handle = await container.campus_auth_service.authenticate(
        CampusAuthRequest(
            school_code="szu",
            auth_mode="cli_cas",
            target_system="ehall",
            entry_url="https://ehall.szu.edu.cn/appShow?appId=4980269146247992",
            username_env="SZU_BOARD_USERNAME",
            password_env="SZU_BOARD_PASSWORD",
        )
    )

    validation = handle.metadata["validation"]
    assert validation["has_login"] is True
    assert validation["user_info"]["hasLogin"] is True or validation["app_status"]["hasLogin"] is True
    assert validation["module_probe"]["status_code"] == 200
