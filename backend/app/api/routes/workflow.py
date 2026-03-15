from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.container import AppContainer

router = APIRouter(prefix="/api/v1/workflows", tags=["workflow"])


class WorkflowRunRequest(BaseModel):
    user_ids: list[str] | None = None
    context: dict[str, Any] = Field(default_factory=dict)


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


@router.post("/events/{event_id}/run")
async def run_event_workflow(
    event_id: str,
    payload: WorkflowRunRequest,
    request: Request,
) -> dict[str, Any]:
    container = get_container(request)
    result = await container.workflow_orchestrator.replay_event(
        event_id=event_id,
        user_ids=payload.user_ids,
        context=payload.context,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"Unknown event_id: {event_id}")
    return {"success": True, "workflow": result.model_dump()}
