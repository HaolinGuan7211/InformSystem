from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.app.container import AppContainer
from backend.app.shared.models import DeliveryLog, FeedbackType

router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])


class FeedbackCreateRequest(BaseModel):
    feedback_id: str | None = None
    user_id: str
    event_id: str
    decision_id: str | None = None
    delivery_log_id: str | None = None
    feedback_type: FeedbackType
    rating: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


@router.post("")
async def create_feedback(payload: FeedbackCreateRequest, request: Request) -> dict[str, Any]:
    container = get_container(request)
    try:
        record = await container.feedback_service.record_user_feedback(
            payload.model_dump(exclude_none=True)
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"success": True, "feedback_id": record.feedback_id}


@router.post("/delivery-outcomes")
async def create_delivery_outcome(payload: DeliveryLog, request: Request) -> dict[str, Any]:
    container = get_container(request)
    await container.feedback_service.record_delivery_outcome(payload)
    return {"success": True, "log_id": payload.log_id}


@router.get("/optimization-samples")
async def export_optimization_samples(
    request: Request,
    limit: int = Query(default=1000, ge=1, le=5000),
    source: str | None = None,
    outcome_label: str | None = None,
) -> dict[str, Any]:
    container = get_container(request)
    items = await container.feedback_service.export_optimization_samples(
        limit=limit,
        source=source,
        outcome_label=outcome_label,
    )
    return {
        "success": True,
        "count": len(items),
        "items": [item.model_dump() for item in items],
    }
