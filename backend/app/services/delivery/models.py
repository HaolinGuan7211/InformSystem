from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.app.shared.models import DecisionResult, DeliveryLog, DeliveryTask, SourceEvent, UserProfile


class GatewaySendResult(BaseModel):
    provider_message_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DigestJob(BaseModel):
    job_id: str
    user_id: str
    window_key: str
    status: str
    task_refs: list[dict[str, Any]] = Field(default_factory=list)
    scheduled_at: str
    sent_at: str | None = None
    created_at: str


__all__ = [
    "DecisionResult",
    "DeliveryLog",
    "DeliveryTask",
    "DigestJob",
    "GatewaySendResult",
    "SourceEvent",
    "UserProfile",
]
