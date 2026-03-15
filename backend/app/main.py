from __future__ import annotations

from fastapi import FastAPI

from backend.app.api.routes.feedback import router as feedback_router
from backend.app.api.routes.ingestion import router as ingestion_router
from backend.app.api.routes.profile_sync import router as profile_sync_router
from backend.app.api.routes.user_profile import router as user_profile_router
from backend.app.api.routes.workflow import router as workflow_router
from backend.app.container import build_container
from backend.app.core.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title=(settings.app_name if settings else "InformSystem"))
    app.state.container = build_container(settings)
    app.include_router(feedback_router)
    app.include_router(ingestion_router)
    app.include_router(profile_sync_router)
    app.include_router(user_profile_router)
    app.include_router(workflow_router)

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"success": True}

    return app


app = create_app()
