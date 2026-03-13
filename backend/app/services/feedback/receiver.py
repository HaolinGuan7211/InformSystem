from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from backend.app.shared.models import UserFeedbackRecord


class FeedbackReceiver:
    def __init__(self, timezone_offset: str = "+08:00") -> None:
        self._timezone_offset = timezone_offset

    async def receive(self, payload: dict[str, Any]) -> UserFeedbackRecord:
        metadata = payload.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be an object")

        created_at = payload.get("created_at") or self._default_timestamp()
        feedback_id = payload.get("feedback_id") or self._build_feedback_id(metadata)

        return UserFeedbackRecord.model_validate(
            {
                "feedback_id": feedback_id,
                "user_id": payload.get("user_id"),
                "event_id": payload.get("event_id"),
                "decision_id": payload.get("decision_id"),
                "delivery_log_id": payload.get("delivery_log_id"),
                "feedback_type": payload.get("feedback_type"),
                "rating": payload.get("rating"),
                "comment": payload.get("comment"),
                "metadata": metadata,
                "created_at": created_at,
            }
        )

    def _build_feedback_id(self, metadata: dict[str, Any]) -> str:
        request_id = metadata.get("request_id")
        if isinstance(request_id, str) and request_id.strip():
            digest = hashlib.sha1(request_id.strip().encode("utf-8")).hexdigest()[:12]
            return f"fb_{digest}"
        return f"fb_{uuid4().hex[:12]}"

    def _default_timestamp(self) -> str:
        offset = self._parse_timezone_offset(self._timezone_offset)
        return datetime.now(timezone.utc).astimezone(offset).isoformat()

    @staticmethod
    def _parse_timezone_offset(value: str) -> timezone:
        sign = 1 if value.startswith("+") else -1
        hour_text, minute_text = value[1:].split(":", maxsplit=1)
        delta = timedelta(hours=int(hour_text), minutes=int(minute_text))
        return timezone(sign * delta)
