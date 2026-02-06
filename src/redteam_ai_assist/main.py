from __future__ import annotations

from fastapi import FastAPI

from redteam_ai_assist.api.routes import router as assistant_router
from redteam_ai_assist.config import get_settings
from redteam_ai_assist.services.assistant_service import AssistantService


def create_app() -> FastAPI:
    settings = get_settings()
    service = AssistantService(settings=settings)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "Multi-tenant redteam coaching assistant for an isolated cyber range. "
            "Uses LangGraph workflow + RAG + scope policy guard."
        ),
    )
    app.state.settings = settings
    app.state.assistant_service = service
    app.include_router(assistant_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "app_env": settings.app_env}

    return app


app = create_app()
