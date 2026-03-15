from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from backend.app.services.profile_sampling.models import ProfileSyncRequest

router = APIRouter(prefix="/api/v1/profile-sync", tags=["profile_sync"])


def get_container(request: Request) -> Any:
    return request.app.state.container


@router.post("/{school_code}/run")
async def run_profile_sync(
    school_code: str,
    payload: ProfileSyncRequest,
    request: Request,
) -> dict[str, object]:
    container = get_container(request)
    sync_request = payload.model_copy(update={"school_code": school_code})

    try:
        result = await container.profile_sync_orchestrator.run(sync_request)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"success": True, "result": result.model_dump()}
