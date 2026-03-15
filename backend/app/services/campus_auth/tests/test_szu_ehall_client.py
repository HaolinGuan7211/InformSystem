from __future__ import annotations

from backend.app.services.campus_auth.szu.ehall_client import SzuEhallClient


class _FakeResponse:
    def __init__(
        self,
        *,
        text: str,
        url: str,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.text = text
        self.url = url
        self.status_code = status_code
        self.headers = headers or {"content-type": "application/json"}

    def raise_for_status(self) -> None:
        return None


class _FakeSession:
    def __init__(self) -> None:
        self._responses: list[_FakeResponse] = []

    def queue(self, response: _FakeResponse) -> None:
        self._responses.append(response)

    def get(self, url: str, timeout: int, headers: dict[str, str]):
        return self._responses.pop(0)

    def post(self, url: str, data: dict, timeout: int, headers: dict[str, str], allow_redirects: bool):
        return self._responses.pop(0)


def test_szu_ehall_client_extracts_app_id_and_parses_jsonp() -> None:
    client = SzuEhallClient()

    assert client.extract_app_id("https://ehall.szu.edu.cn/appShow?appId=4980269146247992") == "4980269146247992"
    assert client._parse_json_like_payload('callback({"hasLogin":true,"name":"tester"});') == {
        "hasLogin": True,
        "name": "tester",
    }


def test_szu_ehall_client_validates_active_portal_session() -> None:
    from backend.app.services.campus_auth.models import CampusSessionHandle

    session = _FakeSession()
    session.queue(
        _FakeResponse(
            text='{"hasLogin": true, "userName": "tester"}',
            url="https://ehall.szu.edu.cn/jsonp/userInfo.json",
        )
    )
    session.queue(
        _FakeResponse(
            text='callback({"hasLogin": true});',
            url="https://ehall.szu.edu.cn/jsonp/sendRecUseApp.json?appId=4980269146247992",
        )
    )
    session.queue(
        _FakeResponse(
            text='{"code":"0","datas":[]}',
            url="https://ehall.szu.edu.cn/jwapp/sys/xywccx/modules/xsxywcck/xywcfacx.do",
        )
    )
    handle = CampusSessionHandle(
        school_code="szu",
        auth_mode="cli_cas",
        target_system="ehall",
        session=session,
        entry_url="https://ehall.szu.edu.cn/appShow?appId=4980269146247992",
        authenticated_url="https://ehall.szu.edu.cn/jwapp/sys/xywccx/*default/index.do",
    )

    result = SzuEhallClient().validate_portal_session(handle)

    assert result["has_login"] is True
    assert result["user_info"]["hasLogin"] is True
    assert result["app_status"]["hasLogin"] is True
    assert result["module_probe"]["status_code"] == 200


def test_szu_ehall_client_collects_academic_completion_bundle() -> None:
    from backend.app.services.campus_auth.models import CampusSessionHandle

    session = _FakeSession()
    handle = CampusSessionHandle(
        school_code="szu",
        auth_mode="cli_cas",
        target_system="ehall",
        session=session,
        entry_url="https://ehall.szu.edu.cn/appShow?appId=4980269146247992",
        authenticated_url="https://ehall.szu.edu.cn/jwapp/sys/xywccx/*default/index.do",
    )
    session.queue(
        _FakeResponse(
            text='{"datas":{"xywcfacx":{"rows":[{"XM":"Test Student","XH":"2020124040","PYFADM":"plan_001","PYFAMC":"Test Plan","SZYXDM_DISPLAY":"Computer Science","ZYDM_DISPLAY":"Software Engineering","NJDM_DISPLAY":"2020级","YQXF":133.0,"WCXF":118.5,"BJMC":"2020 Test Class"}]}},"code":"0"}',
            url=SzuEhallClient.XYWCFACX_URL,
        )
    )
    session.queue(
        _FakeResponse(
            text='{"datas":{"cxxsjbxx":{"rows":[{"XH":"2020124040","XM":"Test Student"}]}},"code":"0"}',
            url=SzuEhallClient.CXXSJBXX_URL,
        )
    )
    session.queue(
        _FakeResponse(
            text='{"datas":{"cxscfa":{"rows":[{"PYFADM":"plan_001","PYFAMC":"Test Plan"}]}},"code":"0"}',
            url=SzuEhallClient.CXSCFA_URL,
        )
    )
    session.queue(
        _FakeResponse(
            text='{"datas":{"cxscfakz":{"rows":[{"KZH":"root_1","FKZH":"-1","KZM":"专业模块"},{"KZH":"child_1","FKZH":"root_1","KZM":"专业核心课","PYFADM":"plan_001","YQXF":"10.0","WCXF":"7.0","YQMS":3,"WCMS":2}]}},"code":"0"}',
            url=SzuEhallClient.CXSCFAKZ_URL,
        )
    )
    session.queue(
        _FakeResponse(
            text='{"datas":{"cxscfakzkc":{"totalSize":2,"rows":[{"KCM":"Operating Systems","KCH":"CS301","XF":3.0,"CJ":"A","SFTG_DISPLAY":"通过"}]}},"code":"0"}',
            url=SzuEhallClient.CXSCFAKZKC_URL,
        )
    )

    result = SzuEhallClient().collect_academic_completion(handle)

    assert result["context"]["student_id"] == "2020124040"
    assert result["context"]["plan_id"] == "plan_001"
    assert result["student_info"]["XM"] == "Test Student"
    assert result["root_nodes"][0]["KZM"] == "专业模块"
    assert result["child_nodes"][0]["KZM"] == "专业核心课"
    assert result["course_groups"][0]["child_module"] == "专业核心课"
    assert result["course_groups"][0]["course_total"] == 2
    assert result["course_rows"][0]["parent_module"] == "专业模块"
    assert result["summary"]["course_row_count"] == 1
