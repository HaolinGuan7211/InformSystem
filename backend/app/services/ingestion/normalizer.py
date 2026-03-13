from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from backend.app.services.ingestion.models import AttachmentInfo, SourceEvent


class Normalizer:
    def __init__(self, now_factory: Callable[[], datetime] | None = None) -> None:
        self._now_factory = now_factory or (lambda: datetime.now(timezone.utc))

    def build_source_event(
        self,
        source_config: dict[str, Any],
        *,
        channel_type: str,
        content_text: str,
        raw_identifier: str | None = None,
        source_name: str | None = None,
        title: str | None = None,
        content_html: str | None = None,
        author: str | None = None,
        published_at: str | datetime | None = None,
        collected_at: str | datetime | None = None,
        url: str | None = None,
        attachments: list[dict[str, Any]] | list[AttachmentInfo] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SourceEvent:
        published_at_iso = self.normalize_datetime(
            published_at,
            timezone_hint=source_config.get("timezone") or source_config.get("parse_config", {}).get("timezone"),
            required=False,
        )
        collected_at_iso = self.normalize_datetime(
            collected_at or self._now_factory(),
            timezone_hint=source_config.get("timezone") or source_config.get("parse_config", {}).get("timezone"),
            required=True,
        )
        normalized_title = self.clean_text(title) if title else None
        normalized_text = self.clean_text(content_text)
        if not normalized_text:
            raise ValueError("content_text cannot be empty after normalization")

        event_id = self.generate_event_id(
            source_id=source_config["source_id"],
            raw_identifier=raw_identifier,
            title=normalized_title,
            content_text=normalized_text,
            published_at=published_at_iso,
            url=url,
        )
        event_metadata = dict(metadata or {})
        if raw_identifier:
            event_metadata.setdefault("unique_source_key", f"{source_config['source_id']}:{raw_identifier}")
        elif url:
            event_metadata.setdefault("unique_source_key", f"{source_config['source_id']}:{url}")

        return SourceEvent(
            event_id=event_id,
            source_id=source_config["source_id"],
            source_type=source_config["source_type"],
            source_name=source_name or source_config["source_name"],
            channel_type=channel_type,
            title=normalized_title,
            content_text=normalized_text,
            content_html=content_html,
            author=self.clean_text(author) if author else None,
            published_at=published_at_iso,
            collected_at=collected_at_iso,
            url=url,
            attachments=self.normalize_attachments(attachments),
            metadata=event_metadata,
        )

    def normalize_datetime(
        self,
        value: str | datetime | None,
        *,
        timezone_hint: str | None = None,
        required: bool,
    ) -> str | None:
        if value is None:
            if required:
                raise ValueError("datetime value is required")
            return None

        tz = self.parse_timezone(timezone_hint)
        if isinstance(value, datetime):
            dt = value if value.tzinfo else value.replace(tzinfo=tz)
            return dt.isoformat()

        candidate = value.strip()
        if not candidate:
            if required:
                raise ValueError("datetime value is required")
            return None

        normalized = candidate.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz)
            return dt.isoformat()
        except ValueError:
            pass

        formats = (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y-%m-%d",
        )
        for fmt in formats:
            try:
                dt = datetime.strptime(candidate, fmt).replace(tzinfo=tz)
                return dt.isoformat()
            except ValueError:
                continue

        raise ValueError(f"Unsupported datetime format: {value}")

    def parse_timezone(self, timezone_hint: str | None) -> timezone:
        if not timezone_hint or timezone_hint in {"Asia/Shanghai", "Asia/Chongqing", "CST"}:
            return timezone(timedelta(hours=8))
        if timezone_hint == "UTC":
            return timezone.utc

        match = re.fullmatch(r"([+-])(\d{2}):?(\d{2})", timezone_hint)
        if not match:
            return timezone(timedelta(hours=8))

        sign = 1 if match.group(1) == "+" else -1
        hours = int(match.group(2))
        minutes = int(match.group(3))
        offset = timedelta(hours=hours, minutes=minutes) * sign
        return timezone(offset)

    def normalize_attachments(
        self,
        attachments: list[dict[str, Any]] | list[AttachmentInfo] | None,
    ) -> list[AttachmentInfo]:
        normalized: list[AttachmentInfo] = []
        for attachment in attachments or []:
            if isinstance(attachment, AttachmentInfo):
                normalized.append(attachment)
                continue
            if not attachment or not attachment.get("name"):
                continue
            normalized.append(AttachmentInfo(**attachment))
        return normalized

    def extra_metadata(self, raw_data: dict[str, Any], consumed_keys: set[str]) -> dict[str, Any]:
        return {
            key: value
            for key, value in raw_data.items()
            if key not in consumed_keys and value is not None
        }

    def html_to_text(self, html_content: str | None) -> str:
        if not html_content:
            return ""
        stripped = re.sub(r"<[^>]+>", " ", html_content)
        unescaped = html.unescape(stripped)
        return self.clean_text(unescaped)

    def clean_text(self, value: str | None) -> str:
        if not value:
            return ""
        return re.sub(r"\s+", " ", value).strip()

    def generate_event_id(
        self,
        *,
        source_id: str,
        raw_identifier: str | None,
        title: str | None,
        content_text: str,
        published_at: str | None,
        url: str | None,
    ) -> str:
        seed = raw_identifier or "|".join(
            filter(
                None,
                [
                    source_id,
                    title or "",
                    content_text,
                    published_at or "",
                    url or "",
                ],
            )
        )
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
        return f"evt_{digest}"

