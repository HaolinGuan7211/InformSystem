from __future__ import annotations

import re
from html import unescape
from typing import Any

from backend.app.services.ingestion.models import SourceEvent

TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


class EventPreprocessor:
    async def build_rule_view(self, event: SourceEvent) -> dict[str, Any]:
        title = self._normalize_text(event.title)
        content_text = self._normalize_text(event.content_text)
        html_text = self._normalize_text(TAG_RE.sub(" ", unescape(event.content_html or "")))
        attachment_names = [self._normalize_text(attachment.name) for attachment in event.attachments]

        content_segments = [segment for segment in [title, content_text, html_text, *attachment_names] if segment]
        context_segments = [segment for segment in [*content_segments, event.author, event.source_name] if segment]

        return {
            "title": title,
            "content_text": content_text,
            "html_text": html_text,
            "attachment_names": attachment_names,
            "content_view": "\n".join(content_segments),
            "context_view": "\n".join(context_segments),
            "reference_time": event.published_at or event.collected_at,
        }

    def _normalize_text(self, value: str | None) -> str:
        if not value:
            return ""
        return SPACE_RE.sub(" ", value).strip()
