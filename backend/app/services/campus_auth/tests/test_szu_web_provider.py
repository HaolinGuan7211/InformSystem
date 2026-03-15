from __future__ import annotations

from dataclasses import dataclass

import requests
import pytest

from backend.app.services.campus_auth.models import CampusAuthRequest
from backend.app.services.campus_auth.providers.szu_web_provider import SzuWebCampusAuthProvider
from backend.app.services.campus_auth.szu.cas_client import SzuLoginForm


class _FakeResponse:
    def __init__(self, url: str, text: str = "", history: list | None = None) -> None:
        self.url = url
        self.text = text
        self.history = history or []
        self.headers = {"content-type": "text/html; charset=utf-8"}
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"
        self.content = text.encode("utf-8")
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None


class _FakeCasClient:
    def resolve_credentials(self, request: CampusAuthRequest) -> tuple[str, str]:
        return ("student", "secret")

    def create_session(self, request: CampusAuthRequest) -> requests.Session:
        return requests.Session()

    def bootstrap(self, session: requests.Session, entry_url: str):
        return (
            _FakeResponse(
                "https://authserver.szu.edu.cn/authserver/login?service=...",
                "<html>login</html>",
            ),
            "<html>login</html>",
        )

    def parse_login_form(self, login_html: str, login_page_url: str) -> SzuLoginForm:
        return SzuLoginForm(
            login_page_url=login_page_url,
            action_url=login_page_url,
            execution="e1s1",
            lt="LT-1",
            salt="LbYtGQSI0WCUdT5g",
        )

    def submit_login(self, session: requests.Session, *, form: SzuLoginForm, username: str, password: str):
        return (
            _FakeResponse("https://ehall.szu.edu.cn/jwapp/sys/xywccx/*default/index.do", "<html>ok</html>"),
            "<html>ok</html>",
        )

    def extract_login_error(self, html: str) -> str | None:
        return None

    def redirect_chain(self, *responses) -> list[str]:
        return [response.url for response in responses]


@dataclass(slots=True)
class _FakeEhallClient:
    def validate_portal_session(self, handle) -> dict[str, object]:
        return {"has_login": True, "user_info": {"hasLogin": True}, "module_probe": {"status_code": 200}}


@pytest.mark.asyncio
async def test_szu_web_provider_returns_validated_ehall_session_handle() -> None:
    provider = SzuWebCampusAuthProvider(
        cas_client=_FakeCasClient(),
        ehall_client=_FakeEhallClient(),
    )

    handle = await provider.authenticate(
        CampusAuthRequest(
            school_code="szu",
            auth_mode="cli_cas",
            target_system="ehall",
            entry_url="https://ehall.szu.edu.cn/appShow?appId=4980269146247992",
            username="student",
            password="secret",
        )
    )

    assert handle.target_system == "ehall"
    assert handle.authenticated_url == "https://ehall.szu.edu.cn/jwapp/sys/xywccx/*default/index.do"
    assert handle.metadata["validation"]["has_login"] is True
