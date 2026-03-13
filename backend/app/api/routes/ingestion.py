from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.app.container import AppContainer

router = APIRouter(prefix="/api/v1", tags=["ingestion"])


class ManualIngestRequest(BaseModel):
    source_name: str = "manual_input"
    title: str | None = None
    content_text: str
    published_at: str | None = None
    author: str | None = None
    url: str | None = None


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


@router.post("/webhooks/{source_id}")
async def receive_webhook(source_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    container = get_container(request)
    try:
        events = await container.webhook_receiver.receive(source_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"success": True, "accepted": len(events)}


@router.post("/ingestion/manual")
async def ingest_manual(payload: ManualIngestRequest, request: Request) -> dict[str, Any]:
    container = get_container(request)
    source_config = await container.source_registry.get_source_by_id("manual_input_default")
    if source_config is None:
        raise HTTPException(status_code=500, detail="manual_input_default source config not found")

    try:
        events = await container.ingestion_service.ingest(payload.model_dump(exclude_none=True), source_config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"success": True, "event_ids": [event.event_id for event in events]}


@router.post("/ingestion/replay/{event_id}")
async def replay_event(event_id: str, request: Request) -> dict[str, Any]:
    container = get_container(request)
    event = await container.ingestion_service.replay(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Unknown event_id: {event_id}")
    return {"success": True, "event": event.model_dump()}

