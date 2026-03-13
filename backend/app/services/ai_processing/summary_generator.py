from __future__ import annotations

from typing import Any


class SummaryGenerator:
    def __init__(self, max_length: int = 120) -> None:
        self._max_length = max_length

    async def summarize(self, raw_response: dict[str, Any], fallback_text: str | None = None) -> str | None:
        summary = raw_response.get("summary")
        cleaned = " ".join(str(summary).split()).strip() if isinstance(summary, str) else ""
        if not cleaned and fallback_text:
            cleaned = " ".join(fallback_text.split()).strip()
        if not cleaned:
            return None
        if len(cleaned) <= self._max_length:
            return cleaned
        return cleaned[: self._max_length - 1].rstrip("，,；;。.") + "…"
