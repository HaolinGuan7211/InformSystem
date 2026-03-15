from __future__ import annotations

import os
import re
import shutil
import time
from html import unescape
from typing import Any
from urllib.parse import urljoin

import requests

from backend.app.services.campus_auth.models import CampusAuthRequest
from backend.app.services.campus_auth.szu.cas_client import SzuCasClient
from backend.app.services.ingestion.connectors.base import Connector
from backend.app.services.ingestion.models import SourceEvent
from backend.app.services.ingestion.normalizer import Normalizer

DETAIL_LINK_RE = re.compile(
    r'href="(?P<href>\.?/?view\.asp\?id=(?P<id>\d{5,}))"[^>]*>(?P<title>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
TITLE_RE = re.compile(
    r'<td[^>]*height="80px"[^>]*>\s*<span[^>]*>(?P<title>.*?)</span>\s*</td>',
    re.IGNORECASE | re.DOTALL,
)
METADATA_RE = re.compile(
    r'<td[^>]*height=50px[^>]*>(?P<meta>.*?)</td>',
    re.IGNORECASE | re.DOTALL,
)
CONTENT_RE = re.compile(
    r'<td[^>]*height="300"[^>]*valign=top[^>]*>(?P<content>.*?)</td>',
    re.IGNORECASE | re.DOTALL,
)
DATETIME_RE = re.compile(r"(?P<published_at>\d{4}/\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2}:\d{2})")
AUTHOR_RE = re.compile(r"撰稿[:：]\s*(?P<author>.*?)(?:\s+审核[:：].*|$)")
ATTACHMENT_LINK_RE = re.compile(
    r'<a[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<name>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
FILE_EXTENSION_RE = re.compile(r"\.(?:pdf|doc|docx|xls|xlsx|ppt|pptx|zip|rar|7z|jpg|jpeg|png)$", re.IGNORECASE)
SCRIPT_RE = re.compile(r"<script.*?</script>", re.IGNORECASE | re.DOTALL)
STYLE_RE = re.compile(r"<style.*?</style>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
LOGIN_ERROR_RE = re.compile(r'(?:id="showErrorTip"|class="form-error-tip")[^>]*>(?P<message>.*?)<', re.IGNORECASE | re.DOTALL)


class SzuBoardParser:
    def __init__(self, normalizer: Normalizer) -> None:
        self._normalizer = normalizer

    def parse_list_page(
        self,
        html: str,
        *,
        page_url: str,
        limit: int,
    ) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        seen: set[str] = set()

        for match in DETAIL_LINK_RE.finditer(html):
            href = match.group("href")
            if href in seen:
                continue

            title = self._clean_html_text(match.group("title"))
            if not title:
                continue

            seen.add(href)
            items.append(
                {
                    "detail_url": urljoin(page_url, href),
                    "list_title": title,
                    "raw_identifier": match.group("id"),
                }
            )
            if len(items) >= limit:
                break

        return items

    def parse_detail_page(
        self,
        html: str,
        *,
        detail_url: str,
        list_title: str | None = None,
        raw_identifier: str | None = None,
    ) -> dict[str, Any]:
        title_match = TITLE_RE.search(html)
        meta_match = METADATA_RE.search(html)
        content_match = CONTENT_RE.search(html)
        if title_match is None or meta_match is None or content_match is None:
            raise ValueError("Unable to parse SZU board detail page")

        title = self._clean_html_text(title_match.group("title")) or list_title
        meta_text = self._clean_html_text(meta_match.group("meta"))
        published_at_match = DATETIME_RE.search(meta_text)
        published_at = published_at_match.group("published_at") if published_at_match else None

        department = None
        if published_at_match is not None:
            department = self._normalizer.clean_text(meta_text[: published_at_match.start()])

        content_html = content_match.group("content")
        content_text = self._clean_html_text(content_html)
        author_match = AUTHOR_RE.search(content_text)
        author = author_match.group("author").strip() if author_match else None

        return {
            "raw_identifier": raw_identifier,
            "url": detail_url,
            "title": title,
            "content_text": content_text,
            "html": content_html,
            "published_at": published_at,
            "author": author,
            "attachments": self._extract_attachments(content_html, detail_url),
            "department": department,
            "list_title": list_title,
            "detail_url": detail_url,
        }

    def _extract_attachments(self, content_html: str, detail_url: str) -> list[dict[str, Any]]:
        attachments: list[dict[str, Any]] = []
        for match in ATTACHMENT_LINK_RE.finditer(content_html):
            href = urljoin(detail_url, match.group("href"))
            name = self._clean_html_text(match.group("name"))
            if not name:
                continue
            if not self._is_attachment_link(href, name):
                continue
            attachments.append(
                {
                    "name": name,
                    "url": href,
                }
            )
        return attachments

    def _is_attachment_link(self, href: str, name: str) -> bool:
        href_lower = href.lower()
        name_lower = name.lower()
        if FILE_EXTENSION_RE.search(href_lower) or FILE_EXTENSION_RE.search(name_lower):
            return True
        return any(token in href_lower for token in ["/upload/", "/file/", "download", "attachment"])

    def _clean_html_text(self, value: str | None) -> str:
        if not value:
            return ""
        stripped = SCRIPT_RE.sub(" ", value)
        stripped = STYLE_RE.sub(" ", stripped)
        stripped = TAG_RE.sub(" ", stripped)
        return self._normalizer.clean_text(unescape(stripped).replace("\xa0", " "))


class SzuBoardConnector(Connector):
    def __init__(self, normalizer: Normalizer) -> None:
        self._normalizer = normalizer
        self._parser = SzuBoardParser(normalizer)
        self._cas_client = SzuCasClient()

    async def fetch(self, source_config: dict[str, Any]) -> list[dict[str, Any]]:
        auth_config = source_config.get("auth_config", {})
        parse_config = source_config.get("parse_config", {})
        username = self._resolve_secret(auth_config, "username")
        password = self._resolve_secret(auth_config, "password")
        if not username or not password:
            raise ValueError("SZU board credentials are required via auth_config or environment variables")

        login_url = auth_config.get("login_url")
        if not isinstance(login_url, str) or not login_url:
            raise ValueError("auth_config.login_url is required for SZU board connector")

        list_urls = self._resolve_list_urls(parse_config, auth_config)
        if not list_urls:
            raise ValueError("parse_config.list_url is required for SZU board connector")

        timeout = float(parse_config.get("request_timeout_seconds", 20))
        max_items = max(1, int(parse_config.get("max_items", 1)))
        request_delay_seconds = max(0.0, float(parse_config.get("request_delay_seconds", 0.0)))
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": self._cas_client.create_session(
                    CampusAuthRequest(
                        school_code="szu",
                        target_system="board",
                        entry_url=login_url,
                    )
                ).headers["User-Agent"],
                "Referer": login_url,
            }
        )

        login_page = session.get(login_url, timeout=timeout)
        login_page.raise_for_status()
        login_html = self._cas_client.decode_response(login_page)
        form = self._cas_client.parse_login_form(login_html, login_page.url)
        board_response = session.post(
            form.action_url,
            data={
                "username": username,
                "password": self._cas_client.encrypt_password(password, form.salt),
                "captcha": "",
                "_eventId": "submit",
                "cllt": "userNameLogin",
                "dllt": "generalLogin",
                "lt": form.lt,
                "execution": form.execution,
            },
            timeout=timeout,
            allow_redirects=True,
        )
        board_response.raise_for_status()
        board_html = self._cas_client.decode_response(board_response)
        self._ensure_login_success(board_response.url, board_html)

        list_items = self._collect_list_items(
            session=session,
            list_urls=list_urls,
            board_url=board_response.url,
            board_html=board_html,
            timeout=timeout,
            max_items=max_items,
            request_delay_seconds=request_delay_seconds,
        )

        results: list[dict[str, Any]] = []
        for index, item in enumerate(list_items):
            if request_delay_seconds and index > 0:
                time.sleep(request_delay_seconds)
            detail_response = session.get(
                item["detail_url"],
                headers={"Referer": item.get("referer") or board_response.url},
                timeout=timeout,
            )
            detail_response.raise_for_status()
            detail_html = self._cas_client.decode_response(detail_response)
            parsed = self._parser.parse_detail_page(
                detail_html,
                detail_url=item["detail_url"],
                list_title=item["list_title"],
                raw_identifier=item["raw_identifier"],
            )
            results.append(parsed)

        return results

    async def normalize(
        self,
        raw_data: dict[str, Any],
        source_config: dict[str, Any],
    ) -> list[SourceEvent]:
        consumed_keys = {
            "raw_identifier",
            "url",
            "title",
            "content_text",
            "html",
            "published_at",
            "author",
            "attachments",
            "department",
            "list_title",
            "detail_url",
        }
        metadata = self._normalizer.extra_metadata(raw_data, consumed_keys)
        metadata["authority_level"] = source_config.get("authority_level")
        if raw_data.get("department"):
            metadata["department"] = raw_data["department"]
        if raw_data.get("list_title") and raw_data.get("list_title") != raw_data.get("title"):
            metadata["list_title"] = raw_data["list_title"]

        event = self._normalizer.build_source_event(
            source_config,
            raw_identifier=raw_data.get("raw_identifier") or raw_data.get("url"),
            channel_type=source_config.get("parse_config", {}).get("channel_type", "website_notice"),
            title=raw_data.get("title"),
            content_text=raw_data.get("content_text") or self._normalizer.html_to_text(raw_data.get("html")),
            content_html=raw_data.get("html"),
            author=raw_data.get("author") or raw_data.get("department"),
            published_at=raw_data.get("published_at"),
            url=raw_data.get("url"),
            attachments=raw_data.get("attachments"),
            metadata=metadata,
        )
        return [event]

    async def health_check(self, source_config: dict[str, Any]) -> bool:
        auth_config = source_config.get("auth_config", {})
        login_url = auth_config.get("login_url")
        list_urls = self._resolve_list_urls(source_config.get("parse_config", {}), auth_config)
        has_credentials = bool(self._resolve_secret(auth_config, "username") and self._resolve_secret(auth_config, "password"))
        has_node = shutil.which("node") is not None
        return bool(login_url and list_urls and has_credentials and has_node)

    def _collect_list_items(
        self,
        *,
        session: requests.Session,
        list_urls: list[str],
        board_url: str,
        board_html: str,
        timeout: float,
        max_items: int,
        request_delay_seconds: float,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen_detail_urls: set[str] = set()

        for index, list_url in enumerate(list_urls):
            if len(results) >= max_items:
                break

            if self._urls_match(board_url, list_url):
                page_html = board_html
                referer = board_url
            else:
                if request_delay_seconds and index > 0:
                    time.sleep(request_delay_seconds)
                response = session.get(
                    list_url,
                    headers={"Referer": board_url},
                    timeout=timeout,
                )
                response.raise_for_status()
                page_html = self._cas_client.decode_response(response)
                referer = response.url

            remaining = max_items - len(results)
            page_items = self._parser.parse_list_page(
                page_html,
                page_url=list_url,
                limit=remaining,
            )
            for item in page_items:
                if item["detail_url"] in seen_detail_urls:
                    continue
                results.append({**item, "referer": referer})
                seen_detail_urls.add(item["detail_url"])
                if len(results) >= max_items:
                    break

        return results

    def _resolve_list_urls(
        self,
        parse_config: dict[str, Any],
        auth_config: dict[str, Any],
    ) -> list[str]:
        configured = parse_config.get("list_urls")
        if isinstance(configured, list):
            result = [value.strip() for value in configured if isinstance(value, str) and value.strip()]
            if result:
                return result

        list_url = parse_config.get("list_url") or auth_config.get("board_url")
        if isinstance(list_url, str) and list_url.strip():
            return [list_url.strip()]
        return []

    def _urls_match(self, left: str, right: str) -> bool:
        return left.rstrip("/") == right.rstrip("/")

    def _ensure_login_success(self, final_url: str, html: str) -> None:
        if "/board/" in final_url:
            return

        error_match = LOGIN_ERROR_RE.search(html)
        if error_match is not None:
            message = self._normalizer.clean_text(unescape(error_match.group("message")))
            raise PermissionError(message or "SZU board login failed")
        raise PermissionError("SZU board login failed or additional verification is required")

    def _resolve_secret(self, auth_config: dict[str, Any], key: str) -> str | None:
        direct_value = auth_config.get(key)
        if isinstance(direct_value, str) and direct_value.strip():
            return direct_value.strip()

        env_key = auth_config.get(f"{key}_env")
        if isinstance(env_key, str) and env_key.strip():
            value = os.getenv(env_key.strip())
            if value:
                return value.strip()
        return None
