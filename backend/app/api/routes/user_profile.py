from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from backend.app.services.user_profile.models import UserProfile

router = APIRouter(prefix="/api/v1/users", tags=["user_profile"])


def get_container(request: Request) -> Any:
    return request.app.state.container


@router.get("/active")
async def list_active_users(
    request: Request,
    limit: int = Query(default=1000, ge=1, le=5000),
) -> dict[str, object]:
    container = get_container(request)
    users = await container.user_profile_service.list_active_users(limit=limit)
    return {
        "success": True,
        "count": len(users),
        "users": [user.model_dump() for user in users],
    }


@router.get("/{user_id}/profile")
async def get_user_profile(user_id: str, request: Request) -> dict[str, object]:
    container = get_container(request)
    profile = await container.user_profile_service.get_profile(user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Unknown user_id: {user_id}")
    return {"success": True, "profile": profile.model_dump()}


@router.put("/{user_id}/profile")
async def upsert_user_profile(
    user_id: str,
    payload: UserProfile,
    request: Request,
) -> dict[str, object]:
    container = get_container(request)
    profile = payload if payload.user_id == user_id else payload.model_copy(update={"user_id": user_id})
    await container.user_profile_service.upsert_profile(profile)
    snapshot = await container.user_profile_service.build_snapshot(user_id)
    if snapshot is None:
        raise HTTPException(status_code=500, detail=f"Failed to build snapshot for user_id: {user_id}")
    return {"success": True, "profile": snapshot.model_dump()}
