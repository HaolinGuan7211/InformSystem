from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from html import unescape
from urllib.parse import urljoin

import requests

from backend.app.services.campus_auth.models import CampusAuthRequest

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/134.0.0.0 Safari/537.36"
)
CHARSET_RE = re.compile(r"charset=([A-Za-z0-9_-]+)", re.IGNORECASE)
LOGIN_ERROR_RE = re.compile(
    r'(?:id="showErrorTip"|class="form-error-tip")[^>]*>(?P<message>.*?)<',
    re.IGNORECASE | re.DOTALL,
)


@dataclass(slots=True)
class SzuLoginForm:
    login_page_url: str
    action_url: str
    execution: str
    lt: str
    salt: str


class SzuCasClient:
    def create_session(self, request: CampusAuthRequest) -> requests.Session:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": request.hints.get("user_agent", DEFAULT_USER_AGENT),
                "Referer": request.entry_url,
            }
        )
        return session

    def resolve_credentials(self, request: CampusAuthRequest) -> tuple[str, str]:
        username = request.username or self._get_env_value(request.username_env)
        password = request.password or self._get_env_value(request.password_env)
        if not username or not password:
            raise ValueError("username/password are required directly or via username_env/password_env")
        return username, password

    def bootstrap(self, session: requests.Session, entry_url: str) -> tuple[requests.Response, str]:
        response = session.get(entry_url, timeout=20, allow_redirects=True)
        response.raise_for_status()
        html = self.decode_response(response)
        return response, html

    def parse_login_form(self, login_html: str, login_page_url: str) -> SzuLoginForm:
        execution = self._extract_input_value(login_html, "execution")
        lt = self._extract_input_value(login_html, "lt") or ""
        salt_match = re.search(
            r'id="pwdEncryptSalt"[^>]*value="([^"]+)"',
            login_html,
            re.IGNORECASE,
        )
        if execution is None or salt_match is None:
            raise ValueError("Unable to parse SZU auth login form")

        action_url = self._resolve_login_action(login_html, login_page_url)
        return SzuLoginForm(
            login_page_url=login_page_url,
            action_url=action_url,
            execution=execution,
            lt=lt,
            salt=salt_match.group(1),
        )

    def submit_login(
        self,
        session: requests.Session,
        *,
        form: SzuLoginForm,
        username: str,
        password: str,
    ) -> tuple[requests.Response, str]:
        response = session.post(
            form.action_url,
            data={
                "username": username,
                "password": self.encrypt_password(password, form.salt),
                "captcha": "",
                "_eventId": "submit",
                "cllt": "userNameLogin",
                "dllt": "generalLogin",
                "lt": form.lt,
                "execution": form.execution,
            },
            timeout=20,
            allow_redirects=True,
        )
        response.raise_for_status()
        html = self.decode_response(response)
        return response, html

    def extract_login_error(self, html: str) -> str | None:
        match = LOGIN_ERROR_RE.search(html)
        if match is None:
            return None
        return self.clean_text(unescape(match.group("message")))

    def decode_response(self, response: requests.Response) -> str:
        candidates: list[str] = []
        encoding = response.encoding
        if encoding and encoding.lower() != "iso-8859-1":
            candidates.append(encoding)

        header_charset = self._extract_charset(response.headers.get("content-type", ""))
        if header_charset:
            candidates.append(header_charset)

        preview = response.content[:4096].decode("ascii", errors="ignore")
        preview_charset = self._extract_charset(preview)
        if preview_charset:
            candidates.append(preview_charset)

        if response.apparent_encoding:
            candidates.append(response.apparent_encoding)
        candidates.extend(["utf-8", "gb18030", "gbk"])

        for candidate in self._dedupe_encodings(candidates):
            try:
                text = response.content.decode(candidate)
            except (LookupError, UnicodeDecodeError):
                continue
            response.encoding = candidate
            return text

        response.encoding = "utf-8"
        return response.content.decode("utf-8", errors="replace")

    def redirect_chain(self, *responses: requests.Response) -> list[str]:
        urls: list[str] = []
        for response in responses:
            for item in [*response.history, response]:
                if item.url not in urls:
                    urls.append(item.url)
        return urls

    def encrypt_password(self, password: str, salt: str) -> str:
        node_path = shutil.which("node")
        if node_path is None:
            raise RuntimeError("Node.js is required to encrypt SZU passwords")

        script = """
const crypto = require("crypto");
const password = process.argv[1];
const salt = process.argv[2];
const chars = "ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678";
function randomString(n) {
  let out = "";
  for (let i = 0; i < n; i += 1) {
    out += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return out;
}
const key = Buffer.from(salt.trim(), "utf8");
if (![16, 24, 32].includes(key.length)) {
  throw new Error(`Unsupported AES key length: ${key.length}`);
}
const iv = Buffer.from(randomString(16), "utf8");
const payload = randomString(64) + password;
const cipher = crypto.createCipheriv(`aes-${key.length * 8}-cbc`, key, iv);
const encrypted = Buffer.concat([cipher.update(payload, "utf8"), cipher.final()]).toString("base64");
process.stdout.write(encrypted);
"""
        completed = subprocess.run(
            [node_path, "-e", script, password, salt],
            capture_output=True,
            text=True,
            check=True,
        )
        return completed.stdout.strip()

    def clean_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    def _extract_input_value(self, html: str, name: str) -> str | None:
        match = re.search(
            rf'name="{re.escape(name)}"[^>]*value="([^"]*)"',
            html,
            re.IGNORECASE,
        )
        return match.group(1) if match else None

    def _resolve_login_action(self, login_html: str, page_url: str) -> str:
        match = re.search(r'<form[^>]+action="([^"]+)"', login_html, re.IGNORECASE)
        if match is None:
            raise ValueError("Unable to find SZU auth login form action")
        return urljoin(page_url, match.group(1))

    def _extract_charset(self, value: str) -> str | None:
        match = CHARSET_RE.search(value)
        return match.group(1) if match else None

    def _dedupe_encodings(self, candidates: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = candidate.strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(candidate.strip())
        return result

    def _get_env_value(self, env_key: str | None) -> str | None:
        if not env_key:
            return None
        value = os.getenv(env_key)
        return value.strip() if value else None
