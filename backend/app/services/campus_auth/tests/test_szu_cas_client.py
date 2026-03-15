from __future__ import annotations

from backend.app.services.campus_auth.szu.cas_client import SzuCasClient

LOGIN_PAGE_HTML = """
<html>
  <body>
    <form id="casLoginForm" action="/authserver/login?service=https%3A%2F%2Fehall.szu.edu.cn%2Flogin">
      <input name="execution" value="e1s1" />
      <input name="lt" value="LT-abc" />
      <input id="pwdEncryptSalt" value="LbYtGQSI0WCUdT5g" />
    </form>
  </body>
</html>
"""


def test_szu_cas_client_parses_login_form() -> None:
    client = SzuCasClient()

    form = client.parse_login_form(
        LOGIN_PAGE_HTML,
        "https://authserver.szu.edu.cn/authserver/login?service=https%3A%2F%2Fehall.szu.edu.cn%2Flogin",
    )

    assert form.execution == "e1s1"
    assert form.lt == "LT-abc"
    assert form.salt == "LbYtGQSI0WCUdT5g"
    assert form.action_url == (
        "https://authserver.szu.edu.cn/authserver/login?service=https%3A%2F%2Fehall.szu.edu.cn%2Flogin"
    )


def test_szu_cas_client_extracts_login_error() -> None:
    client = SzuCasClient()

    error = client.extract_login_error(
        '<span id="showErrorTip"> 登录名或密码不正确 </span>'
    )

    assert error == "登录名或密码不正确"
